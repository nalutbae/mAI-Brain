"""mAI-Brain — 시스템 프롬프트 API

엔드포인트:
- GET    /api/prompts                       — 프롬프트 목록 (필터: workspace_id, mode)
- POST   /api/prompts                       — 프롬프트 생성
- GET    /api/prompts/{id}                  — 프롬프트 조회
- PUT    /api/prompts/{id}                  — 프롬프트 수정
- DELETE /api/prompts/{id}                  — 프롬프트 삭제
- POST   /api/prompts/{id}/preview          — 프롬프트 미리보기 (변수 치환)
- GET    /api/prompts/defaults              — 기본 프롬프트 목록
- GET    /api/prompts/variables             — 지원 변수 목록
"""

from fastapi import APIRouter, HTTPException, Query
from typing import Optional

from app.config import ChatMode
from app.models.system_prompt import (
    SystemPrompt,
    SystemPromptCreate,
    SystemPromptUpdate,
    SystemPromptListResponse,
    SystemPromptPreview,
    SUPPORTED_VARIABLES,
)
from app.core.system_prompt import get_system_prompt_store

router = APIRouter()


@router.get("", response_model=SystemPromptListResponse)
def list_prompts(
    workspace_id: Optional[str] = Query(default=None, description="워크스페이스 ID 필터"),
    mode: Optional[ChatMode] = Query(default=None, description="채팅 모드 필터"),
):
    """프롬프트 목록 조회."""
    store = get_system_prompt_store()
    prompts = store.list_prompts(workspace_id=workspace_id, mode=mode)
    return SystemPromptListResponse(prompts=prompts, total=len(prompts))


@router.post("", response_model=SystemPrompt, status_code=201)
def create_prompt(data: SystemPromptCreate):
    """새 프롬프트 생성. 동일 워크스페이스+모드 조합의 커스텀 프롬프트는 1개만 허용."""
    store = get_system_prompt_store()
    try:
        return store.create_prompt(data)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/defaults", response_model=SystemPromptListResponse)
def list_defaults():
    """기본 프롬프트 목록 조회."""
    store = get_system_prompt_store()
    prompts = [p for p in store.list_prompts() if p.is_default]
    return SystemPromptListResponse(prompts=prompts, total=len(prompts))


@router.get("/variables")
def list_variables():
    """지원하는 템플릿 변수 목록."""
    return {"variables": SUPPORTED_VARIABLES}


@router.get("/{prompt_id}", response_model=SystemPrompt)
def get_prompt(prompt_id: str):
    """프롬프트 ID로 조회."""
    store = get_system_prompt_store()
    prompt = store.get_prompt(prompt_id)
    if not prompt:
        raise HTTPException(status_code=404, detail="프롬프트를 찾을 수 없습니다")
    return prompt


@router.put("/{prompt_id}", response_model=SystemPrompt)
def update_prompt(prompt_id: str, data: SystemPromptUpdate):
    """프롬프트 수정."""
    store = get_system_prompt_store()
    prompt = store.update_prompt(prompt_id, data)
    if not prompt:
        raise HTTPException(status_code=404, detail="프롬프트를 찾을 수 없습니다")
    return prompt


@router.delete("/{prompt_id}")
def delete_prompt(prompt_id: str):
    """프롬프트 삭제. 기본 프롬프트는 삭제 불가."""
    store = get_system_prompt_store()
    try:
        if not store.delete_prompt(prompt_id):
            raise HTTPException(status_code=404, detail="프롬프트를 찾을 수 없습니다")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"message": "프롬프트가 삭제되었습니다", "id": prompt_id}


@router.post("/{prompt_id}/preview", response_model=SystemPromptPreview)
def preview_prompt(
    prompt_id: str,
    workspace_id: Optional[str] = Query(default=None, description="변수 치환용 워크스페이스 ID"),
    mode: Optional[str] = Query(default=None, description="채팅 모드 (변수 치환용)"),
):
    """프롬프트 미리보기. 템플릿 변수를 실제 값으로 치환한 결과를 반환."""
    store = get_system_prompt_store()
    context = store.build_context(workspace_id=workspace_id, mode=mode)
    result = store.preview_prompt(prompt_id, context=context)
    if not result:
        raise HTTPException(status_code=404, detail="프롬프트를 찾을 수 없습니다")
    return result
