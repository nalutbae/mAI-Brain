"""mAI-Brain — 프로바이더 설정 API

LLM/임베딩 프로바이더 CRUD + 연결 테스트 엔드포인트.
"""

from __future__ import annotations

import logging
from typing import Optional

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.models.provider import (
    EMBEDDING_PROVIDER_DEFAULTS,
    LLM_PROVIDER_DEFAULTS,
    EmbeddingProviderConfig,
    EmbeddingProviderType,
    LLMProviderConfig,
    LLMProviderType as NewLLMProviderType,
    ProviderSettingsStore,
)

logger = logging.getLogger(__name__)
router = APIRouter()


# ---------------------------------------------------------------------------
# 요청/응답 모델
# ---------------------------------------------------------------------------

class LLMProviderCreate(BaseModel):
    """LLM 프로바이더 생성 요청"""
    id: str = Field(default="", description="프로바이더 ID (빈값 → 자동 생성)")
    provider: NewLLMProviderType
    name: str = Field(default="", description="표시 이름")
    api_key: str = Field(default="", description="API 키")
    base_url: str = Field(default="", description="빈값 → 프로바이더 기본 URL")
    model: str = Field(default="", description="빈값 → 프로바이더 기본 모델")
    is_active: bool = Field(default=False)
    temperature: float = Field(default=0.1)
    max_tokens: int = Field(default=2048)
    fallback_provider_id: str = Field(default="")


class LLMProviderUpdate(BaseModel):
    """LLM 프로바이더 업데이트 요청"""
    name: Optional[str] = None
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    model: Optional[str] = None
    is_active: Optional[bool] = None
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None
    fallback_provider_id: Optional[str] = None


class EmbeddingProviderUpdate(BaseModel):
    """임베딩 프로바이더 업데이트 요청"""
    provider: EmbeddingProviderType
    api_key: str = Field(default="")
    base_url: str = Field(default="")
    model: str = Field(default="")
    dim: int = Field(default=0)


class ConnectionTestRequest(BaseModel):
    """연결 테스트 요청"""
    provider: NewLLMProviderType
    api_key: str = Field(default="")
    base_url: str = Field(default="")
    model: str = Field(default="")


class ConnectionTestResponse(BaseModel):
    """연결 테스트 응답"""
    success: bool
    message: str
    model_info: Optional[str] = None
    response_time_ms: Optional[float] = None


class MaskedAPIKey(BaseModel):
    """마스킹된 API 키"""
    masked: str
    is_set: bool


# ---------------------------------------------------------------------------
# 유틸리티
# ---------------------------------------------------------------------------

def _mask_api_key(key: str) -> str:
    """API 키 마스킹 — 처음 4자리와 마지막 4자리만 표시."""
    if not key or len(key) < 12:
        return "****" if key else ""
    return f"{key[:4]}...{key[-4:]}"


def _mask_provider(provider: LLMProviderConfig) -> dict:
    """프로바이더 설정을 응답용으로 마스킹."""
    d = provider.model_dump()
    d["api_key"] = _mask_api_key(provider.api_key)
    d["effective_base_url"] = provider.get_effective_base_url()
    d["effective_model"] = provider.get_effective_model()
    d["display_name"] = provider.get_display_name()
    return d


# ---------------------------------------------------------------------------
# LLM 프로바이더 엔드포인트
# ---------------------------------------------------------------------------

@router.get("/providers/llm")
def list_llm_providers():
    """LLM 프로바이더 목록 조회."""
    store = ProviderSettingsStore.get()
    settings = store.get_settings()
    return {
        "providers": [_mask_provider(p) for p in settings.llm_providers],
        "active_id": next(
            (p.id for p in settings.llm_providers if p.is_active),
            None,
        ),
    }


@router.post("/providers/llm")
def create_llm_provider(req: LLMProviderCreate):
    """LLM 프로바이더 추가."""
    store = ProviderSettingsStore.get()
    config = LLMProviderConfig(
        id=req.id or "",
        provider=req.provider,
        name=req.name,
        api_key=req.api_key,
        base_url=req.base_url,
        model=req.model,
        is_active=req.is_active,
        temperature=req.temperature,
        max_tokens=req.max_tokens,
        fallback_provider_id=req.fallback_provider_id,
    )
    created = store.add_llm_provider(config)
    return _mask_provider(created)


@router.put("/providers/llm/{provider_id}")
def update_llm_provider(provider_id: str, req: LLMProviderUpdate):
    """LLM 프로바이더 업데이트."""
    store = ProviderSettingsStore.get()
    updates = {k: v for k, v in req.model_dump().items() if v is not None}
    updated = store.update_llm_provider(provider_id, updates)
    if updated is None:
        raise HTTPException(status_code=404, detail=f"프로바이더 '{provider_id}'를 찾을 수 없습니다.")
    return _mask_provider(updated)


@router.delete("/providers/llm/{provider_id}")
def delete_llm_provider(provider_id: str):
    """LLM 프로바이더 삭제."""
    store = ProviderSettingsStore.get()
    if not store.delete_llm_provider(provider_id):
        raise HTTPException(status_code=404, detail=f"프로바이더 '{provider_id}'를 찾을 수 없습니다.")
    return {"message": f"프로바이더 '{provider_id}'가 삭제되었습니다."}


@router.post("/providers/llm/{provider_id}/activate")
def activate_llm_provider(provider_id: str):
    """활성 LLM 프로바이더 변경."""
    store = ProviderSettingsStore.get()
    activated = store.set_active_llm_provider(provider_id)
    if activated is None:
        raise HTTPException(status_code=404, detail=f"프로바이더 '{provider_id}'를 찾을 수 없습니다.")
    # LLMClient는 ProviderSettingsStore에서 동적으로 읽으므로
    # 설정만 변경하면 됨 — 싱글톤 리셋 불필요
    return _mask_provider(activated)


# ---------------------------------------------------------------------------
# 임베딩 프로바이더 엔드포인트
# ---------------------------------------------------------------------------

@router.get("/providers/embedding")
def get_embedding_provider():
    """임베딩 프로바이더 설정 조회."""
    store = ProviderSettingsStore.get()
    config = store.get_settings().embedding
    d = config.model_dump()
    d["api_key"] = _mask_api_key(config.api_key)
    return d


@router.put("/providers/embedding")
def update_embedding_provider(req: EmbeddingProviderUpdate):
    """임베딩 프로바이더 설정 업데이트."""
    store = ProviderSettingsStore.get()
    config = EmbeddingProviderConfig(
        provider=req.provider,
        api_key=req.api_key,
        base_url=req.base_url,
        model=req.model,
        dim=req.dim,
    )
    updated = store.update_embedding_provider(config)
    d = updated.model_dump()
    d["api_key"] = _mask_api_key(updated.api_key)
    # 임베딩 프로바이더 변경 시 싱글톤 리셋 필요
    from app.core.embedding import reset_embedding_provider
    reset_embedding_provider()
    return d


# ---------------------------------------------------------------------------
# 사용 가능한 프로바이더 목록
# ---------------------------------------------------------------------------

@router.get("/providers/available/llm")
def list_available_llm_providers():
    """사용 가능한 LLM 프로바이더 타입 + 기본값 목록."""
    return {"providers": ProviderSettingsStore.get_available_llm_providers()}


@router.get("/providers/available/embedding")
def list_available_embedding_providers():
    """사용 가능한 임베딩 프로바이더 타입 + 기본값 목록."""
    return {"providers": ProviderSettingsStore.get_available_embedding_providers()}


# ---------------------------------------------------------------------------
# 연결 테스트
# ---------------------------------------------------------------------------

@router.post("/providers/test")
async def test_provider_connection(req: ConnectionTestRequest):
    """프로바이더 연결 테스트."""
    import time

    # 기본값 채우기
    defaults = LLM_PROVIDER_DEFAULTS.get(req.provider.value)
    base_url = req.base_url or (defaults.base_url if defaults else "")
    model = req.model or (defaults.default_model if defaults else "")
    api_key = req.api_key

    if not base_url or not model:
        return ConnectionTestResponse(
            success=False,
            message="base_url과 model을 지정하세요.",
        )

    # Anthropic은 별도 API 포맷
    if req.provider == NewLLMProviderType.ANTHROPIC:
        if not api_key:
            return ConnectionTestResponse(
                success=False,
                message="Anthropic API 키가 필요합니다.",
            )
        url = f"{base_url.rstrip('/')}/v1/messages"
        try:
            start = time.time()
            response = httpx.post(
                url,
                headers={
                    "x-api-key": api_key,
                    "anthropic-version": "2023-06-01",
                    "Content-Type": "application/json",
                },
                json={
                    "model": model,
                    "max_tokens": 10,
                    "messages": [{"role": "user", "content": "Hi"}],
                },
                timeout=30.0,
            )
            elapsed_ms = (time.time() - start) * 1000
            if response.status_code == 200:
                return ConnectionTestResponse(
                    success=True,
                    message=f"Anthropic({model}) 연결 성공",
                    model_info=model,
                    response_time_ms=round(elapsed_ms, 1),
                )
            else:
                return ConnectionTestResponse(
                    success=False,
                    message=f"Anthropic API 오류: {response.status_code} {response.text[:200]}",
                )
        except Exception as exc:
            return ConnectionTestResponse(
                success=False,
                message=f"Anthropic 연결 실패: {exc}",
            )

    # OpenAI 호환 엔드포인트 (ollama, openai, groq, deepseek, custom)
    url = f"{base_url.rstrip('/')}/v1/chat/completions"
    effective_key = api_key or "ollama"
    try:
        start = time.time()
        response = httpx.post(
            url,
            headers={
                "Authorization": f"Bearer {effective_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": model,
                "messages": [{"role": "user", "content": "Hi"}],
                "max_tokens": 10,
            },
            timeout=30.0,
        )
        elapsed_ms = (time.time() - start) * 1000
        if response.status_code == 200:
            data = response.json()
            model_used = data.get("model", model)
            return ConnectionTestResponse(
                success=True,
                message=f"{req.provider.value}({model_used}) 연결 성공",
                model_info=model_used,
                response_time_ms=round(elapsed_ms, 1),
            )
        else:
            return ConnectionTestResponse(
                success=False,
                message=f"{req.provider.value} API 오류: {response.status_code} {response.text[:200]}",
            )
    except httpx.ConnectError:
        return ConnectionTestResponse(
            success=False,
            message=f"{req.provider.value} 서버에 연결할 수 없습니다: {base_url}",
        )
    except Exception as exc:
        return ConnectionTestResponse(
            success=False,
            message=f"{req.provider.value} 연결 실패: {exc}",
        )


# ---------------------------------------------------------------------------
# 전체 설정 조회
# ---------------------------------------------------------------------------

@router.get("/settings")
def get_full_settings():
    """전체 설정 조회 (LLM + 임베딩)."""
    store = ProviderSettingsStore.get()
    settings = store.get_settings()
    return {
        "llm": {
            "providers": [_mask_provider(p) for p in settings.llm_providers],
            "active_id": next(
                (p.id for p in settings.llm_providers if p.is_active),
                None,
            ),
        },
        "embedding": {
            "provider": settings.embedding.provider.value,
            "api_key": _mask_api_key(settings.embedding.api_key),
            "base_url": settings.embedding.base_url,
            "model": settings.embedding.model,
            "dim": settings.embedding.dim,
        },
    }