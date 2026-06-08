"""mAI-Brain AI 챗봇 — 임베디드 위젯 API

엔드포인트:
- GET /api/widget/settings: 위젯 설정 조회
- PUT /api/widget/settings: 위젯 설정 업데이트
- POST /api/widget/token: 익명 세션 토큰 발급
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException

from app.core.widget import get_widget_store, get_token_issuer
from app.models.widget import (
    WidgetSettings,
    WidgetSettingsUpdate,
    WidgetTokenRequest,
    WidgetTokenResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter()


# --------------------------------------------------------------------------- #
# 위젯 설정
# --------------------------------------------------------------------------- #

@router.get("/settings", response_model=WidgetSettings)
async def get_widget_settings():
    """현재 위젯 설정을 반환합니다.

    외부 웹사이트에서 위젯 초기화 시 호출됩니다.
    """
    store = get_widget_store()
    return store.get_settings()


@router.put("/settings", response_model=WidgetSettings)
async def update_widget_settings(updates: WidgetSettingsUpdate):
    """위젯 설정을 업데이트합니다.

    None이 아닌 필드만 부분 업데이트됩니다.
    관리자 페이지에서 위젯 커스터마이징 시 사용됩니다.
    """
    store = get_widget_store()
    try:
        return store.update_settings(updates.model_dump(exclude_none=True))
    except Exception as exc:
        logger.error("위젯 설정 업데이트 오류: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"설정 업데이트 중 오류가 발생했습니다: {exc}",
        ) from exc


# --------------------------------------------------------------------------- #
# 익명 토큰
# --------------------------------------------------------------------------- #

@router.post("/token", response_model=WidgetTokenResponse)
async def issue_widget_token(request: WidgetTokenRequest):
    """익명 위젯 세션 토큰을 발급합니다.

    위젯이 삽입된 페이지에서 최초 로드 시 호출되어,
    익명 채팅 세션을 시작할 수 있는 토큰을 받습니다.

    토큰은 24시간 유효하며, 채팅 API 호출 시
    Authorization: Bearer <token> 헤더로 전달합니다.
    """
    store = get_widget_store()
    settings = store.get_settings()

    # origin 검증
    allowed = settings.allowed_origins
    if "*" not in allowed and request.origin not in allowed:
        raise HTTPException(
            status_code=403,
            detail=f"이 origin은 허용되지 않았습니다: {request.origin}",
        )

    issuer = get_token_issuer()
    workspace_id = request.workspace_id or settings.workspace_id

    try:
        token = issuer.issue_token(
            origin=request.origin,
            workspace_id=workspace_id,
        )
    except Exception as exc:
        logger.error("토큰 발급 오류: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"토큰 발급 중 오류가 발생했습니다: {exc}",
        ) from exc

    return WidgetTokenResponse(
        token=token,
        expires_in=86400,
        settings=settings,
    )
