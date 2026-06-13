"""mAI-Brain — 관리자용 사용자 관리 라우터

사용자 목록, 상세, 역할 변경, 활성/비활성, 삭제.
모든 엔드포인트는 관리자 권한 필요.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, status

from app.models.user import UserResponse, RoleUpdate, ActiveUpdate, get_user_store
from app.core.auth_jwt import require_admin

logger = logging.getLogger(__name__)

router = APIRouter()


def _user_to_response(user: dict) -> UserResponse:
    """DB 행을 응답 모델로 변환."""
    return UserResponse(
        id=user["id"],
        username=user["username"],
        display_name=user.get("display_name"),
        role=user["role"],
        is_active=bool(user.get("is_active", 1)),
        created_at=user.get("created_at", ""),
        last_login_at=user.get("last_login_at"),
    )


# ── 사용자 목록 ───────────────────────────────────────────────────────────────

@router.get("", response_model=list[UserResponse])
async def list_users(
    limit: int = 50,
    offset: int = 0,
    admin: dict = Depends(require_admin),
):
    """관리자: 사용자 목록 조회."""
    store = get_user_store()
    users = store.list_users(limit=limit, offset=offset)
    return [_user_to_response(u) for u in users]


# ── 사용자 상세 ───────────────────────────────────────────────────────────────

@router.get("/{user_id}", response_model=UserResponse)
async def get_user(
    user_id: str,
    admin: dict = Depends(require_admin),
):
    """관리자: 사용자 상세 조회."""
    store = get_user_store()
    user = store.get_user(user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="사용자를 찾을 수 없습니다.")
    return _user_to_response(user)


# ── 역할 변경 ─────────────────────────────────────────────────────────────────

@router.put("/{user_id}/role", response_model=UserResponse)
async def update_role(
    user_id: str,
    req: RoleUpdate,
    admin: dict = Depends(require_admin),
):
    """관리자: 사용자 역할 변경 (admin ↔ user)."""
    store = get_user_store()

    # 자기 자신의 역할 변경 방지
    if user_id == admin["id"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="자신의 역할은 변경할 수 없습니다.",
        )

    try:
        user = store.update_role(user_id, req.role)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="사용자를 찾을 수 없습니다.")

    logger.info("역할 변경: %s → %s (by %s)", user["username"], req.role, admin["username"])
    return _user_to_response(user)


# ── 활성/비활성 ──────────────────────────────────────────────────────────────

@router.put("/{user_id}/active", response_model=UserResponse)
async def update_active(
    user_id: str,
    req: ActiveUpdate,
    admin: dict = Depends(require_admin),
):
    """관리자: 사용자 활성/비활성 전환."""
    store = get_user_store()

    if user_id == admin["id"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="자신을 비활성화할 수 없습니다.",
        )

    user = store.update_active(user_id, req.is_active)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="사용자를 찾을 수 없습니다.")

    status_text = "활성화" if req.is_active else "비활성화"
    logger.info("사용자 %s: %s (by %s)", user["username"], status_text, admin["username"])
    return _user_to_response(user)


# ── 사용자 삭제 ───────────────────────────────────────────────────────────────

@router.delete("/{user_id}")
async def delete_user(
    user_id: str,
    admin: dict = Depends(require_admin),
):
    """관리자: 사용자 삭제."""
    store = get_user_store()

    if user_id == admin["id"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="자신을 삭제할 수 없습니다.",
        )

    deleted = store.delete_user(user_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="사용자를 찾을 수 없습니다.")

    logger.info("사용자 삭제: %s (by %s)", user_id, admin["username"])
    return {"ok": True, "message": "사용자가 삭제되었습니다."}


# ── 사용자 통계 ───────────────────────────────────────────────────────────────

@router.get("/stats/summary")
async def user_stats(
    admin: dict = Depends(require_admin),
):
    """관리자: 사용자 통계."""
    store = get_user_store()
    users = store.list_users(limit=10000)
    return {
        "total": len(users),
        "active": sum(1 for u in users if u.get("is_active")),
        "admins": sum(1 for u in users if u.get("role") == "admin"),
        "regular_users": sum(1 for u in users if u.get("role") == "user"),
    }