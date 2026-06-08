"""mAI-Brain AI 챗봇 — 세션 관리 API

엔드포인트:
- POST /api/sessions: 새 세션 생성
- GET /api/sessions: 세션 목록 (최근순)
- GET /api/sessions/{session_id}: 세션 상세 + 대화 내역
- DELETE /api/sessions/{session_id}: 세션 삭제
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from app.core.session_store import get_session_store
from app.models.session import (
    SessionCreateRequest,
    SessionDetailResponse,
    SessionListResponse,
    SessionResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("", response_model=SessionResponse)
async def create_session(request: SessionCreateRequest):
    """새 대화 세션 생성.

    세션 ID가 자동으로 발급되며, 이후 채팅 요청 시 session_id를 전달하면
    이전 대화 컨텍스트가 유지됩니다.
    """
    store = get_session_store()
    session = store.create_session(title=request.title)

    return SessionResponse(
        session_id=session["session_id"],
        title=session["title"],
        created_at=session["created_at"],
        updated_at=session["updated_at"],
        message_count=0,
    )


@router.get("", response_model=SessionListResponse)
async def list_sessions(
    limit: int = Query(default=50, ge=1, le=200, description="페이지 크기"),
    offset: int = Query(default=0, ge=0, description="오프셋"),
):
    """세션 목록 조회 (최근 업데이트순)."""
    store = get_session_store()
    sessions = store.list_sessions(limit=limit, offset=offset)

    session_responses = []
    for s in sessions:
        msg_count = store.get_message_count(s["session_id"])
        session_responses.append(SessionResponse(
            session_id=s["session_id"],
            title=s["title"],
            created_at=s["created_at"],
            updated_at=s["updated_at"],
            message_count=msg_count,
        ))

    return SessionListResponse(
        sessions=session_responses,
        total=len(session_responses),
    )


@router.get("/{session_id}", response_model=SessionDetailResponse)
async def get_session_detail(session_id: str):
    """세션 상세 조회 (대화 내역 포함)."""
    store = get_session_store()

    # 세션 존재 확인
    session = store.get_session(session_id)
    if session is None:
        raise HTTPException(
            status_code=404,
            detail=f"세션을 찾을 수 없습니다: {session_id}",
        )

    # 대화 메시지 조회
    messages = store.get_messages(session_id)

    return SessionDetailResponse(
        session_id=session["session_id"],
        title=session["title"],
        created_at=session["created_at"],
        updated_at=session["updated_at"],
        messages=messages,
    )


@router.delete("/{session_id}")
async def delete_session(session_id: str):
    """세션 및 대화 기록 삭제."""
    store = get_session_store()

    deleted = store.delete_session(session_id)
    if not deleted:
        raise HTTPException(
            status_code=404,
            detail=f"세션을 찾을 수 없습니다: {session_id}",
        )

    return {"message": "세션이 삭제되었습니다.", "session_id": session_id}