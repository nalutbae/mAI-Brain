"""mAI-Brain — API 키 관리 라우터

관리자 전용: API 키 CRUD + 회전. /api/api-keys 엔드포인트.
"""

import logging

from fastapi import APIRouter, HTTPException

from app.models.api_key import (
    ApiKeyCreate,
    ApiKeyCreateResponse,
    ApiKeyResponse,
    get_api_key_store,
)

logger = logging.getLogger(__name__)
router = APIRouter()


# ── API 키 CRUD ─────────────────────────────────────────────────────────────

@router.get("", response_model=list[ApiKeyResponse])
async def list_api_keys():
    """모든 API 키 목록 조회."""
    store = get_api_key_store()
    return store.list_keys()


@router.post("", response_model=ApiKeyCreateResponse, status_code=201)
async def create_api_key(req: ApiKeyCreate):
    """새 API 키 생성. 평문 키는 이 응답에서만 반환됩니다."""
    store = get_api_key_store()
    result = store.create_key(req)
    logger.info("API 키 생성: id=%s, name=%s", result.id, result.name)
    return result


@router.get("/{key_id}", response_model=ApiKeyResponse)
async def get_api_key(key_id: str):
    """특정 API 키 정보 조회."""
    store = get_api_key_store()
    result = store.get_key(key_id)
    if not result:
        raise HTTPException(status_code=404, detail=f"API 키를 찾을 수 없습니다: {key_id}")
    return result


@router.post("/{key_id}/rotate", response_model=ApiKeyCreateResponse)
async def rotate_api_key(key_id: str):
    """API 키 회전. 기존 키를 비활성화하고 새 키를 발급합니다."""
    store = get_api_key_store()
    result = store.rotate_key(key_id)
    if not result:
        raise HTTPException(status_code=404, detail=f"API 키를 찾을 수 없습니다: {key_id}")
    logger.info("API 키 회전: old_id=%s → new_id=%s", key_id, result.id)
    return result


@router.post("/{key_id}/deactivate", response_model=ApiKeyResponse)
async def deactivate_api_key(key_id: str):
    """API 키 비활성화 (삭제 대신 사용 중지)."""
    store = get_api_key_store()
    if not store.deactivate_key(key_id):
        raise HTTPException(status_code=404, detail=f"API 키를 찾을 수 없습니다: {key_id}")
    result = store.get_key(key_id)
    logger.info("API 키 비활성화: id=%s", key_id)
    return result


@router.delete("/{key_id}")
async def delete_api_key(key_id: str):
    """API 키 완전 삭제."""
    store = get_api_key_store()
    if not store.delete_key(key_id):
        raise HTTPException(status_code=404, detail=f"API 키를 찾을 수 없습니다: {key_id}")
    logger.info("API 키 삭제: id=%s", key_id)
    return {"ok": True, "message": f"API 키 {key_id}가 삭제되었습니다."}