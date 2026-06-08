"""mAI-Brain AI 챗봇 — 하이브리드 검색 모듈

질문 임베딩(dense+sparse) → 벡터 DB 검색 → SearchResult 반환.

핵심 설계:
- 검색 모드별 top-k 조절: 팩트(5), 요약(8), 컬럼(18), 추론(15)
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
from app.core.vectordb import VectorDBProvider, get_vector_db
from app.models.chat import SearchHit

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# 모드별 top-k 매핑
# --------------------------------------------------------------------------- #

def _get_top_k(mode: ChatMode) -> int:
    """검색 모드에 따른 top-k 반환.

    Args:
        mode: 채팅 모드 (fact/summary/column/reasoning)

    Returns:
        검색 결과 수
    """
    settings = get_settings()
    mode_top_k = {
        ChatMode.FACT: settings.top_k_fact,
        ChatMode.SUMMARY: settings.top_k_summary,
        ChatMode.COLUMN: settings.top_k_column,
        ChatMode.REASONING: settings.top_k_reasoning,
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
) -> SearchResult:
    """벡터 DB 검색 수행.

    파이프라인:
    1. 질문 임베딩 (dense + sparse) 생성
    2. VectorDBProvider.search() 호출
    3. 검색 결과 → SearchHit 리스트 변환

    Args:
        query: 사용자 질문
        mode: 채팅 모드 (top-k 결정)
        session_id: 세션 ID (향후 세션별 필터링용, 현재 미사용)
        vdb: 벡터 DB 프로바이더 (None이면 기본 인스턴스)

    Returns:
        SearchResult: 검색 결과 + 메타데이터
    """
    top_k = _get_top_k(mode)
    logger.info(
        "벡터 DB 검색: query='%s', mode=%s, top_k=%d",
        query[:50], mode.value, top_k,
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
        limit=top_k,
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

    logger.info("검색 완료: %d개 결과 (mode=%s)", len(hits), mode.value)

    return SearchResult(hits=hits, query=query, mode=mode)