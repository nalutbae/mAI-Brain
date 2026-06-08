"""mAI-Brain — LLM/임베딩 프로바이더 설정 모델

다중 프로바이더 지원: Ollama, OpenAI, Anthropic, Groq 등
설정은 JSON 파일로 저장되며, 런타임에 동적으로 변경 가능.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field, SecretStr


# ---------------------------------------------------------------------------
# 프로바이더 타입 enum
# ---------------------------------------------------------------------------

class LLMProviderType(str, Enum):
    """LLM 제공자 타입"""
    OLLAMA = "ollama"
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    GROQ = "groq"
    DEEPSEEK = "deepseek"
    CUSTOM = "custom"  # OpenAI 호환 커스텀 엔드포인트


class EmbeddingProviderType(str, Enum):
    """임베딩 제공자 타입"""
    LOCAL = "local"       # bge-m3 로컬 (dense + sparse)
    OPENAI = "openai"     # OpenAI API 임베딩
    JINA = "jina"         # Jina API 임베딩
    OLLAMA = "ollama"     # Ollama 임베딩
    COHERE = "cohere"     # Cohere API 임베딩


# ---------------------------------------------------------------------------
# 프로바이더별 기본 설정
# ---------------------------------------------------------------------------

class ProviderDefaults(BaseModel):
    """프로바이더별 기본값"""
    base_url: str
    default_model: str
    supports_streaming: bool = True
    supports_tools: bool = False
    api_key_env_var: str = ""  # 환경변수에서 API 키 자동 로드할 때 사용


LLM_PROVIDER_DEFAULTS: dict[str, ProviderDefaults] = {
    "ollama": ProviderDefaults(
        base_url="http://localhost:11434",
        default_model="glm-5.1",
        supports_streaming=True,
        supports_tools=False,
        api_key_env_var="",
    ),
    "openai": ProviderDefaults(
        base_url="https://api.openai.com/v1",
        default_model="gpt-4o",
        supports_streaming=True,
        supports_tools=True,
        api_key_env_var="OPENAI_API_KEY",
    ),
    "anthropic": ProviderDefaults(
        base_url="https://api.anthropic.com",
        default_model="claude-sonnet-4-20250514",
        supports_streaming=True,
        supports_tools=True,
        api_key_env_var="ANTHROPIC_API_KEY",
    ),
    "groq": ProviderDefaults(
        base_url="https://api.groq.com/openai/v1",
        default_model="llama-3.3-70b-versatile",
        supports_streaming=True,
        supports_tools=True,
        api_key_env_var="GROQ_API_KEY",
    ),
    "deepseek": ProviderDefaults(
        base_url="https://api.deepseek.com/v1",
        default_model="deepseek-chat",
        supports_streaming=True,
        supports_tools=False,
        api_key_env_var="DEEPSEEK_API_KEY",
    ),
    "custom": ProviderDefaults(
        base_url="",
        default_model="",
        supports_streaming=True,
        supports_tools=False,
        api_key_env_var="",
    ),
}

EMBEDDING_PROVIDER_DEFAULTS: dict[str, dict] = {
    "local": {
        "description": "bge-m3 로컬 임베딩 (dense + sparse, 1024차원)",
        "requires_api_key": False,
    },
    "openai": {
        "description": "OpenAI text-embedding-3-small (dense, 1536차원)",
        "default_model": "text-embedding-3-small",
        "default_base_url": "https://api.openai.com/v1",
        "default_dim": 1536,
        "requires_api_key": True,
        "api_key_env_var": "OPENAI_API_KEY",
    },
    "jina": {
        "description": "Jina jina-embeddings-v3 (dense, 1024차원)",
        "default_model": "jina-embeddings-v3",
        "default_base_url": "https://api.jina.ai/v1",
        "default_dim": 1024,
        "requires_api_key": True,
        "api_key_env_var": "JINA_API_KEY",
    },
    "ollama": {
        "description": "로컬 Ollama 임베딩 (dense, 모델별 차원 상이)",
        "default_model": "nomic-embed-text",
        "default_base_url": "http://localhost:11434",
        "default_dim": 768,
        "requires_api_key": False,
    },
    "cohere": {
        "description": "Cohere embed-multilingual-v3.0 (dense, 1024차원)",
        "default_model": "embed-multilingual-v3.0",
        "default_base_url": "https://api.cohere.ai/v1",
        "default_dim": 1024,
        "requires_api_key": True,
        "api_key_env_var": "COHERE_API_KEY",
    },
}


# ---------------------------------------------------------------------------
# 프로바이더 설정 모델
# ---------------------------------------------------------------------------

class LLMProviderConfig(BaseModel):
    """LLM 프로바이더 설정"""
    id: str = Field(default="default", description="프로바이더 설정 ID")
    provider: LLMProviderType = Field(default=LLMProviderType.OLLAMA)
    name: str = Field(default="", description="사용자 정의 이름 (빈값 → 기본 이름)")
    api_key: str = Field(default="", description="API 키 (마스킹 처리)")
    base_url: str = Field(default="", description="빈값 → 프로바이더 기본 URL")
    model: str = Field(default="", description="빈값 → 프로바이더 기본 모델")
    is_active: bool = Field(default=True, description="현재 활성 프로바이더 여부")
    temperature: float = Field(default=0.1, description="응답 온도")
    max_tokens: int = Field(default=2048, description="최대 토큰 수")
    fallback_provider_id: str = Field(default="", description="폴백 프로바이더 ID")
    created_at: str = Field(default="")
    updated_at: str = Field(default="")

    def get_effective_base_url(self) -> str:
        """빈값이면 프로바이더 기본 URL 반환"""
        if self.base_url:
            return self.base_url
        defaults = LLM_PROVIDER_DEFAULTS.get(self.provider.value)
        return defaults.base_url if defaults else ""

    def get_effective_model(self) -> str:
        """빈값이면 프로바이더 기본 모델 반환"""
        if self.model:
            return self.model
        defaults = LLM_PROVIDER_DEFAULTS.get(self.provider.value)
        return defaults.default_model if defaults else ""

    def get_display_name(self) -> str:
        """표시용 이름"""
        if self.name:
            return self.name
        return f"{self.provider.value} / {self.get_effective_model()}"


class EmbeddingProviderConfig(BaseModel):
    """임베딩 프로바이더 설정"""
    provider: EmbeddingProviderType = Field(default=EmbeddingProviderType.LOCAL)
    api_key: str = Field(default="")
    base_url: str = Field(default="", description="빈값 → 프로바이더 기본 URL")
    model: str = Field(default="", description="빈값 → 프로바이더 기본 모델")
    dim: int = Field(default=0, description="임베딩 차원 (0 → 프로바이더 기본값)")


class AppSettings(BaseModel):
    """애플리케이션 전체 설정 (LLM + 임베딩)"""
    llm_providers: list[LLMProviderConfig] = Field(default_factory=list)
    embedding: EmbeddingProviderConfig = Field(default_factory=EmbeddingProviderConfig)
    # 호환성: 기존 .env 설정값을 유지
    llm_provider: str = Field(default="ollama-cloud", description="레거시 LLM_PROVIDER 값")
    deepseek_api_key: str = Field(default="")
    deepseek_base_url: str = Field(default="https://api.deepseek.com/v1")
    deepseek_model: str = Field(default="deepseek-chat")
    ollama_base_url: str = Field(default="http://localhost:11434")
    ollama_model: str = Field(default="glm-5.1")


# ---------------------------------------------------------------------------
# 설정 저장소 (JSON 파일 기반)
# ---------------------------------------------------------------------------

SETTINGS_DIR = Path(os.environ.get("MAI_BRAIN_DATA_DIR", "data"))
SETTINGS_FILE = SETTINGS_DIR / "provider_settings.json"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class ProviderSettingsStore:
    """프로바이더 설정 JSON 저장소 — 싱글톤."""

    _instance: Optional[ProviderSettingsStore] = None

    def __init__(self, path: Path = SETTINGS_FILE) -> None:
        self._path = path
        self._data: AppSettings = AppSettings()
        self._load()

    # ── 싱글톤 ──────────────────────────────────────────────────────

    @classmethod
    def get(cls) -> ProviderSettingsStore:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset(cls) -> None:
        """테스트용 리셋"""
        cls._instance = None

    # ── I/O ──────────────────────────────────────────────────────────

    def _load(self) -> None:
        """JSON 파일에서 설정 로드. 없으면 기본값 생성."""
        if self._path.exists():
            try:
                raw = self._path.read_text(encoding="utf-8")
                data = json.loads(raw)
                self._data = AppSettings(**data)
                return
            except (json.JSONDecodeError, Exception):
                pass

        # 기본값: .env의 레거시 설정에서 초기 프로바이더 구성
        self._data = AppSettings()
        self._init_from_env()
        self._save()

    def _save(self) -> None:
        """JSON 파일에 설정 저장."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(
            self._data.model_dump_json(indent=2),
            encoding="utf-8",
        )

    def _init_from_env(self) -> None:
        """레거시 .env 환경변수에서 초기 프로바이더 구성."""
        # ollama-cloud 프로바이더 (1순위)
        ollama_provider = LLMProviderConfig(
            id="ollama-cloud",
            provider=LLMProviderType.OLLAMA,
            name="Ollama Cloud",
            api_key="",
            base_url=self._data.ollama_base_url or "http://localhost:11434",
            model=self._data.ollama_model or "glm-5.1",
            is_active=True,
            fallback_provider_id="deepseek",
            created_at=_now_iso(),
            updated_at=_now_iso(),
        )

        # DeepSeek 프로바이더 (2순위)
        deepseek_provider = LLMProviderConfig(
            id="deepseek",
            provider=LLMProviderType.DEEPSEEK,
            name="DeepSeek",
            api_key=self._data.deepseek_api_key,
            base_url=self._data.deepseek_base_url or "https://api.deepseek.com/v1",
            model=self._data.deepseek_model or "deepseek-chat",
            is_active=False,
            fallback_provider_id="",
            created_at=_now_iso(),
            updated_at=_now_iso(),
        )

        self._data.llm_providers = [ollama_provider, deepseek_provider]

        # 임베딩 설정 (레거시 .env에서)
        provider_str = self._data.llm_provider  # ollama-cloud / deepseek
        emb_provider = EmbeddingProviderType.LOCAL
        if provider_str == "api" or os.environ.get("EMBEDDING_PROVIDER") == "api":
            emb_provider = EmbeddingProviderType.OPENAI
        elif provider_str == "ollama" or os.environ.get("EMBEDDING_PROVIDER") == "ollama":
            emb_provider = EmbeddingProviderType.OLLAMA

        self._data.embedding = EmbeddingProviderConfig(
            provider=emb_provider,
            api_key=os.environ.get("OPENAI_API_KEY", "")
            or os.environ.get("EMBEDDING_API_KEY", ""),
            base_url=os.environ.get("EMBEDDING_API_BASE_URL", ""),
            model=os.environ.get("EMBEDDING_API_MODEL", ""),
            dim=int(os.environ.get("OLLAMA_EMBEDDING_DIM", "0") or "0"),
        )

    # ── 프로바이더 CRUD ──────────────────────────────────────────────

    def get_settings(self) -> AppSettings:
        """전체 설정 반환."""
        return self._data

    def get_active_llm_provider(self) -> LLMProviderConfig:
        """현재 활성 LLM 프로바이더 반환."""
        for p in self._data.llm_providers:
            if p.is_active:
                return p
        # 활성이 없으면 첫 번째 반환
        if self._data.llm_providers:
            return self._data.llm_providers[0]
        # 마지막 리소트: 기본 ollama-cloud
        return LLMProviderConfig(
            id="ollama-cloud",
            provider=LLMProviderType.OLLAMA,
            name="Ollama Cloud",
            base_url="http://localhost:11434",
            model="glm-5.1",
            is_active=True,
        )

    def get_fallback_llm_provider(self, provider: LLMProviderConfig) -> Optional[LLMProviderConfig]:
        """폴백 프로바이더 반환."""
        if not provider.fallback_provider_id:
            return None
        for p in self._data.llm_providers:
            if p.id == provider.fallback_provider_id:
                return p
        return None

    def add_llm_provider(self, config: LLMProviderConfig) -> LLMProviderConfig:
        """LLM 프로바이더 추가."""
        if not config.id:
            config.id = f"provider-{len(self._data.llm_providers) + 1}"
        config.created_at = config.created_at or _now_iso()
        config.updated_at = _now_iso()
        self._data.llm_providers.append(config)
        self._save()
        return config

    def update_llm_provider(self, provider_id: str, updates: dict) -> Optional[LLMProviderConfig]:
        """LLM 프로바이더 업데이트."""
        for i, p in enumerate(self._data.llm_providers):
            if p.id == provider_id:
                updated = p.model_copy(update=updates)
                updated.updated_at = _now_iso()
                self._data.llm_providers[i] = updated
                # 활성으로 설정 시 다른 프로바이더 비활성화
                if updates.get("is_active"):
                    for j, other in enumerate(self._data.llm_providers):
                        if j != i:
                            self._data.llm_providers[j] = other.model_copy(
                                update={"is_active": False}
                            )
                self._save()
                return updated
        return None

    def delete_llm_provider(self, provider_id: str) -> bool:
        """LLM 프로바이더 삭제."""
        original_len = len(self._data.llm_providers)
        self._data.llm_providers = [
            p for p in self._data.llm_providers if p.id != provider_id
        ]
        if len(self._data.llm_providers) < original_len:
            self._save()
            return True
        return False

    def set_active_llm_provider(self, provider_id: str) -> Optional[LLMProviderConfig]:
        """활성 LLM 프로바이더 변경."""
        found = False
        for i, p in enumerate(self._data.llm_providers):
            if p.id == provider_id:
                self._data.llm_providers[i] = p.model_copy(update={"is_active": True})
                found = True
            else:
                self._data.llm_providers[i] = p.model_copy(update={"is_active": False})
        if found:
            self._save()
            return self.get_active_llm_provider()
        return None

    def update_embedding_provider(self, config: EmbeddingProviderConfig) -> EmbeddingProviderConfig:
        """임베딩 프로바이더 설정 업데이트."""
        self._data.embedding = config
        self._save()
        return config

    # ── 프로바이더 목록 조회 ────────────────────────────────────────

    @staticmethod
    def get_available_llm_providers() -> list[dict]:
        """사용 가능한 LLM 프로바이더 목록 (ID + 기본값)."""
        result = []
        for key, defaults in LLM_PROVIDER_DEFAULTS.items():
            result.append({
                "provider": key,
                "default_base_url": defaults.base_url,
                "default_model": defaults.default_model,
                "supports_streaming": defaults.supports_streaming,
                "supports_tools": defaults.supports_tools,
                "requires_api_key": bool(defaults.api_key_env_var),
            })
        return result

    @staticmethod
    def get_available_embedding_providers() -> list[dict]:
        """사용 가능한 임베딩 프로바이더 목록."""
        result = []
        for key, info in EMBEDDING_PROVIDER_DEFAULTS.items():
            result.append({
                "provider": key,
                "description": info.get("description", ""),
                "default_model": info.get("default_model", ""),
                "default_base_url": info.get("default_base_url", ""),
                "default_dim": info.get("default_dim", 0),
                "requires_api_key": info.get("requires_api_key", False),
            })
        return result