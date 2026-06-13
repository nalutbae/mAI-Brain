"""mAI-Brain AI 챗봇 — 문서 관리 API

관리자용 문서 업로드, 인덱싱 상태 조회, 문서 목록 엔드포인트.

엔드포인트:
- POST /api/documents/upload: 파일 업로드 → 백그라운드 인덱싱
- POST /api/documents/upload-async: 파일 업로드 → 태스크 ID 즉시 반환 (비동기)
- GET /api/documents/status/{document_id}: 인덱싱 상태 조회 (기존 폴링)
- GET /api/documents/task/{task_id}: 태스크 상태 조회 (비동기)
- GET /api/documents/task/{task_id}/stream: SSE 실시간 진행률 스트리밍
- GET /api/documents: 인덱싱된 문서 목록
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException, UploadFile, Query
from fastapi.responses import StreamingResponse

from app.config import get_settings
from app.core.task_queue import TaskQueue, TaskStatus, get_task_queue
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

# 인덱싱 작업을 위한 전용 스레드풀 (이벤트 루프 블로킹 방지)
_indexing_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="indexing")


# --------------------------------------------------------------------------- #
# 파일 저장 경로
# --------------------------------------------------------------------------- #

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


# --------------------------------------------------------------------------- #
# 백그라운드 인덱싱 태스크 (기존 — ThreadPoolExecutor)
# --------------------------------------------------------------------------- #

def _run_indexing(file_path: str) -> None:
    """인덱싱 태스크 (스레드풀에서 실행).

    무거운 임베딩 모델 로딩과 Qdrant upsert를 수행하므로
    이벤트 루프 블로킹을 방지하기 위해 스레드풀에서 실행.

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


def _run_bulk_index(dir_path: str) -> None:
    """일괄 인덱싱 태스크 (스레드풀에서 실행)."""
    try:
        results = index_directory(dir_path)
        success = sum(1 for r in results if r.status == IndexingStatus.COMPLETED)
        failed = sum(1 for r in results if r.status == IndexingStatus.FAILED)
        logger.info("일괄 인덱싱 완료: 성공 %d, 실패 %d", success, failed)
    except Exception:
        logger.exception("일괄 인덱싱 예외")


# --------------------------------------------------------------------------- #
# 비동기 태스크 인덱싱 (BackgroundTasks + TaskQueue)
# --------------------------------------------------------------------------- #

async def _run_indexing_async(task_id: str, file_path: str, filename: str) -> None:
    """BackgroundTasks에서 실행하는 비동기 인덱싱.

    TaskQueue를 통해 진행률을 업데이트하고 SSE로 브로드캐스트합니다.
    실제 무거운 작업은 스레드풀에서 실행하여 이벤트 루프를 블로킹하지 않습니다.
    """
    task_queue = get_task_queue()

    try:
        # PENDING → PROCESSING
        task_queue.update_progress(task_id, 5, "인덱싱 준비 중...")

        loop = asyncio.get_running_loop()

        # 단계별 진행률 업데이트를 위한 콜백 래핑
        task_queue.update_progress(task_id, 10, "텍스트 추출 중...")

        def _do_index() -> dict:
            """스레드풀에서 실행할 인덱싱 작업"""
            try:
                result = index_document(file_path)
                return {
                    "document_id": result.document_id,
                    "filename": result.filename,
                    "status": result.status.value,
                    "total_chunks": result.total_chunks,
                    "error": result.error,
                }
            except Exception as e:
                return {
                    "document_id": "",
                    "filename": filename,
                    "status": "failed",
                    "total_chunks": 0,
                    "error": str(e),
                }

        # 스레드풀에서 실제 인덱싱 실행
        result = await loop.run_in_executor(_indexing_executor, _do_index)

        if result["status"] == "completed":
            task_queue.complete_task(task_id, result)
            logger.info("비동기 인덱싱 완료: %s (task_id=%s)", filename, task_id)
        else:
            task_queue.fail_task(task_id, result.get("error", "인덱싱 실패"))
            logger.error("비동기 인덱싱 실패: %s — %s (task_id=%s)", filename, result.get("error"), task_id)

    except Exception as exc:
        task_queue.fail_task(task_id, f"{type(exc).__name__}: {exc}")
        logger.exception("비동기 인덱싱 예외: %s (task_id=%s)", filename, task_id)


# --------------------------------------------------------------------------- #
# API 엔드포인트 — 기존 (후방 호환)
# --------------------------------------------------------------------------- #

@router.post("/upload-multiple")
async def upload_multiple_documents(
    files: list[UploadFile],
) -> list[DocumentUploadResponse]:
    """여러 파일 동시 업로드 → 각각 백그라운드 인덱싱.

    - multipart/form-data로 다중 파일 수신 (같은 필드명 'files')
    - 각 파일을 저장하고 스레드풀에서 인덱싱 시작
    - 각 파일별 {document_id, status: "indexing"} 응답
    """
    results: list[DocumentUploadResponse] = []
    upload_dir = _get_upload_dir()
    from app.ingestion.indexer import _generate_document_id

    loop = asyncio.get_running_loop()

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
        # 스레드풀에서 인덱싱 실행 (이벤트 루프 블로킹 방지)
        loop.run_in_executor(_indexing_executor, _run_indexing, str(saved_path))

        results.append(DocumentUploadResponse(
            document_id=document_id,
            filename=filename,
            status=IndexingStatus.INDEXING,
            message="파일이 업로드되었으며 인덱싱이 시작되었습니다.",
        ))

    return results


@router.post("/upload", response_model=DocumentUploadResponse)
async def upload_document(
    file: UploadFile,
) -> DocumentUploadResponse:
    """문서 업로드 → 스레드풀에서 인덱싱.

    - multipart/form-data로 파일 수신
    - 파일 저장 후 스레드풀에서 인덱싱
    - 즉시 {document_id, status: "indexing"} 응답
    - 클라이언트는 GET /status/{document_id} 로 상태 폴링

    ※ 후방 호환 엔드포인트 — 기존 폴링 방식 유지
    """
    # 파일 형식 검증
    filename = file.filename or "unknown"
    suffix = Path(filename).suffix.lower()

    if suffix not in SUPPORTED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"지원하지 않는 파일 형식: {suffix} (PDF, EPUB, TXT, DOCX, DOC, HWP, XLSX, XLS, CSV, MD 지원)",
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

    # 트래커에 상태 등록
    tracker = get_tracker()
    tracker.start(document_id, filename)

    # 스레드풀에서 인덱싱 실행 (이벤트 루프 블로킹 방지)
    loop = asyncio.get_running_loop()
    loop.run_in_executor(_indexing_executor, _run_indexing, str(saved_path))

    return DocumentUploadResponse(
        document_id=document_id,
        filename=filename,
        status=IndexingStatus.INDEXING,
        message="파일이 업로드되었으며 인덱싱이 시작되었습니다.",
    )


# --------------------------------------------------------------------------- #
# API 엔드포인트 — 비동기 태스크 (새로운)
# --------------------------------------------------------------------------- #

@router.post("/upload-async")
async def upload_document_async(
    background_tasks: BackgroundTasks,
    file: UploadFile,
) -> dict:
    """비동기 문서 업로드 → 태스크 ID 즉시 반환.

    - 파일 저장 후 BackgroundTasks로 인덱싱 예약
    - 즉시 {task_id, status: "pending"} 응답
    - 클라이언트는 GET /task/{task_id} 또는 GET /task/{task_id}/stream 으로 진행률 확인

    이 엔드포인트는 기존 /upload와 달리 응답 후 백그라운드에서 처리되며,
    SSE를 통해 실시간 진행률을 스트리밍할 수 있습니다.
    """
    # 파일 형식 검증
    filename = file.filename or "unknown"
    suffix = Path(filename).suffix.lower()

    if suffix not in SUPPORTED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"지원하지 않는 파일 형식: {suffix} (PDF, EPUB, TXT, DOCX, DOC, HWP, XLSX, XLS, CSV, MD 지원)",
        )

    if not file.size or file.size == 0:
        raise HTTPException(
            status_code=400,
            detail="빈 파일은 업로드할 수 없습니다.",
        )

    # 파일 저장
    upload_dir = _get_upload_dir()
    saved_path = _save_upload(file, upload_dir)

    # TaskQueue에 태스크 생성
    task_queue = get_task_queue()
    task = task_queue.add_task()

    # 기존 IndexingTracker에도 등록 (후방 호환)
    from app.ingestion.indexer import _generate_document_id
    document_id = _generate_document_id(filename)
    tracker = get_tracker()
    tracker.start(document_id, filename)

    # BackgroundTasks로 인덱싱 예약
    background_tasks.add_task(
        _run_indexing_async,
        task_id=task.id,
        file_path=str(saved_path),
        filename=filename,
    )

    return {
        "task_id": task.id,
        "document_id": document_id,
        "filename": filename,
        "status": "pending",
        "message": "파일이 업로드되었으며 인덱싱이 백그라운드에서 시작됩니다.",
    }


@router.post("/upload-multiple-async")
async def upload_multiple_documents_async(
    background_tasks: BackgroundTasks,
    files: list[UploadFile],
) -> list[dict]:
    """여러 파일 비동기 업로드 → 각각 태스크 ID 반환.

    - multipart/form-data로 다중 파일 수신 (필드명 'files')
    - 각 파일을 저장하고 BackgroundTasks로 인덱싱 예약
    - 각 파일별 {task_id, status: "pending"} 응답
    """
    results: list[dict] = []
    upload_dir = _get_upload_dir()
    from app.ingestion.indexer import _generate_document_id

    task_queue = get_task_queue()

    for file in files:
        filename = file.filename or "unknown"
        suffix = Path(filename).suffix.lower()

        if suffix not in SUPPORTED_EXTENSIONS:
            results.append({
                "task_id": None,
                "document_id": "",
                "filename": filename,
                "status": "failed",
                "message": f"지원하지 않는 파일 형식: {suffix}",
            })
            continue

        if not file.size or file.size == 0:
            results.append({
                "task_id": None,
                "document_id": "",
                "filename": filename,
                "status": "failed",
                "message": "빈 파일입니다.",
            })
            continue

        saved_path = _save_upload(file, upload_dir)

        # TaskQueue에 태스크 생성
        task = task_queue.add_task()
        document_id = _generate_document_id(filename)

        # 기존 IndexingTracker에도 등록
        tracker = get_tracker()
        tracker.start(document_id, filename)

        # BackgroundTasks로 인덱싱 예약
        background_tasks.add_task(
            _run_indexing_async,
            task_id=task.id,
            file_path=str(saved_path),
            filename=filename,
        )

        results.append({
            "task_id": task.id,
            "document_id": document_id,
            "filename": filename,
            "status": "pending",
            "message": "파일이 업로드되었으며 인덱싱이 백그라운드에서 시작됩니다.",
        })

    return results


@router.get("/task/{task_id}")
async def get_task_status(task_id: str) -> dict:
    """태스크 상태 조회 (폴링용).

    Args:
        task_id: upload-async에서 반환된 태스크 ID

    Returns:
        태스크 상태 정보 (status, progress, result, error)
    """
    task_queue = get_task_queue()
    task = task_queue.get_task(task_id)

    if task is None:
        raise HTTPException(
            status_code=404,
            detail=f"태스크를 찾을 수 없습니다: task_id={task_id}",
        )

    return task.to_dict()


@router.get("/task/{task_id}/stream")
async def stream_task_progress(task_id: str) -> StreamingResponse:
    """SSE 스트리밍 — 태스크 진행률 실시간 전송.

    Content-Type: text/event-stream 으로 진행률 이벤트를 스트리밍합니다.
    태스크가 완료/실패하면 [done] 이벤트를 전송하고 연결을 종료합니다.

    이벤트 형식:
        event: progress
        data: {"progress": 50, "message": "텍스트 추출 중..."}

        event: completed
        data: {"progress": 100, "result": {...}}

        event: failed
        data: {"progress": 30, "error": "에러 메시지"}

        event: done
        data: {}
    """
    task_queue = get_task_queue()
    task = task_queue.get_task(task_id)

    if task is None:
        raise HTTPException(
            status_code=404,
            detail=f"태스크를 찾을 수 없습니다: task_id={task_id}",
        )

    # 태스크의 이벤트 큐에 구독
    event_queue = task_queue.subscribe(task_id)
    if event_queue is None:
        raise HTTPException(
            status_code=404,
            detail=f"태스크 이벤트 구독 실패: task_id={task_id}",
        )

    async def event_generator():
        """SSE 이벤트 제너레이터"""
        try:
            # 이미 완료/실패된 태스크인 경우 즉시 완료 이벤트 전송
            if task.status in (TaskStatus.COMPLETED, TaskStatus.FAILED):
                event_type = "completed" if task.status == TaskStatus.COMPLETED else "failed"
                data = task.to_dict()
                yield f"event: {event_type}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
                yield f"event: done\ndata: {{}}\n\n"
                return

            # 이벤트 루프에서 큐 대기
            while True:
                try:
                    # 30초 타임아웃으로 이벤트 대기
                    event = await asyncio.wait_for(event_queue.get(), timeout=30.0)
                except asyncio.TimeoutError:
                    # 타임아웃 시 하트비트 전송 (연결 유지)
                    yield f"event: heartbeat\ndata: {{}}\n\n"
                    continue

                event_type = event.get("type", "progress")
                data = json.dumps(event, ensure_ascii=False)

                yield f"event: {event_type}\ndata: {data}\n\n"

                # 완료/실패 시 종료
                if event_type in ("completed", "failed"):
                    yield f"event: done\ndata: {{}}\n\n"
                    break

        except asyncio.CancelledError:
            # 클라이언트 연결 종료
            logger.info("SSE 연결 종료: task_id=%s", task_id)
        except Exception:
            logger.exception("SSE 스트리밍 오류: task_id=%s", task_id)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # nginx 버퍼링 방지
        },
    )


# --------------------------------------------------------------------------- #
# API 엔드포인트 — 기존 상태 조회 (후방 호환)
# --------------------------------------------------------------------------- #

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
    # 벡터 DB에서 실제 문서 목록 조회 (영속적 소스)
    db = get_vector_db()

    # 벡터 DB 연결 실패 시 빈 목록 대신 에러 명시
    if not db.collection_exists():
        return DocumentListResponse(documents=[], total=0)

    db_docs = db.list_documents()

    # IndexingTracker에서 진행 중/실패 상태 병합
    tracker = get_tracker()
    tracker_states = {s["document_id"]: s for s in tracker.list_all()}

    documents = []
    for doc in db_docs:
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

    # 트래커에만 있고 벡터 DB에 없는 문서 (인덱싱 진행 중/실패)
    db_ids = {doc["document_id"] for doc in db_docs}
    for doc_id, state in tracker_states.items():
        if doc_id not in db_ids and state.get("status") in (
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
async def reindex_all_documents() -> dict:
    """data/uploads/ 내 모든 지원 파일 일괄 재인덱싱.

    기존 Qdrant 포인트를 유지하면서 누락된 파일만 인덱싱하거나,
    force=True면 전체 재인덱싱.

    Query params:
        force: true면 기존 상태 무시하고 전체 재인덱싱 (기본 false)
    """
    from fastapi import Query

    upload_dir = _get_upload_dir()

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

    # 스레드풀에서 일괄 인덱싱 실행 (이벤트 루프 블로킹 방지)
    loop = asyncio.get_running_loop()
    loop.run_in_executor(_indexing_executor, _run_bulk_index, str(upload_dir))

    return {
        "message": f"{len(supported_files)}개 파일 일괄 인덱싱이 시작되었습니다.",
        "file_count": len(supported_files),
        "files": [f.name for f in sorted(supported_files)],
    }

@router.post("/{document_id}/reindex")
async def reindex_single_document(document_id: str):
    """단일 문서 재인덱싱.

    기존 Qdrant 포인트를 삭제하고 해당 파일을 다시 인덱싱합니다.
    """
    tracker = get_tracker()
    state = tracker.get(document_id)

    if state is None:
        raise HTTPException(
            status_code=404,
            detail=f"문서를 찾을 수 없습니다: document_id={document_id}",
        )

    filename = state.get("filename", "")
    upload_dir = _get_upload_dir()
    file_path = upload_dir / filename

    if not file_path.exists():
        raise HTTPException(
            status_code=404,
            detail=f"파일을 찾을 수 없습니다: {filename}",
        )

    # 기존 포인트 삭제 후 재인덱싱
    vdb = get_vector_db()
    vdb.delete_by_source(filename)

    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(
        _indexing_executor, index_document, str(file_path)
    )

    return {
        "message": f"문서 '{filename}' 재인덱싱이 완료되었습니다.",
        "document_id": document_id,
        "chunks": result.total_chunks if hasattr(result, "total_chunks") else 0,
    }


@router.get("/{document_id}")
async def get_document_detail(document_id: str):
    """문서 상세 정보 조회."""
    tracker = get_tracker()
    state = tracker.get(document_id)

    if state is None:
        raise HTTPException(
            status_code=404,
            detail=f"문서를 찾을 수 없습니다: document_id={document_id}",
        )

    return {"document_id": document_id, **state}


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


# --------------------------------------------------------------------------- #
# URL 웹페이지 인덱싱
# --------------------------------------------------------------------------- #

@router.post("/upload-url", response_model=DocumentUploadResponse)
async def upload_url(url: str = Query(..., description="인덱싱할 웹페이지 URL")):
    """URL 웹페이지를 다운로드하여 인덱싱합니다.

    웹페이지의 본문 텍스트를 추출하여 Qdrant에 저장합니다.
    readability 라이브러리로 광고/네비게이션을 제거하고 본문만 추출합니다.
    """
    # URL 형식 검증
    from urllib.parse import urlparse
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise HTTPException(
            status_code=400,
            detail=f"지원하지 않는 URL 스킴: {parsed.scheme} (http, https만 지원)",
        )

    # 웹페이지 텍스트 추출
    from app.ingestion.parser import extract_url
    try:
        result = extract_url(url)
    except ImportError as e:
        raise HTTPException(status_code=501, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=422,
            detail=f"URL에서 텍스트를 추출할 수 없습니다: {e}",
        )

    if not result.text.strip():
        raise HTTPException(
            status_code=422,
            detail=f"URL에서 텍스트를 추출할 수 없습니다: {url}",
        )

    # 텍스트를 임시 파일로 저장 후 인덱싱
    import tempfile
    import os

    # URL에서 파일명 생성
    domain = parsed.netloc.replace(".", "_").replace(":", "_")
    path_part = parsed.path.strip("/").replace("/", "_")[:50] or "index"
    safe_filename = f"{domain}_{path_part}.txt"

    upload_dir = _get_upload_dir()
    saved_path = upload_dir / safe_filename

    # 동일 파일이 있으면 덮어쓰기
    saved_path.write_text(result.text, encoding="utf-8")

    # document_id 생성
    from app.ingestion.indexer import _generate_document_id
    document_id = _generate_document_id(safe_filename)

    # 트래커에 상태 등록
    tracker = get_tracker()
    tracker.start(document_id, safe_filename)

    # 스레드풀에서 인덱싱 실행
    loop = asyncio.get_running_loop()
    loop.run_in_executor(_indexing_executor, _run_indexing, str(saved_path))

    return DocumentUploadResponse(
        document_id=document_id,
        filename=safe_filename,
        status=IndexingStatus.INDEXING,
        message=f"URL 웹페이지가 다운로드되었으며 인덱싱이 시작되었습니다.",
    )