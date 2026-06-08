"""mAI-Brain AI 챗봇 — 인덱싱 파이프라인

문서 파일 → 텍스트 추출 → 청킹 → 임베딩 → Qdrant upsert 전체 파이프라인.

핵심 설계:
- index_document(): 단일 파일 인덱싱 (재업로드 시 기존 포인트 삭제 후 재삽입)
- index_directory(): 디렉토리 내 지원 파일 일괄 인덱싱
- 인덱싱 진행 상태 로깅
- Qdrant sparse 벡터는 token_id(정수)를 인덱스로 사용하므로,
  bge-m3 lexical_weights의 문자열 토큰을 해싱하여 정수 인덱스로 변환
"""

from __future__ import annotations

import hashlib
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from qdrant_client.models import PointStruct, SparseVector

from app.config import get_settings
from app.core.embedding import EmbeddingProvider, EmbeddingResult, get_embedding_provider
from app.core.qdrant import QdrantManager, get_qdrant
from app.ingestion.chunker import Chunk, chunk_text
from app.ingestion.parser import ExtractResult, extract_text
from app.models.document import IndexResult, IndexingStatus

logger = logging.getLogger(__name__)

# 지원 파일 확장자
SUPPORTED_EXTENSIONS = {".pdf", ".epub", ".txt"}


# ---------------------------------------------------------------------------
# 토큰 해시 유틸리티
# ---------------------------------------------------------------------------

def _token_to_index(token: str) -> int:
    """문자열 토큰을 정수 인덱스로 변환 (Qdrant sparse vector 요구사항).

    bge-m3의 lexical_weights는 {토큰문자열: 가중치} 형태이지만,
    Qdrant의 SparseVector는 indices: list[int] 를 요구.
    해시 충돌 가능성은 있지만, sparse 검색 보조 용도이므로 실질적 영향 미미.

    Args:
        token: bge-m3에서 추출한 토큰 문자열

    Returns:
        음이 아닌 정수 인덱스
    """
    return abs(hash(token)) % (2**31)


def _sparse_dict_to_qdrant(sparse: dict[str, float]) -> SparseVector:
    """bge-m3 lexical_weights → Qdrant SparseVector 변환.

    Args:
        sparse: {토큰문자열: 가중치} 딕셔너리

    Returns:
        SparseVector: Qdrant 포인트 삽입용
    """
    if not sparse:
        return SparseVector(indices=[], values=[])

    indices = [_token_to_index(k) for k in sparse.keys()]
    values = list(sparse.values())

    return SparseVector(indices=indices, values=values)


# ---------------------------------------------------------------------------
# 인덱싱 상태 추적 (인메모리)
# ---------------------------------------------------------------------------

class IndexingTracker:
    """인메모리 인덱싱 상태 추적기.

    MVP에서는 인메모리 딕셔너리로 상태를 관리.
    P1에서 SQLite/Redis 등 영속 스토리지로 교체 가능.
    """

    def __init__(self) -> None:
        # document_id → 상태 정보 딕셔너리
        self._states: dict[str, dict] = {}

    def start(self, document_id: str, filename: str) -> None:
        """인덱싱 시작 상태 기록"""
        self._states[document_id] = {
            "document_id": document_id,
            "filename": filename,
            "status": IndexingStatus.INDEXING,
            "total_chunks": None,
            "error": None,
            "created_at": datetime.now(timezone.utc),
            "completed_at": None,
        }

    def complete(self, document_id: str, total_chunks: int) -> None:
        """인덱싱 완료 상태 기록"""
        if document_id in self._states:
            self._states[document_id].update({
                "status": IndexingStatus.COMPLETED,
                "total_chunks": total_chunks,
                "completed_at": datetime.now(timezone.utc),
            })

    def fail(self, document_id: str, error: str) -> None:
        """인덱싱 실패 상태 기록"""
        if document_id in self._states:
            self._states[document_id].update({
                "status": IndexingStatus.FAILED,
                "error": error,
            })

    def get(self, document_id: str) -> Optional[dict]:
        """특정 문서의 인덱싱 상태 조회"""
        return self._states.get(document_id)

    def list_all(self) -> list[dict]:
        """전체 문서 상태 목록 반환"""
        return list(self._states.values())

    def delete(self, document_id: str) -> bool:
        """문서 삭제

        Returns:
            bool: 삭제 성공 여부
        """
        if document_id in self._states:
            del self._states[document_id]
            return True
        return False


# 전역 인스턴스
_tracker: Optional[IndexingTracker] = None


def get_tracker() -> IndexingTracker:
    """IndexingTracker 싱글톤 반환"""
    global _tracker
    if _tracker is None:
        _tracker = IndexingTracker()
    return _tracker


# ---------------------------------------------------------------------------
# 핵심 인덱싱 로직
# ---------------------------------------------------------------------------

def index_document(
    file_path: str,
    embedding_provider: Optional[EmbeddingProvider] = None,
    qdrant: Optional[QdrantManager] = None,
    tracker: Optional[IndexingTracker] = None,
) -> IndexResult:
    """단일 문서 인덱싱.

    파이프라인: extract_text → chunk_text → encode → qdrant upsert

    동일 파일 재업로드 시:
    1. 기존 포인트를 source(파일명) 기준으로 삭제
    2. 새 포인트를 삽입

    Args:
        file_path: 인덱싱할 파일 경로
        embedding_provider: 임베딩 제공자 (None이면 기본 인스턴스)
        qdrant: Qdrant 관리자 (None이면 기본 인스턴스)
        tracker: 상태 추적기 (None이면 기본 인스턴스)

    Returns:
        IndexResult: 인덱싱 결과
    """
    path = Path(file_path)
    filename = path.name
    document_id = _generate_document_id(filename)
    _tracker = tracker or get_tracker()
    _qdrant = qdrant or get_qdrant()
    _embedding = embedding_provider or get_embedding_provider()

    _tracker.start(document_id, filename)
    logger.info("인덱싱 시작: %s (document_id=%s)", filename, document_id)

    try:
        # 1. 텍스트 추출
        logger.info("  [1/4] 텍스트 추출: %s", filename)
        extracted: ExtractResult = extract_text(file_path)

        # 2. 청킹
        settings = get_settings()
        logger.info("  [2/4] 청킹: chunk_size=%d, overlap=%d", settings.chunk_size, settings.chunk_overlap)
        chunks: list[Chunk] = chunk_text(
            extracted.text,
            extracted.metadata,
            chunk_size=settings.chunk_size,
            chunk_overlap=settings.chunk_overlap,
        )

        if not chunks:
            logger.warning("  청크가 생성되지 않음: %s", filename)
            _tracker.complete(document_id, 0)
            return IndexResult(
                document_id=document_id,
                filename=filename,
                status=IndexingStatus.COMPLETED,
                total_chunks=0,
            )

        logger.info("  청크 %d개 생성", len(chunks))

        # 3. 임베딩 (배치 처리)
        logger.info("  [3/4] 임베딩: %d 청크", len(chunks))
        texts = [c.text for c in chunks]
        embedding_result: EmbeddingResult = _embedding.encode(texts)

        # 4. Qdrant upsert
        logger.info("  [4/4] Qdrant upsert")

        # 컬렉션 존재 확인 (delete_by_source보다 먼저!)
        _qdrant.init_collection()

        # 동일 파일 기존 포인트 삭제 (재업로드)
        _qdrant.delete_by_source(filename)

        # 포인트 생성
        points = _build_points(
            document_id=document_id,
            chunks=chunks,
            embedding_result=embedding_result,
        )

        _qdrant.upsert_points(points)

        # 완료
        _tracker.complete(document_id, len(chunks))
        logger.info("인덱싱 완료: %s → %d 청크", filename, len(chunks))

        return IndexResult(
            document_id=document_id,
            filename=filename,
            status=IndexingStatus.COMPLETED,
            total_chunks=len(chunks),
        )

    except Exception as exc:
        error_msg = f"{type(exc).__name__}: {exc}"
        logger.error("인덱싱 실패: %s — %s", filename, error_msg, exc_info=True)
        _tracker.fail(document_id, error_msg)
        return IndexResult(
            document_id=document_id,
            filename=filename,
            status=IndexingStatus.FAILED,
            error=error_msg,
        )


def index_directory(
    dir_path: str,
    embedding_provider: Optional[EmbeddingProvider] = None,
    qdrant: Optional[QdrantManager] = None,
    tracker: Optional[IndexingTracker] = None,
) -> list[IndexResult]:
    """디렉토리 내 모든 지원 파일 일괄 인덱싱.

    Args:
        dir_path: 인덱싱할 디렉토리 경로
        embedding_provider: 임베딩 제공자
        qdrant: Qdrant 관리자
        tracker: 상태 추적기

    Returns:
        list[IndexResult]: 파일별 인덱싱 결과 목록
    """
    directory = Path(dir_path)

    if not directory.is_dir():
        raise ValueError(f"디렉토리가 아닙니다: {dir_path}")

    # 지원 파일 수집
    files = sorted(
        f for f in directory.rglob("*")
        if f.is_file() and f.suffix.lower() in SUPPORTED_EXTENSIONS
    )

    if not files:
        logger.info("지원 파일 없음: %s", dir_path)
        return []

    logger.info("디렉토리 인덱싱 시작: %s — %d개 파일", dir_path, len(files))

    results: list[IndexResult] = []
    for file_path in files:
        logger.info("  [%d/%d] %s", len(results) + 1, len(files), file_path.name)
        result = index_document(
            str(file_path),
            embedding_provider=embedding_provider,
            qdrant=qdrant,
            tracker=tracker,
        )
        results.append(result)

    # 요약 로깅
    success = sum(1 for r in results if r.status == IndexingStatus.COMPLETED)
    failed = sum(1 for r in results if r.status == IndexingStatus.FAILED)
    total_chunks = sum(r.total_chunks for r in results if r.status == IndexingStatus.COMPLETED)
    logger.info(
        "디렉토리 인덱싱 완료: 성공 %d, 실패 %d, 총 청크 %d",
        success, failed, total_chunks,
    )

    return results


# ---------------------------------------------------------------------------
# 내부 유틸리티
# ---------------------------------------------------------------------------

def _generate_document_id(filename: str) -> str:
    """파일명 기반 document_id 생성.

    같은 파일명은 같은 ID를 가져야 재업로드 시 상태를 조회 가능.
    hashlib.sha256을 사용하여 프로세스 재시작에도 동일한 ID 보장.
    (Python 내장 hash()는 세션마다 salt가 달라 결과가 불안정함)

    Args:
        filename: 파일명

    Returns:
        'doc-' 접두사가 붙은 식별자 문자열
    """
    # SHA-256 해시로 결정론적 ID 생성 (동일 파일명 = 동일 ID, 프로세스 무관)
    h = int(hashlib.sha256(filename.encode("utf-8")).hexdigest(), 16) % (10**10)
    return f"doc-{h}"


def _build_points(
    document_id: str,
    chunks: list[Chunk],
    embedding_result: EmbeddingResult,
) -> list[PointStruct]:
    """청크 + 임베딩 결과 → Qdrant PointStruct 리스트 변환.

    각 포인트:
    - id: UUID (청크별 고유)
    - vector: {dense: [...], sparse: SparseVector}
    - payload: 청크 메타데이터 + document_id

    Args:
        document_id: 문서 식별자
        chunks: 청크 리스트
        embedding_result: 임베딩 결과 (dense + sparse)

    Returns:
        list[PointStruct]: Qdrant 삽입용 포인트 리스트
    """
    points = []
    has_sparse = embedding_result.sparse is not None

    for idx, chunk in enumerate(chunks):
        dense_vec = embedding_result.dense[idx]

        # Vector 구성 — sparse가 없으면 dense만 포함 (API 임베딩 모드)
        if has_sparse and embedding_result.sparse:
            sparse_vec = _sparse_dict_to_qdrant(embedding_result.sparse[idx])
            vector = {"dense": dense_vec, "sparse": sparse_vec}
        else:
            vector = {"dense": dense_vec}

        # Payload 구성
        payload = {
            **chunk.metadata,
            "document_id": document_id,
            "text": chunk.text,
        }

        point = PointStruct(
            id=str(uuid.uuid4()),
            vector=vector,
            payload=payload,
        )
        points.append(point)

    return points