"""mAI-Brain AI 챗봇 — 임베디드 위젯 API

엔드포인트:
- GET /api/widget: 위젯 설정 목록 조회
- POST /api/widget: 위젯 설정 생성
- GET /api/widget/{id}: 위젯 설정 조회
- PUT /api/widget/{id}: 위젯 설정 업데이트
- DELETE /api/widget/{id}: 위젯 설정 삭제
- POST /api/widget/{id}/token: 익명 세션 토큰 발급
- GET /api/widget/{id}/snippet: 삽입 스니펫 반환
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException

from app.core.widget import get_widget_store, get_token_issuer
from app.models.widget import (
    WidgetConfig,
    WidgetConfigCreate,
    WidgetConfigUpdate,
    WidgetConfigListResponse,
    WidgetTokenRequest,
    WidgetTokenResponse,
    WidgetSnippetResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter()


def _get_snippet_base_url() -> str:
    """스니펫 생성에 사용할 기본 URL."""
    import os
    return os.environ.get("WIDGET_BASE_URL", "http://localhost:3000")


# --------------------------------------------------------------------------- #
# 위젯 설정 CRUD
# --------------------------------------------------------------------------- #

@router.get("", response_model=WidgetConfigListResponse)
async def list_widgets():
    """모든 위젯 설정 목록을 반환합니다."""
    store = get_widget_store()
    widgets = store.list_widgets()
    return WidgetConfigListResponse(widgets=widgets, total=len(widgets))


@router.post("", response_model=WidgetConfig, status_code=201)
async def create_widget(config: WidgetConfigCreate):
    """새 위젯 설정을 생성합니다."""
    store = get_widget_store()
    return store.create_widget(config.model_dump(mode="json"))


@router.get("/{widget_id}", response_model=WidgetConfig)
async def get_widget(widget_id: str):
    """특정 위젯 설정을 반환합니다."""
    store = get_widget_store()
    widget = store.get_widget(widget_id)
    if widget is None:
        raise HTTPException(status_code=404, detail="위젯을 찾을 수 없습니다")
    return widget


@router.put("/{widget_id}", response_model=WidgetConfig)
async def update_widget(widget_id: str, updates: WidgetConfigUpdate):
    """위젯 설정을 업데이트합니다."""
    store = get_widget_store()
    updated = store.update_widget(widget_id, updates)
    if updated is None:
        raise HTTPException(status_code=404, detail="위젯을 찾을 수 없습니다")
    return updated


@router.delete("/{widget_id}")
async def delete_widget(widget_id: str):
    """위젯 설정을 삭제합니다."""
    store = get_widget_store()
    if not store.delete_widget(widget_id):
        raise HTTPException(status_code=404, detail="위젯을 찾을 수 없습니다")
    return {"message": "위젯이 삭제되었습니다", "widget_id": widget_id}


# --------------------------------------------------------------------------- #
# 익명 토큰
# --------------------------------------------------------------------------- #

@router.post("/{widget_id}/token", response_model=WidgetTokenResponse)
async def issue_widget_token(widget_id: str, request: WidgetTokenRequest):
    """익명 위젯 세션 토큰을 발급합니다.

    위젯이 삽입된 페이지에서 최초 로드 시 호출되어,
    익명 채팅 세션을 시작할 수 있는 토큰을 받습니다.
    """
    store = get_widget_store()
    widget = store.get_widget(widget_id)
    if widget is None:
        raise HTTPException(status_code=404, detail="위젯을 찾을 수 없습니다")

    if not widget.is_active:
        raise HTTPException(status_code=403, detail="이 위젯은 비활성화되어 있습니다")

    # origin 검증
    allowed = widget.allowed_origins
    if "*" not in allowed and request.origin not in allowed:
        raise HTTPException(
            status_code=403,
            detail=f"이 origin은 허용되지 않았습니다: {request.origin}",
        )

    issuer = get_token_issuer()
    try:
        token = issuer.issue_token(
            widget_id=widget_id,
            origin=request.origin,
        )
    except Exception as exc:
        logger.error("토큰 발급 오류: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"토큰 발급 중 오류가 발생했습니다: {exc}",
        ) from exc

    expires_at = datetime.now(timezone.utc).replace(
        hour=23, minute=59, second=59
    ).isoformat()  # 당일 자정

    return WidgetTokenResponse(
        token=token,
        widget_id=widget_id,
        expires_at=expires_at,
        config=widget,
    )


# --------------------------------------------------------------------------- #
# 삽입 스니펫
# --------------------------------------------------------------------------- #

@router.get("/{widget_id}/snippet", response_model=WidgetSnippetResponse)
async def get_widget_snippet(widget_id: str):
    """위젯 삽입용 HTML 스니펫을 반환합니다."""
    store = get_widget_store()
    widget = store.get_widget(widget_id)
    if widget is None:
        raise HTTPException(status_code=404, detail="위젯을 찾을 수 없습니다")

    base_url = _get_snippet_base_url()
    widget_url = f"{base_url}/widget"

    snippet = (
        f'<script src="{base_url}/widget.js"'
        f' data-widget-id="{widget_id}"'
        f' data-widget-url="{widget_url}"'
    )
    if widget.theme.primary_color != "#3B82F6":
        snippet += f' data-primary-color="{widget.theme.primary_color}"'
    if widget.position != "bottom-right":
        snippet += f' data-position="{widget.position}"'
    if widget.greeting != "안녕하세요! 무엇을 도와드릴까요?":
        snippet += f' data-greeting="{widget.greeting}"'
    snippet += "></script>"

    iframe_url = f"{base_url}/widget-frame.html?widget_id={widget_id}"

    return WidgetSnippetResponse(
        widget_id=widget_id,
        snippet=snippet,
        iframe_url=iframe_url,
    )
