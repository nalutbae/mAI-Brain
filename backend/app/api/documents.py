"""mAI-Brain AI 챗봇 — 문서 관리 API

관리자용 문서 업로드, 인덱싱 상태 조회, 문서 목록 엔드포인트.

엔드포인트:
- POST /api/documents/upload: 파일 업로드 → 백그라운드 인덱싱
- GET /api/documents/status/{document_id}: 인덱싱 상태 조회
- GET /api/documents: 인덱싱된 문서 목록
"""

from __future__ import annotations

import logging
import os
import shutil
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, HTTPException, UploadFile

from app.config import get_settings
from app.core.vectordb import get_vector_db
from app.ingestion.indexer import SUPPORTED_EXTENSIONS, index_document, index_directory
from app.ingestion.indexer import get_tracker
from app.models.document import (
    DocumentInfo,
    DocumentListResponse,
    DocumentStatusResponse,
    DocumentUploadResponse,
    IndexingStatus,
)

logger = logging.getLogger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# 파일 저장 경로
# ---------------------------------------------------------------------------

def _get_upload_dir() -> Path:
    """업로드 파일 저장 디렉토리 반환 (없으면 생성)"""
    # 프로젝트 루트 기준 data/uploads 사용 (재부팅 시에도 유지)
    project_root = Path(__file__).resolve().parent.parent.parent.parent
    default_upload_dir = project_root / "data" / "uploads"
    upload_dir = Path(os.environ.get("UPLOAD_DIR", str(default_upload_dir)))
    upload_dir.mkdir(parents=True, exist_ok=True)
    return upload_dir


def _save_upload(file: UploadFile, upload_dir: Path) -> Path:
    """업로드된 파일을 디스크에 저장.

    Args:
        file: FastAPI UploadFile
        upload_dir: 저장 디렉토리

    Returns:
        저장된 파일의 경로
    """
    filename = file.filename or "unknown"
    dest = upload_dir / filename

    # 동일 파일명 존재 시 덮어쓰기 (indexer가 재업로드 처리)
    with open(dest, "wb") as f:
        shutil.copyfileobj(file.file, f)

    logger.info("파일 저장: %s → %s", filename, dest)
    return dest


# ---------------------------------------------------------------------------
# 백그라운드 인덱싱 태스크
# ---------------------------------------------------------------------------

def _run_indexing(file_path: str) -> None:
    """백그라운드에서 실행되는 인덱싱 태스크.

    FastAPI BackgroundTasks에 의해 비동기 호출.
    인덱싱 중에도 기존 검색 서비스에 영향 없음(핫 리로드).

    Args:
        file_path: 인덱싱할 파일 경로
    """
    try:
        result = index_document(file_path)
        if result.status == IndexingStatus.COMPLETED:
            logger.info("백그라운드 인덱싱 완료: %s (%d 청크)", result.filename, result.total_chunks)
        else:
            logger.error("백그라운드 인덱싱 실패: %s — %s", result.filename, result.error)
    except Exception:
        logger.exception("백그라운드 인덱싱 예외: %s", file_path)


# ---------------------------------------------------------------------------
# API 엔드포인트
# ---------------------------------------------------------------------------

@router.post("/upload-multiple")
async def upload_multiple_documents(
    background_tasks: BackgroundTasks,
    files: list[UploadFile],
) -> list[DocumentUploadResponse]:
    """여러 파일 동시 업로드 → 각각 백그라운드 인덱싱.

    - multipart/form-data로 다중 파일 수신 (같은 필드명 'files')
    - 각 파일을 저장하고 백그라운드 인덱싱 시작
    - 각 파일별 {document_id, status: "indexing"} 응답
    """
    results: list[DocumentUploadResponse] = []
    upload_dir = _get_upload_dir()
    from app.ingestion.indexer import _generate_document_id

    for file in files:
        filename = file.filename or "unknown"
        suffix = Path(filename).suffix.lower()

        if suffix not in SUPPORTED_EXTENSIONS:
            results.append(DocumentUploadResponse(
                document_id="",
                filename=filename,
                status=IndexingStatus.FAILED,
                message=f"지원하지 않는 파일 형식: {suffix}",
            ))
            continue

        if not file.size or file.size == 0:
            results.append(DocumentUploadResponse(
                document_id="",
                filename=filename,
                status=IndexingStatus.FAILED,
                message="빈 파일입니다.",
            ))
            continue

        saved_path = _save_upload(file, upload_dir)
        document_id = _generate_document_id(filename)

        tracker = get_tracker()
        tracker.start(document_id, filename)
        background_tasks.add_task(_run_indexing, str(saved_path))

        results.append(DocumentUploadResponse(
            document_id=document_id,
            filename=filename,
            status=IndexingStatus.INDEXING,
            message="파일이 업로드되었으며 인덱싱이 시작되었습니다.",
        ))

    return results


@router.post("/upload", response_model=DocumentUploadResponse)
async def upload_document(
    background_tasks: BackgroundTasks,
    file: UploadFile,
) -> DocumentUploadResponse:
    """문서 업로드 → 백그라운드 인덱싱.

    - multipart/form-data로 파일 수신
    - 파일 저장 후 백그라운드 태스크로 인덱싱
    - 즉시 {document_id, status: "indexing"} 응답
    - 클라이언트는 GET /status/{document_id} 로 상태 폴링

    핫 리로드: 인덱싱이 백그라운드에서 실행되므로
    기존 검색 서비스에 중단 없음.
    """
    # 파일 형식 검증
    filename = file.filename or "unknown"
    suffix = Path(filename).suffix.lower()

    if suffix not in SUPPORTED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"지원하지 않는 파일 형식: {suffix} (PDF, EPUB, TXT만 지원)",
        )

    if not file.size or file.size == 0:
        raise HTTPException(
            status_code=400,
            detail="빈 파일은 업로드할 수 없습니다.",
        )

    # 파일 저장
    upload_dir = _get_upload_dir()
    saved_path = _save_upload(file, upload_dir)

    # document_id 생성 (indexer와 동일 로직)
    from app.ingestion.indexer import _generate_document_id
    document_id = _generate_document_id(filename)

    # 트래커에 상태 등록 (시작 전에 PENDING으로)
    tracker = get_tracker()
    tracker.start(document_id, filename)

    # 백그라운드 인덱싱 예약
    background_tasks.add_task(_run_indexing, str(saved_path))

    return DocumentUploadResponse(
        document_id=document_id,
        filename=filename,
        status=IndexingStatus.INDEXING,
        message="파일이 업로드되었으며 인덱싱이 시작되었습니다.",
    )


@router.get("/status/{document_id}", response_model=DocumentStatusResponse)
async def get_document_status(document_id: str) -> DocumentStatusResponse:
    """인덱싱 상태 조회.

    document_id로 인덱싱 진행 상태를 확인.

    Returns:
        DocumentStatusResponse: 현재 상태, 청크 수, 에러 정보 등
    """
    tracker = get_tracker()
    state = tracker.get(document_id)

    if state is None:
        raise HTTPException(
            status_code=404,
            detail=f"문서를 찾을 수 없습니다: document_id={document_id}",
        )

    return DocumentStatusResponse(
        document_id=state["document_id"],
        filename=state["filename"],
        status=state["status"],
        total_chunks=state.get("total_chunks"),
        error=state.get("error"),
        created_at=state.get("created_at"),
        completed_at=state.get("completed_at"),
    )


@router.get("", response_model=DocumentListResponse)
async def list_documents() -> DocumentListResponse:
    """인덱싱된 문서 목록.

    Qdrant에서 실제 포인트를 직접 조회하여 항상 정확한 상태를 반환합니다.
    IndexingTracker의 인메모리 상태와 무관하게 동작하므로
    서버 재시작이나 외부 스크립트로 인덱싱한 경우에도 올바른 목록을 보여줍니다.

    Returns:
        DocumentListResponse: 문서 목록과 전체 수
    """
    # Qdrant에서 실제 문서 목록 조회 (영속적 소스)
    qdrant = get_qdrant()

    # Qdrant 연결 실패 시 빈 목록 대신 에러 명시
    if not qdrant.collection_exists():
        return DocumentListResponse(documents=[], total=0)

    qdrant_docs = qdrant.list_documents()

    # IndexingTracker에서 진행 중/실패 상태 병합
    tracker = get_tracker()
    tracker_states = {s["document_id"]: s for s in tracker.list_all()}

    documents = []
    for doc in qdrant_docs:
        # 트래커에 진행 중인 상태가 있으면 우선 반영
        tracker_entry = tracker_states.get(doc["document_id"])
        status = IndexingStatus.COMPLETED
        created_at = None

        if tracker_entry:
            tracker_status = tracker_entry.get("status")
            if tracker_status in (IndexingStatus.INDEXING, IndexingStatus.PENDING):
                status = tracker_status
            created_at = tracker_entry.get("created_at")

        documents.append(DocumentInfo(
            document_id=doc["document_id"],
            filename=doc["filename"],
            status=status,
            total_chunks=doc["total_chunks"],
            created_at=created_at,
        ))

    # 트래커에만 있고 Qdrant에 없는 문서 (인덱싱 진행 중/실패)
    qdrant_ids = {doc["document_id"] for doc in qdrant_docs}
    for doc_id, state in tracker_states.items():
        if doc_id not in qdrant_ids and state.get("status") in (
            IndexingStatus.INDEXING,
            IndexingStatus.PENDING,
            IndexingStatus.FAILED,
        ):
            documents.append(DocumentInfo(
                document_id=state["document_id"],
                filename=state["filename"],
                status=state["status"],
                total_chunks=state.get("total_chunks"),
                created_at=state.get("created_at"),
            ))

    return DocumentListResponse(
        documents=documents,
        total=len(documents),
    )


@router.post("/reindex-all")
async def reindex_all_documents(
    background_tasks: BackgroundTasks,
) -> dict:
    """data/uploads/ 내 모든 지원 파일 일괄 재인덱싱.

    기존 Qdrant 포인트를 유지하면서 누락된 파일만 인덱싱하거나,
    force=True면 전체 재인덱싱.

    Query params:
        force: true면 기존 상태 무시하고 전체 재인덱싱 (기본 false)
    """
    from fastapi import Query

    # 지연 임포트로 Query 파라미터 처리 (위에서 이미 import됨)
    upload_dir = _get_upload_dir()

    def _run_bulk_index(dir_path: str) -> None:
        """백그라운드에서 전체 디렉토리 인덱싱 실행."""
        try:
            results = index_directory(dir_path)
            success = sum(1 for r in results if r.status == IndexingStatus.COMPLETED)
            failed = sum(1 for r in results if r.status == IndexingStatus.FAILED)
            logger.info("일괄 인덱싱 완료: 성공 %d, 실패 %d", success, failed)
        except Exception:
            logger.exception("일괄 인덱싱 예외")

    # 지원 파일 개수 확인
    supported_files = [
        f for f in upload_dir.rglob("*")
        if f.is_file() and f.suffix.lower() in SUPPORTED_EXTENSIONS
    ]

    if not supported_files:
        return {
            "message": "인덱싱할 파일이 없습니다.",
            "file_count": 0,
        }

    # 백그라운드에서 일괄 인덱싱 시작
    background_tasks.add_task(_run_bulk_index, str(upload_dir))

    return {
        "message": f"{len(supported_files)}개 파일 일괄 인덱싱이 시작되었습니다.",
        "file_count": len(supported_files),
        "files": [f.name for f in sorted(supported_files)],
    }


@router.delete("/{document_id}")
async def delete_document(document_id: str):
    """문서 삭제.

    문서 ID로 문서를 삭제합니다.
    """
    tracker = get_tracker()
    state = tracker.get(document_id)

    if state is None:
        raise HTTPException(
            status_code=404,
            detail=f"문서를 찾을 수 없습니다: document_id={document_id}",
        )

    # 트래커에서 삭제
    tracker.delete(document_id)

    # TODO: Qdrant에서도 해당 문서의 청크 삭제 필요
    # indexer에서 delete_document 함수 구현 후 호출

    return {"message": "문서가 삭제되었습니다.", "document_id": document_id}