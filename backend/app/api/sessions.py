"""mAI-Brain AI 챗봇 — 세션 관리 API

엔드포인트:
- POST /api/sessions: 새 세션 생성
- GET /api/sessions: 세션 목록 (최근순)
- GET /api/sessions/{session_id}: 세션 상세 + 대화 내역
- DELETE /api/sessions/{session_id}: 세션 삭제
- GET /api/sessions/{session_id}/export: 세션 대화 내보내기 (Markdown/JSON/CSV)
- GET /api/sessions/export: 전체 세션 목록 내보내기 (Markdown/JSON/CSV)
"""

from __future__ import annotations

import csv
import io
import json
import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse

from app.core.session_store import get_session_store
from app.models.session import (
    SessionCreateRequest,
    SessionDetailResponse,
    SessionListResponse,
    SessionResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter()


# --------------------------------------------------------------------------- #
# 세션 CRUD
# --------------------------------------------------------------------------- #

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


# --------------------------------------------------------------------------- #
# 세션 내보내기 — /export/all 을 /{session_id}보다 먼저 등록해야 함
# (FastAPI가 경로 변수로 "export"를 잡지 않도록)
# --------------------------------------------------------------------------- #

@router.get("/export/all")
async def export_all_sessions(
    format: str = Query(
        default="markdown",
        description="내보내기 형식: markdown, json, csv",
        pattern="^(markdown|json|csv)$",
    ),
):
    """전체 세션 대화 내보내기 (Markdown/JSON/CSV).

    모든 세션의 대화 내역을 선택한 형식으로 다운로드합니다.
    """
    store = get_session_store()

    # 전체 세션 조회 (최대 200개)
    sessions = store.list_sessions(limit=200, offset=0)

    # 각 세션의 메시지 조회
    sessions_with_messages = []
    for s in sessions:
        messages = store.get_messages(s["session_id"], limit=10000)
        sessions_with_messages.append({
            "session": s,
            "messages": messages,
        })

    if format == "markdown":
        content = _all_sessions_to_markdown(sessions_with_messages)
        filename = "conversations-all.md"
        media_type = "text/markdown; charset=utf-8"
    elif format == "json":
        content = _all_sessions_to_json(sessions_with_messages)
        filename = "conversations-all.json"
        media_type = "application/json; charset=utf-8"
    elif format == "csv":
        content = _all_sessions_to_csv(sessions_with_messages)
        filename = "conversations-all.csv"
        media_type = "text/csv; charset=utf-8"
    else:
        raise HTTPException(
            status_code=400,
            detail=f"지원하지 않는 형식입니다: {format} (markdown, json, csv 지원)",
        )

    return StreamingResponse(
        iter([content.encode("utf-8")]),
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# --------------------------------------------------------------------------- #
# 세션 CRUD (상세/삭제)
# --------------------------------------------------------------------------- #

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


# --------------------------------------------------------------------------- #
# 단일 세션 내보내기
# --------------------------------------------------------------------------- #

def _session_to_markdown(session: dict, messages: list[dict]) -> str:
    """세션 대화를 Markdown 형식으로 변환."""
    lines = [
        f"# {session['title']}",
        "",
        f"- **세션 ID**: {session['session_id']}",
        f"- **생성일**: {session['created_at']}",
        f"- **수정일**: {session['updated_at']}",
        f"- **메시지 수**: {len(messages)}",
        "",
        "---",
        "",
    ]

    for i, msg in enumerate(messages, 1):
        role_label = {"user": "사용자", "assistant": "AI", "system": "시스템"}.get(
            msg["role"], msg["role"]
        )
        mode_str = f" (`{msg.get('mode')}`)" if msg.get("mode") else ""
        lines.append(f"## [{i}] {role_label}{mode_str}")
        lines.append("")
        lines.append(msg["content"])
        lines.append("")

        # 출처 정보
        sources = msg.get("sources")
        if sources:
            lines.append("**출처**:")
            for s in sources:
                source_name = s.get("source", "알 수 없음")
                score = s.get("score")
                score_str = f" (점수: {score:.3f})" if score else ""
                lines.append(f"- {source_name}{score_str}")
            lines.append("")

        lines.append(f"_{msg.get('created_at', '')}_")
        lines.append("")

    return "\n".join(lines)


def _session_to_json(session: dict, messages: list[dict]) -> str:
    """세션 대화를 JSON 형식으로 변환."""
    data = {
        "session": {
            "session_id": session["session_id"],
            "title": session["title"],
            "created_at": session["created_at"],
            "updated_at": session["updated_at"],
        },
        "messages": messages,
    }
    return json.dumps(data, ensure_ascii=False, indent=2)


def _session_to_csv(messages: list[dict]) -> str:
    """세션 대화를 CSV 형식으로 변환."""
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["번호", "역할", "모드", "내용", "출처", "시간"])

    for i, msg in enumerate(messages, 1):
        sources_str = ""
        if msg.get("sources"):
            source_parts = []
            for s in msg["sources"]:
                name = s.get("source", "")
                score = s.get("score", "")
                source_parts.append(f"{name}" + (f"({score})" if score else ""))
            sources_str = "; ".join(source_parts)

        writer.writerow([
            i,
            msg.get("role", ""),
            msg.get("mode", ""),
            msg.get("content", ""),
            sources_str,
            msg.get("created_at", ""),
        ])

    return output.getvalue()


@router.get("/{session_id}/export")
async def export_session(
    session_id: str,
    format: str = Query(
        default="markdown",
        description="내보내기 형식: markdown, json, csv",
        pattern="^(markdown|json|csv)$",
    ),
):
    """세션 대화 내보내기 (Markdown/JSON/CSV).

    지정된 세션의 전체 대화 내역을 선택한 형식으로 다운로드합니다.
    """
    store = get_session_store()

    session = store.get_session(session_id)
    if session is None:
        raise HTTPException(
            status_code=404,
            detail=f"세션을 찾을 수 없습니다: {session_id}",
        )

    messages = store.get_messages(session_id, limit=10000)

    if format == "markdown":
        content = _session_to_markdown(session, messages)
        filename = f"session-{session_id[:8]}.md"
        media_type = "text/markdown; charset=utf-8"
    elif format == "json":
        content = _session_to_json(session, messages)
        filename = f"session-{session_id[:8]}.json"
        media_type = "application/json; charset=utf-8"
    elif format == "csv":
        content = _session_to_csv(messages)
        filename = f"session-{session_id[:8]}.csv"
        media_type = "text/csv; charset=utf-8"
    else:
        raise HTTPException(
            status_code=400,
            detail=f"지원하지 않는 형식입니다: {format} (markdown, json, csv 지원)",
        )

    return StreamingResponse(
        iter([content.encode("utf-8")]),
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# --------------------------------------------------------------------------- #
# 전체 세션 내보내기
# --------------------------------------------------------------------------- #

def _all_sessions_to_markdown(sessions_with_messages: list[dict]) -> str:
    """전체 세션 목록을 Markdown 형식으로 변환."""
    lines = ["# 대화 내역 전체 내보내기", ""]

    # 요약 테이블
    lines.append("## 세션 목록")
    lines.append("")
    lines.append("| # | 제목 | 메시지 수 | 생성일 | 수정일 |")
    lines.append("|---|------|----------|--------|--------|")
    for i, item in enumerate(sessions_with_messages, 1):
        s = item["session"]
        msg_count = len(item["messages"])
        lines.append(
            f"| {i} | {s['title']} | {msg_count} | {s['created_at'][:10]} | {s['updated_at'][:10]} |"
        )
    lines.append("")

    # 각 세션 대화
    for item in sessions_with_messages:
        lines.append("---")
        lines.append("")
        lines.extend(_session_to_markdown(item["session"], item["messages"]).splitlines())
        lines.append("")

    return "\n".join(lines)


def _all_sessions_to_json(sessions_with_messages: list[dict]) -> str:
    """전체 세션 목록을 JSON 형식으로 변환."""
    data = {
        "exported_at": datetime.utcnow().isoformat(),
        "total_sessions": len(sessions_with_messages),
        "sessions": [
            {
                "session": {
                    "session_id": item["session"]["session_id"],
                    "title": item["session"]["title"],
                    "created_at": item["session"]["created_at"],
                    "updated_at": item["session"]["updated_at"],
                },
                "messages": item["messages"],
            }
            for item in sessions_with_messages
        ],
    }
    return json.dumps(data, ensure_ascii=False, indent=2)


def _all_sessions_to_csv(sessions_with_messages: list[dict]) -> str:
    """전체 세션 목록을 CSV 형식으로 변환 (모든 대화를 하나의 테이블로)."""
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["세션ID", "세션제목", "번호", "역할", "모드", "내용", "출처", "시간"])

    for item in sessions_with_messages:
        s = item["session"]
        for i, msg in enumerate(item["messages"], 1):
            sources_str = ""
            if msg.get("sources"):
                source_parts = []
                for src in msg["sources"]:
                    name = src.get("source", "")
                    score = src.get("score", "")
                    source_parts.append(f"{name}" + (f"({score})" if score else ""))
                sources_str = "; ".join(source_parts)

            writer.writerow([
                s["session_id"][:8],
                s["title"],
                i,
                msg.get("role", ""),
                msg.get("mode", ""),
                msg.get("content", ""),
                sources_str,
                msg.get("created_at", ""),
            ])

    return output.getvalue()