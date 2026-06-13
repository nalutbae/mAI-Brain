"""mAI-Brain AI 챗봇 — 하이브리드 검색 모듈

질문 임베딩(dense+sparse) → 벡터 DB 검색 → 리랭킹(선택) → SearchResult 반환.

핵심 설계:
- 검색 모드별 top-k 조절: 팩트(5), 요약(8), 컬럼(18), 추론(15)
- 리랭커 활성화 시 초기 검색 후보를 늘려 리랭크 후 최종 k개 선택
  팩트(20→5), 요약(25→8), 컬럼(30→12), 추론(30→10)
- 검색 결과에 메타데이터(출처, 점수, 페이지) 포함
- VectorDBProvider를 통해 Qdrant/Chroma/PGVector 전환 가능
- sparse 벡터 지원 여부에 따라 검색 방식 자동 분기
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

from app.config import ChatMode, get_settings
from app.core.embedding import EmbeddingResult, get_embedding_provider
from app.core.reranker import (
    RERANK_FINAL_K,
    RERANK_INITIAL_K,
    get_reranker,
)
from app.core.vectordb import VectorDBProvider, get_vector_db
from app.models.chat import SearchHit

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# 모드별 top-k 매핑
# --------------------------------------------------------------------------- #

def _get_top_k(mode: ChatMode) -> int:
    """검색 모드에 따른 top-k 반환.

    리랭커가 활�성화된 경우 초기 후보를 늘리기 위해
    RERANK_INITIAL_K 값을 사용합니다.

    Args:
        mode: 채팅 모드 (fact/summary/column/reasoning/creative)

    Returns:
        검색 결과 수 (creative는 0 = 검색 안 함)
    """
    settings = get_settings()

    if settings.reranker_enabled:
        # 리랭커 활성화 → 더 많은 후보를 검색한 후 리랭크
        return RERANK_INITIAL_K.get(mode, settings.top_k_fact)

    # 리랭커 비활성화 → 기존 top-k 그대로 사용
    mode_top_k = {
        ChatMode.FACT: settings.top_k_fact,
        ChatMode.SUMMARY: settings.top_k_summary,
        ChatMode.COLUMN: settings.top_k_column,
        ChatMode.REASONING: settings.top_k_reasoning,
        ChatMode.CREATIVE: 0,
    }
    return mode_top_k.get(mode, settings.top_k_fact)


def _get_final_k(mode: ChatMode) -> int:
    """리랭크 후 최종 반환할 결과 수.

    리랭커 비활성화 시 _get_top_k와 동일.
    """
    settings = get_settings()

    if settings.reranker_enabled:
        return RERANK_FINAL_K.get(mode, settings.top_k_fact)

    mode_top_k = {
        ChatMode.FACT: settings.top_k_fact,
        ChatMode.SUMMARY: settings.top_k_summary,
        ChatMode.COLUMN: settings.top_k_column,
        ChatMode.REASONING: settings.top_k_reasoning,
        ChatMode.CREATIVE: 0,
    }
    return mode_top_k.get(mode, settings.top_k_fact)


# --------------------------------------------------------------------------- #
# 검색 결과 데이터 클래스
# --------------------------------------------------------------------------- #

@dataclass
class SearchResult:
    """하이브리드 검색 결과.

    Attributes:
        hits: 검색 결과 항목 리스트
        query: 원본 질문
        mode: 사용된 검색 모드
    """
    hits: list[SearchHit]
    query: str
    mode: ChatMode


# --------------------------------------------------------------------------- #
# 핵심 검색 함수
# --------------------------------------------------------------------------- #

def hybrid_search(
    query: str,
    mode: ChatMode = ChatMode.FACT,
    session_id: Optional[str] = None,
    vdb: Optional[VectorDBProvider] = None,
    collection_name: Optional[str] = None,
    query_expansion: Optional[str] = None,
) -> SearchResult:
    """벡터 DB 검색 + 리랭킹 수행.

    파이프라인:
    1. (선택) 쿼리 확장 — query_expansion 파라미터가 설정된 경우
    2. 질문 임베딩 (dense + sparse) 생성
    3. VectorDBProvider.search() 호출 (리랭커 활성화 시 후보 많이 검색)
    4. 리랭커 재정렬 (활성화 시)
    5. 검색 결과 → SearchHit 리스트 변환

    Args:
        query: 사용자 질문
        mode: 채팅 모드 (top-k 결정)
        session_id: 세션 ID (향후 세션별 필터링용, 현재 미사용)
        vdb: 벡터 DB 프로바이더 (None이면 기본 인스턴스)
        collection_name: 검색 대상 컬렉션 이름 (None이면 기본 컬렉션)
        query_expansion: 쿼리 확장 전략
            "multi_query" | "hyde" | "korean_synonyms" | "auto" | None

    Returns:
        SearchResult: 검색 결과 + 메타데이터
    """
    # ── 쿼리 확장 (선택) ─────────────────────────────────────────────── #
    # query_expansion이 설정되면 확장된 쿼리들로 다중 검색 후 결과 병합
    if query_expansion:
        from app.core.query_expansion import QueryExpansionStrategy, get_query_expander

        try:
            strategy = QueryExpansionStrategy(query_expansion)
        except ValueError:
            logger.warning(
                "알 수 없는 쿼리 확장 전략: %s — 확장 없이 검색", query_expansion,
            )
            strategy = QueryExpansionStrategy.NONE

        if strategy != QueryExpansionStrategy.NONE:
            expander = get_query_expander()
            merged_hits, expansion = expander.expand_and_search(
                query=query,
                strategy=strategy,
                mode=mode,
                session_id=session_id,
                collection_name=collection_name,
            )
            logger.info(
                "쿼리 확장 검색 완료: 전략=%s, 확장=%d개, 결과=%d개",
                expansion.strategy_used.value,
                len(expansion.expanded_queries),
                len(merged_hits),
            )
            # 리랭킹 적용 (활성화 시)
            final_k = _get_final_k(mode)
            reranker = get_reranker()
            if reranker is not None and merged_hits:
                min_score = get_settings().reranker_min_score
                merged_hits = reranker.rerank(
                    query=query,
                    hits=merged_hits,
                    top_k=final_k,
                    min_score=min_score,
                )
            elif len(merged_hits) > final_k:
                merged_hits = merged_hits[:final_k]

            return SearchResult(hits=merged_hits, query=query, mode=mode)

    # ── 일반 검색 파이프라인 ──────────────────────────────────────────── #
    initial_k = _get_top_k(mode)
    final_k = _get_final_k(mode)

    logger.info(
        "벡터 DB 검색: query='%s', mode=%s, initial_k=%d, final_k=%d",
        query[:50], mode.value, initial_k, final_k,
    )

    # 1. 질문 임베딩 생성
    embedding_provider = get_embedding_provider()
    embedding_result: EmbeddingResult = embedding_provider.encode([query])

    if not embedding_result.dense:
        logger.warning("임베딩 결과 없음 — 빈 검색 결과 반환")
        return SearchResult(hits=[], query=query, mode=mode)

    query_dense = embedding_result.dense[0]

    # 2. VectorDB 검색
    _vdb = vdb or get_vector_db()

    # sparse 벡터 준비 — 프로바이더가 지원하는 경우만
    query_sparse = None
    if _vdb.supports_sparse() and embedding_result.sparse and embedding_result.sparse[0]:
        query_sparse = embedding_result.sparse[0]

    results = _vdb.search(
        query_dense=query_dense,
        query_sparse=query_sparse,
        limit=initial_k,
        collection_name=collection_name,
    )

    # 3. 검색 결과 변환 (VectorDBProvider.SearchHit → chat.SearchHit)
    hits: list[SearchHit] = []
    for hit in results:
        payload = hit.payload
        hits.append(SearchHit(
            text=payload.get("text", ""),
            source=payload.get("source", "알 수 없음"),
            score=hit.score,
            chunk_index=payload.get("chunk_index"),
            page=payload.get("page"),
        ))

    # 4. 리랭킹 (활성화 시)
    reranker = get_reranker()
    if reranker is not None and hits:
        min_score = get_settings().reranker_min_score
        hits = reranker.rerank(
            query=query,
            hits=hits,
            top_k=final_k,
            min_score=min_score,
        )
        logger.info(
            "리랭크 완료: %d→%d개 (mode=%s)",
            len(results), len(hits), mode.value,
        )
    elif initial_k != final_k and hits:
        # 리랭커 비활성화지만 initial_k != final_k인 경우 잘라내기
        # (정상적으로는 이 경로를 타지 않음 — 리랭커 비활성화 시 initial_k == final_k)
        hits = hits[:final_k]

    logger.info("검색 완료: %d개 결과 (mode=%s)", len(hits), mode.value)

    return SearchResult(hits=hits, query=query, mode=mode)