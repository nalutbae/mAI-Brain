"""mAI-Brain — 설정 모듈

환경변수 기반 설정을 관리합니다. pydantic-settings를 사용하여
.env 파일과 환경변수를 자동으로 로드합니다.
"""

from enum import Enum
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class EmbeddingProviderType(str, Enum):
    """임베딩 제공자 타입"""
    LOCAL = "local"       # bge-m3 로컬 (dense + sparse)
    API = "api"           # OpenAI/Jina API 임베딩 (dense) + Qdrant BM25 (sparse)
    OLLAMA = "ollama"     # Ollama 임베딩 (dense) + Qdrant BM25 (sparse)


class LLMProviderType(str, Enum):
    """LLM 제공자 타입"""
    OLLAMA_CLOUD = "ollama-cloud"  # ollama-cloud (1순위)
    DEEPSEEK = "deepseek"         # DeepSeek API (2순위)


class ChatMode(str, Enum):
    """채팅 모드"""
    FACT = "fact"        # 팩트 조회: top-5
    SUMMARY = "summary"  # 요약: top-8
    COLUMN = "column"    # 컬럼 작성: top-15~20
    REASONING = "reasoning"  # 추론: top-15, 문서 간 연결·인과·함의 도출


class ReasoningStrength(str, Enum):
    """추론 강도 (추론 모드에서만 사용)"""
    ALL = "all"         # 전체 (기본값)
    STRONG = "strong"   # 강한 추론만
    MID = "mid"         # 중간 추론만
    WEAK = "weak"       # 약한 추론만


class Settings(BaseSettings):
    """애플리케이션 설정"""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Qdrant
    qdrant_url: str = "http://localhost:6333"
    qdrant_collection_name: str = "mai_brain_documents"

    # 임베딩
    embedding_provider: EmbeddingProviderType = EmbeddingProviderType.LOCAL

    # Ollama (로컬 임베딩 시)
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "glm-5.1"  # ollama-cloud 기본 모델 (사용 환경에 맞게 변경)

    # API 임베딩 설정
    openai_api_key: str = ""
    cohere_api_key: str = ""
    embedding_api_provider: str = ""  # "openai", "jina" (빈값 → 자동 감지)
    embedding_api_model: str = ""     # 빈값 → 프로바이더 기본 모델
    embedding_api_base_url: str = ""  # 빈값 → 프로바이더 기본 URL
    embedding_api_key: str = ""       # 빈값 → OPENAI/JINA 키 자동 탐색

    # Ollama 임베딩 설정 (⚠️ 로컬 Ollama 전용, ollama-cloud는 임베딩 미지원)
    ollama_embedding_model: str = "nomic-embed-text"   # 기본 임베딩 모델 (768차원)
    ollama_embedding_dim: int = 768                      # nomic-embed-text 차원

    # LLM
    llm_provider: LLMProviderType = LLMProviderType.OLLAMA_CLOUD
    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com/v1"
    deepseek_model: str = "deepseek-chat"

    # CORS
    cors_origins: list[str] = ["http://localhost:3000", "http://localhost:3001"]

    # 청킹
    chunk_size: int = 700        # 토큰 단위
    chunk_overlap: int = 150     # 토큰 단위

    # 검색 모드별 top-k
    top_k_fact: int = 5
    top_k_summary: int = 8
    top_k_column: int = 18
    top_k_reasoning: int = 15

    # 앱 설정
    app_name: str = "mAI-Brain"
    debug: bool = False


@lru_cache
def get_settings() -> Settings:
    """설정 싱글톤 반환 (캐시됨)"""
    return Settings()