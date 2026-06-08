"""mAI-Brain — 설정 모듈

환경변수 기반 설정을 관리합니다. pydantic-settings를 사용하여
.env 파일과 환경변수를 자동으로 로드합니다.

NOTE: LLMProviderType / EmbeddingProviderType은 models/provider.py로 이전했습니다.
이 모듈은 레거시 .env 호환을 위해 기존 필드를 유지합니다.
"""

from enum import Enum
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class EmbeddingProviderType(str, Enum):
    """임베딩 제공자 타입 (레거시 — models/provider.py 참조)"""
    LOCAL = "local"
    API = "api"
    OLLAMA = "ollama"


class VectorDBType(str, Enum):
    """벡터 DB 타입"""
    QDRANT = "qdrant"
    CHROMA = "chroma"
    PGVECTOR = "pgvector"


class LLMProviderType(str, Enum):
    """LLM 제공자 타입 (레거시 — models/provider.py의 다중 프로바이더로 대체)"""
    OLLAMA_CLOUD = "ollama-cloud"
    DEEPSEEK = "deepseek"


class ChatMode(str, Enum):
    """채팅 모드"""
    FACT = "fact"
    SUMMARY = "summary"
    COLUMN = "column"
    REASONING = "reasoning"


class ReasoningStrength(str, Enum):
    """추론 강도 (추론 모드에서만 사용)"""
    ALL = "all"
    STRONG = "strong"
    MID = "mid"
    WEAK = "weak"


class Settings(BaseSettings):
    """애플리케이션 설정 (레거시 .env 호환)"""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Qdrant
    qdrant_url: str = "http://localhost:6333"
    qdrant_collection_name: str = "mai_brain_documents"

    # 벡터 DB 선택
    vector_db: VectorDBType = VectorDBType.QDRANT

    # 임베딩 (레거시 — provider_settings.json이 우선)
    embedding_provider: EmbeddingProviderType = EmbeddingProviderType.LOCAL

    # Ollama (로컬 임베딩 시)
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "glm-5.1"

    # API 임베딩 설정
    openai_api_key: str = ""
    cohere_api_key: str = ""
    embedding_api_provider: str = ""
    embedding_api_model: str = ""
    embedding_api_base_url: str = ""
    embedding_api_key: str = ""

    # Ollama 임베딩 설정
    ollama_embedding_model: str = "nomic-embed-text"
    ollama_embedding_dim: int = 768

    # LLM (레거시 — provider_settings.json이 우선)
    llm_provider: LLMProviderType = LLMProviderType.OLLAMA_CLOUD
    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com/v1"
    deepseek_model: str = "deepseek-chat"

    # CORS
    cors_origins: list[str] = ["http://localhost:3000", "http://localhost:3001"]

    # 청킹
    chunk_size: int = 700
    chunk_overlap: int = 150

    # 검색 모드별 top-k
    top_k_fact: int = 5
    top_k_summary: int = 8
    top_k_column: int = 18
    top_k_reasoning: int = 15

    # 음성 인터페이스 (선택적)
    voice_whisper_api_key: str = ""
    voice_elevenlabs_api_key: str = ""
    voice_elevenlabs_voice_id: str = ""

    # 앱 설정
    app_name: str = "mAI-Brain"
    debug: bool = False


@lru_cache
def get_settings() -> Settings:
    """설정 싱글톤 반환 (캐시됨)"""
    return Settings()