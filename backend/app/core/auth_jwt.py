"""mAI-Brain — JWT 인증 및 사용자 세션 관리

액세스 토큰: 쿠키(HttpOnly)에 저장, 24시간 유효
리프레시 토큰: 향후 구현 예정

FastAPI Depends()로 현재 사용자를 주입받을 수 있습니다.
"""

import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import Cookie, Depends, HTTPException, Request, status
from fastapi.security import APIKeyHeader
from jose import JWTError, jwt

from app.models.user import ROLE_ADMIN, get_user_store

logger = logging.getLogger(__name__)

# ── JWT 설정 ─────────────────────────────────────────────────────────────────

JWT_SECRET = os.environ.get("JWT_SECRET", "mai-brain-jwt-secret-change-in-production-2024")
JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_HOURS = 24
COOKIE_NAME = "mai_access_token"


def create_access_token(user_id: str, role: str, username: str) -> str:
    """JWT 액세스 토큰 생성."""
    expire = datetime.now(timezone.utc) + timedelta(hours=ACCESS_TOKEN_EXPIRE_HOURS)
    payload = {
        "sub": user_id,
        "role": role,
        "username": username,
        "exp": expire,
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def decode_access_token(token: str) -> Optional[dict]:
    """JWT 토큰 디코딩. 유효하지 않으면 None."""
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return payload
    except JWTError:
        return None


# ── FastAPI 의존성 ──────────────────────────────────────────────────────────

async def get_current_user(request: Request) -> dict:
    """현재 로그인한 사용자 반환. 미인증 시 401."""
    token = None

    # 1. 쿠키에서 토큰 확인
    token = request.cookies.get(COOKIE_NAME)

    # 2. Authorization 헤더에서 확인 (fallback)
    if not token:
        auth_header = request.headers.get("authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="로그인이 필요합니다.",
        )

    payload = decode_access_token(token)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="유효하지 않은 토큰입니다.",
        )

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="유효하지 않은 토큰입니다.",
        )

    store = get_user_store()
    user = store.get_user(user_id)

    if not user or not user.get("is_active"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="비활성화된 계정입니다.",
        )

    return user


async def get_current_user_optional(request: Request) -> Optional[dict]:
    """현재 사용자 반환 (로그인하지 않아도 None 반환)."""
    try:
        return await get_current_user(request)
    except HTTPException:
        return None


async def require_admin(current_user: dict = Depends(get_current_user)) -> dict:
    """관리자 권한 검증 의존성. 비관리자 시 403."""
    if current_user.get("role") != ROLE_ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="관리자 권한이 필요합니다.",
        )
    return current_user


def is_admin(user: Optional[dict]) -> bool:
    """사용자가 관리자인지 확인."""
    return user is not None and user.get("role") == ROLE_ADMIN