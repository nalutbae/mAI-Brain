"""mAI-Brain AI 챗봇 — 컨텍스트 관리 API

엔드포인트:
- POST /api/context/pin — 문서 고정
- DELETE /api/context/pin/{session_id}/{document_id} — 문서 고정 해제
- GET /api/context/pins/{session_id} — 고정 문서 목록 조회
- POST /api/context/summarize/{session_id} — 수동 요약 트리거
- GET /api/context/summary/{session_id} — 현재 요약 조회
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException

from app.core.context_manager import get_context_manager
from app.core.session_store import get_session_store
from app.models.context import (
    ContextSummary,
    PinnedDocument,
    PinDocumentRequest,
    SummarizeResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/pin", response_model=PinnedDocument)
async def pin_document(request: PinDocumentRequest):
    """문서를 세션에 고정.

    고정된 문서는 해당 세션의 컨텍스트에 항상 포함됩니다.
    """
    store = get_session_store()

    # 세션 존재 확인
    session = store.get_session(request.session_id)
    if session is None:
        raise HTTPException(
            status_code=404,
            detail=f"세션을 찾을 수 없습니다: {request.session_id}",
        )

    ctx = get_context_manager()
    result = ctx.pin_document(request.session_id, request.document_id)

    return PinnedDocument(
        session_id=result["session_id"],
        document_id=result["document_id"],
        pinned_at=result["pinned_at"],
        title=result.get("title"),
    )


@router.delete("/pin/{session_id}/{document_id}", response_model=dict)
async def unpin_document(session_id: str, document_id: str):
    """문서 고정 해제."""
    ctx = get_context_manager()
    success = ctx.unpin_document(session_id, document_id)

    if not success:
        raise HTTPException(
            status_code=404,
            detail=f"고정된 문서를 찾을 수 없습니다: session={session_id}, document={document_id}",
        )

    return {"message": "문서 고정이 해제되었습니다.", "session_id": session_id, "document_id": document_id}


@router.get("/pins/{session_id}", response_model=list[PinnedDocument])
async def get_pinned_documents(session_id: str):
    """세션에 고정된 문서 목록 조회."""
    store = get_session_store()

    session = store.get_session(session_id)
    if session is None:
        raise HTTPException(
            status_code=404,
            detail=f"세션을 찾을 수 없습니다: {session_id}",
        )

    ctx = get_context_manager()
    pinned = ctx.get_pinned_documents(session_id)

    return [
        PinnedDocument(
            session_id=p["session_id"],
            document_id=p["document_id"],
            pinned_at=p["pinned_at"],
            title=p.get("title"),
        )
        for p in pinned
    ]


@router.post("/summarize/{session_id}", response_model=SummarizeResponse)
async def summarize_history(session_id: str, max_recent: int = 10):
    """세션 대화 기록 수동 요약.

    이전 대화 기록이 임계값을 넘을 경우 LLM으로 요약을 생성합니다.

    Args:
        session_id: 세션 ID
        max_recent: 최근 유지할 메시지 수 (기본 10)
    """
    store = get_session_store()

    session = store.get_session(session_id)
    if session is None:
        raise HTTPException(
            status_code=404,
            detail=f"세션을 찾을 수 없습니다: {session_id}",
        )

    ctx = get_context_manager()
    summary = ctx.summarize_history(session_id, max_recent=max_recent)

    if summary is None:
        raise HTTPException(
            status_code=400,
            detail="요약할 대화 기록이 충분하지 않습니다. (메시지 수가 임계값 이하)",
        )

    # 요약 후 메시지 수 (요약 포함)
    message_count = store.get_message_count(session_id)

    return SummarizeResponse(
        session_id=session_id,
        summary=summary,
        message_count=message_count,
    )


@router.get("/summary/{session_id}", response_model=Optional[ContextSummary])
async def get_summary(session_id: str):
    """세션의 현재 요약 조회.

    요약이 없으면 null을 반환합니다.
    """
    store = get_session_store()

    session = store.get_session(session_id)
    if session is None:
        raise HTTPException(
            status_code=404,
            detail=f"세션을 찾을 수 없습니다: {session_id}",
        )

    ctx = get_context_manager()
    summary = ctx.get_summary(session_id)

    if summary is None:
        return None

    # 요약에 포함된 메시지 수 추정 (전체 메시지 수 - 최근 대화 수)
    total_count = store.get_message_count(session_id)

    # 요약 생성 시각은 messages 테이블에서 조회
    messages = store.get_messages(session_id, limit=10000)
    summary_created_at = ""
    for msg in messages:
        if msg["role"] == "system" and msg.get("mode") == "summary":
            summary_created_at = msg.get("created_at", "")
            break

    return ContextSummary(
        session_id=session_id,
        summary_text=summary,
        message_count=total_count,
        created_at=summary_created_at,
    )