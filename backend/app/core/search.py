"""mAI-Brain AI 챗봇 — 하이브리드 검색 모듈

질문 임베딩(dense+sparse) → Qdrant RRF 하이브리드 검색 → SearchResult 반환.

핵심 설계:
- 검색 모드별 top-k 조절: 팩트(5), 요약(8), 컬럼(18)
- 검색 결과에 메타데이터(출처, 점수, 페이지) 포함
- 인덱서(indexer.py)의 _token_to_index를 직접 임포트하여
  인덱싱/검색 간 해시 로직이 한 곳(indexer.py)에만 정의됨
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

from qdrant_client.models import Fusion, FusionQuery, Prefetch, SparseVector

from app.config import ChatMode, get_settings
from app.core.embedding import EmbeddingResult, get_embedding_provider
from app.core.qdrant import QdrantManager, get_qdrant
from app.ingestion.indexer import _token_to_index
from app.models.chat import SearchHit

logger = logging.getLogger(__name__)


def _sparse_dict_to_qdrant(sparse: dict[str, float]) -> SparseVector:
    """bge-m3 lexical_weights → Qdrant SparseVector 변환.

    Args:
        sparse: {토큰문자열: 가중치} 딕셔너리

    Returns:
        SparseVector: Qdrant 검색 쿼리용
    """
    if not sparse:
        return SparseVector(indices=[], values=[])

    indices = [_token_to_index(k) for k in sparse.keys()]
    values = list(sparse.values())

    return SparseVector(indices=indices, values=values)


# --------------------------------------------------------------------------- #
# 모드별 top-k 매핑
# --------------------------------------------------------------------------- #

def _get_top_k(mode: ChatMode) -> int:
    """검색 모드에 따른 top-k 반환.

    Args:
        mode: 채팅 모드 (fact/summary/column)

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
) -> SearchResult:
    """하이브리드 검색 수행.

    파이프라인:
    1. 질문 임베딩 (dense + sparse) 생성
    2. Qdrant RRF 하이브리드 검색 (dense + sparse 융합)
    3. 검색 결과 → SearchHit 리스트 변환

    Args:
        query: 사용자 질문
        mode: 채팅 모드 (top-k 결정)
        session_id: 세션 ID (향후 세션별 필터링용, 현재 미사용)

    Returns:
        SearchResult: 검색 결과 + 메타데이터
    """
    top_k = _get_top_k(mode)
    logger.info(
        "하이브리드 검색: query='%s', mode=%s, top_k=%d",
        query[:50], mode.value, top_k,
    )

    # 1. 질문 임베딩 생성
    embedding_provider = get_embedding_provider()
    embedding_result: EmbeddingResult = embedding_provider.encode([query])

    if not embedding_result.dense:
        logger.warning("임베딩 결과 없음 — 빈 검색 결과 반환")
        return SearchResult(hits=[], query=query, mode=mode)

    query_dense = embedding_result.dense[0]

    # 2. Qdrant 검색 — sparse 유무에 따라 검색 방식 분기
    qdrant: QdrantManager = get_qdrant()

    # sparse 벡터 준비
    has_sparse = bool(embedding_result.sparse and embedding_result.sparse[0])

    if has_sparse:
        # 하이브리드 검색 (dense + sparse RRF 융합)
        query_sparse_vec = _sparse_dict_to_qdrant(embedding_result.sparse[0])
        prefetch = [
            Prefetch(
                query=query_dense,
                using="dense",
                limit=top_k * 2,
            ),
            Prefetch(
                query=query_sparse_vec,
                using="sparse",
                limit=top_k * 2,
            ),
        ]
        fusion_query = FusionQuery(fusion=Fusion.RRF)
        response = qdrant.client.query_points(
            collection_name=qdrant.collection_name,
            query=fusion_query,
            prefetch=prefetch,
            limit=top_k,
            with_payload=True,
        )
    else:
        # API 임베딩 모드: dense-only 검색
        logger.info("API 임베딩 모드 — dense-only 검색")
        response = qdrant.client.query_points(
            collection_name=qdrant.collection_name,
            query=query_dense,
            using="dense",
            limit=top_k,
            with_payload=True,
        )

    # 3. 검색 결과 변환
    hits: list[SearchHit] = []
    for point in response.points:
        payload = point.payload or {}
        hits.append(SearchHit(
            text=payload.get("text", ""),
            source=payload.get("source", "알 수 없음"),
            score=point.score,
            chunk_index=payload.get("chunk_index"),
            page=payload.get("page"),
        ))

    logger.info("검색 완료: %d개 결과 (mode=%s)", len(hits), mode.value)

    return SearchResult(hits=hits, query=query, mode=mode)