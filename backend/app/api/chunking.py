"""mAI-Brain — 청킹 프로파일 API

도메인별 시맨틱 청킹 프로파일 관리 및 미리보기 엔드포인트.

엔드포인트:
- GET  /api/chunking/profiles — 프로파일 목록
- POST /api/chunking/profiles — 커스텀 프로파일 생성
- PUT  /api/chunking/profiles/{profile_id} — 프로파일 수정
- DELETE /api/chunking/profiles/{profile_id} — 프로파일 삭제
- POST /api/chunking/profiles/{profile_id}/default — 기본 프로파일 설정
- POST /api/chunking/preview — 청킹 미리보기
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException

from app.models.chunking import (
    ChunkPreview,
    ChunkPreviewRequest,
    ChunkingProfile,
    ChunkingProfileCreate,
    ChunkingProfileUpdate,
)
from app.core.chunker_profiles import (
    get_profile_store,
    preview_chunks,
)

logger = logging.getLogger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# 프로파일 CRUD
# ---------------------------------------------------------------------------

@router.get("/profiles", response_model=list[ChunkingProfile])
async def list_profiles():
    """모든 청킹 프로파일 목록을 반환합니다.

    내장 프로파일(builtin_*)과 커스텀 프로파일을 모두 포함합니다.
    """
    store = get_profile_store()
    return store.list_profiles()


@router.post("/profiles", response_model=ChunkingProfile, status_code=201)
async def create_profile(data: ChunkingProfileCreate):
    """새 커스텀 청킹 프로파일을 생성합니다.

    내장 프로파일과 이름이 중복되면 생성할 수 없습니다.
    """
    store = get_profile_store()
    try:
        profile = store.create_profile(data)
        return profile
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.put("/profiles/{profile_id}", response_model=ChunkingProfile)
async def update_profile(profile_id: str, data: ChunkingProfileUpdate):
    """커스텀 청킹 프로파일을 수정합니다.

    내장 프로파일(builtin_*)은 수정할 수 없습니다.
    """
    store = get_profile_store()
    try:
        profile = store.update_profile(profile_id, data)
        if profile is None:
            raise HTTPException(status_code=404, detail=f"프로파일을 찾을 수 없습니다: {profile_id}")
        return profile
    except ValueError as e:
        raise HTTPException(status_code=403, detail=str(e))


@router.delete("/profiles/{profile_id}")
async def delete_profile(profile_id: str):
    """커스텀 청킹 프로파일을 삭제합니다.

    내장 프로파일과 기본 프로파일은 삭제할 수 없습니다.
    """
    store = get_profile_store()
    try:
        deleted = store.delete_profile(profile_id)
        if not deleted:
            raise HTTPException(status_code=404, detail=f"프로파일을 찾을 수 없습니다: {profile_id}")
        return {"message": "프로파일이 삭제되었습니다.", "profile_id": profile_id}
    except ValueError as e:
        raise HTTPException(status_code=403, detail=str(e))


@router.post("/profiles/{profile_id}/default", response_model=ChunkingProfile)
async def set_default_profile(profile_id: str):
    """기본 청킹 프로파일을 설정합니다.

    지정한 프로파일이 기본값으로 설정되고,
    기존 기본 프로파일은 일반 프로파일로 전환됩니다.
    """
    store = get_profile_store()
    profile = store.set_default(profile_id)
    if profile is None:
        raise HTTPException(status_code=404, detail=f"프로파일을 찾을 수 없습니다: {profile_id}")
    return profile


# ---------------------------------------------------------------------------
# 청킹 미리보기
# ---------------------------------------------------------------------------

@router.post("/preview", response_model=ChunkPreview)
async def preview_chunking(request: ChunkPreviewRequest):
    """텍스트를 청킹 프로파일로 미리보기합니다.

    실제 인덱싱에 영향을 주지 않는 읽기 전용 작업입니다.
    프로파일 ID 또는 커스텀 파라미터로 청킹 결과를 시뮬레이션합니다.
    """
    try:
        result = preview_chunks(request)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))