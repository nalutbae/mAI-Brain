"""mAI-Brain — 인증 API 라우터

회원가입, 로그인, 로그아웃, 내 프로필 조회/수정.
"""

import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Response, HTTPException, status
from pydantic import BaseModel

from app.models.user import (
    UserCreate, UserLogin, UserResponse, get_user_store,
)
from app.core.auth_jwt import (
    create_access_token, COOKIE_NAME, ACCESS_TOKEN_EXPIRE_HOURS,
    get_current_user,
)

logger = logging.getLogger(__name__)

router = APIRouter()


def _user_to_response(user: dict) -> UserResponse:
    """DB 행을 응답 모델로 변환 (password_hash 제외)."""
    return UserResponse(
        id=user["id"],
        username=user["username"],
        display_name=user.get("display_name"),
        role=user["role"],
        is_active=bool(user.get("is_active", 1)),
        created_at=user.get("created_at", ""),
        last_login_at=user.get("last_login_at"),
    )


# ── Pydantic 모델 ────────────────────────────────────────────────────────────

class PasswordChange(BaseModel):
    current_password: str
    new_password: str


class DisplayNameUpdate(BaseModel):
    display_name: str


# ── 회원가입 ─────────────────────────────────────────────────────────────────

@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(req: UserCreate, response: Response):
    """새 사용자 가입. 기본 역할은 user."""
    store = get_user_store()

    existing = store.get_user_by_username(req.username)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"이미 존재하는 사용자 이름입니다: {req.username}",
        )

    try:
        user = store.create_user(
            username=req.username,
            password=req.password,
            display_name=req.display_name or req.username,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    # 가입 즉시 로그인 (토큰 발급)
    token = create_access_token(user["id"], user["role"], user["username"])
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        httponly=True,
        max_age=ACCESS_TOKEN_EXPIRE_HOURS * 3600,
        samesite="lax",
        path="/",
    )

    return _user_to_response(user)


# ── 로그인 ────────────────────────────────────────────────────────────────────

@router.post("/login", response_model=UserResponse)
async def login(req: UserLogin, response: Response):
    """사용자 로그인. 성공 시 HttpOnly 쿠키에 JWT 저장."""
    store = get_user_store()
    user = store.authenticate(req.username, req.password)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="사용자 이름 또는 비밀번호가 올바르지 않습니다.",
        )

    token = create_access_token(user["id"], user["role"], user["username"])
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        httponly=True,
        max_age=ACCESS_TOKEN_EXPIRE_HOURS * 3600,
        samesite="lax",
        path="/",
    )

    logger.info("로그인 성공: %s (role=%s)", user["username"], user["role"])
    return _user_to_response(user)


# ── 로그아웃 ─────────────────────────────────────────────────────────────────

@router.post("/logout")
async def logout(response: Response):
    """로그아웃. 쿠키 삭제."""
    response.delete_cookie(key=COOKIE_NAME, path="/")
    return {"message": "로그아웃되었습니다."}


# ── 내 프로필 ────────────────────────────────────────────────────────────────

@router.get("/me", response_model=UserResponse)
async def get_me(current_user: dict = Depends(get_current_user)):
    """현재 로그인한 사용자 정보."""
    store = get_user_store()
    user = store.get_user(current_user["id"])
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="사용자를 찾을 수 없습니다.")
    return _user_to_response(user)


# ── 비밀번호 변경 ─────────────────────────────────────────────────────────────

@router.put("/me/password")
async def change_password(
    req: PasswordChange,
    current_user: dict = Depends(get_current_user),
):
    """비밀번호 변경."""
    store = get_user_store()

    user = store.authenticate(current_user["username"], req.current_password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="현재 비밀번호가 올바르지 않습니다.",
        )

    try:
        store.update_password(current_user["id"], req.new_password)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    return {"message": "비밀번호가 변경되었습니다."}


# ── 표시 이름 변경 ───────────────────────────────────────────────────────────

@router.put("/me/display-name", response_model=UserResponse)
async def update_display_name(
    req: DisplayNameUpdate,
    current_user: dict = Depends(get_current_user),
):
    """표시 이름 변경."""
    store = get_user_store()
    user = store.update_display_name(current_user["id"], req.display_name)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="사용자를 찾을 수 없습니다.")
    return _user_to_response(user)