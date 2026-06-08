"""mAI-Brain — 위젯 익명 토큰 인증 의존성

FastAPI Depends로 위젯 토큰을 검증하고 workspace_id를 주입합니다.
위젯이 아닌 일반 API 호출에는 영향을 주지 않습니다.
"""

import hashlib
import hmac
import logging
import os
import time
from typing import Optional

from fastapi import Depends, Header, HTTPException, Request

logger = logging.getLogger(__name__)

_WIDGET_SECRET = os.environ.get("MAI_BRAIN_WIDGET_SECRET", "mai-brain-widget-secret-change-me")


def verify_widget_token(token: str) -> Optional[dict]:
    """위젯 토큰을 검증하고 payload를 반환.

    Returns:
        {"widget_id": str, "expires_at": int} 또는 None
    """
    try:
        parts = token.split(":")
        if len(parts) != 3:
            return None
        widget_id, expires_str, sig = parts
        expires_at = int(expires_str)
        if expires_at < int(time.time()):
            return None
        msg = f"{widget_id}:{expires_str}"
        expected_sig = hmac.new(
            _WIDGET_SECRET.encode(),
            msg.encode(),
            hashlib.sha256,
        ).hexdigest()
        if not hmac.compare_digest(sig, expected_sig):
            return None
        return {"widget_id": widget_id, "expires_at": expires_at}
    except (ValueError, IndexError):
        return None


def get_widget_workspace(
    request: Request,
    authorization: Optional[str] = Header(default=None),
) -> Optional[str]:
    """위젯 토큰에서 workspace_id를 추출하는 FastAPI 의존성.

    Authorization: Bearer <token> 헤더가 있으면 검증 후
    해당 위젯의 workspace_id를 반환.
    헤더가 없으면 None 반환 (일반 API 호출).

    위젯 토큰이 유효하지 않으면 401 에러 발생.
    """
    if not authorization:
        return None

    if not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=401,
            detail="잘못된 인증 헤더 형식",
        )

    token = authorization[7:].strip()
    payload = verify_widget_token(token)
    if payload is None:
        raise HTTPException(
            status_code=401,
            detail="유효하지 않거나 만료된 위젯 토큰",
        )

    # 위젯 설정에서 workspace_id 조회
    from app.core.widget_store import get_widget_store
    store = get_widget_store()
    widget = store.get_widget(payload["widget_id"])
    if not widget or not widget.is_active:
        raise HTTPException(
            status_code=401,
            detail="비활성화되거나 존재하지 않는 위젯",
        )

    return widget.workspace_id