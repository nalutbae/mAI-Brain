"""mAI-Brain AI 챗봇 — 임베딩 파이프라인

EmbeddingProvider 추상 인터페이스 기반:
- LocalBGEM3: FlagEmbedding bge-m3 로컬 실행 (dense + sparse)
- OpenAIEmbedding: OpenAI API 임베딩 (dense만, sparse=None)
- JinaEmbedding: Jina API 임베딩 (dense만, sparse=None)
- OllamaEmbedding: Ollama/OpenAI 호환 임베딩 (dense만, sparse=None)
- CohereEmbedding: Cohere API 임베딩 (dense만, sparse=None)

팩토리 함수 get_embedding_provider()가 ProviderSettingsStore를 통해
현재 선택된 임베딩 프로바이더의 인스턴스를 반환.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional

import numpy as np

from app.models.provider import (
    EmbeddingProviderConfig,
    EmbeddingProviderType,
    EMBEDDING_PROVIDER_DEFAULTS,
    ProviderSettingsStore,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 데이터 모델
# ---------------------------------------------------------------------------

@dataclass
class EmbeddingResult:
    """임베딩 결과 — dense + sparse 벡터를 함께 전달하는 컨테이너.

    Attributes:
        dense: (N, dim) 형태의 dense 벡터 리스트.
               LocalBGEM3 → 1024차원, APIEmbedding → 모델에 따라 다름.
        sparse: 길이 N 리스트. 각 원소는 {토큰: 가중치} 딕셔너리.
               LocalBGEM3 → bge-m3 내장 sparse (BM25-like),
               APIEmbedding → None (Qdrant BM25로 대체).
    """

    dense: list[list[float]]
    sparse: Optional[list[dict[str, float]]] = None

    @property
    def dim(self) -> int:
        """dense 벡터 차원 수"""
        if not self.dense:
            return 0
        return len(self.dense[0])


# ---------------------------------------------------------------------------
# 추상 인터페이스
# ---------------------------------------------------------------------------

class EmbeddingProvider(ABC):
    """임베딩 제공자 추상 인터페이스."""

    @abstractmethod
    def encode(self, texts: list[str]) -> EmbeddingResult:
        """텍스트 리스트 → dense + sparse 임베딩 결과."""
        ...


# ---------------------------------------------------------------------------
# LocalBGEM3 — 로컬 bge-m3 (dense + sparse)
# ---------------------------------------------------------------------------

class LocalBGEM3(EmbeddingProvider):
    """FlagEmbedding BGEM3FlagModel 기반 로컬 임베딩.

    - dense: 1024차원 벡터
    - sparse: bge-m3 내장 lexical weights (BM25-like)
    - MPS(Apple Silicon) / CUDA(NVIDIA) 자동 감지 및 가속
    """

    def __init__(self, model_name: str | None = None) -> None:
        model_name = model_name or "BAAI/bge-m3"
        self._device = self._detect_device()
        logger.info("LocalBGEM3 초기화: model=%s, device=%s", model_name, self._device)

        from FlagEmbedding import BGEM3FlagModel  # noqa: PLC0415

        self._model = BGEM3FlagModel(
            model_name,
            use_fp16=True,
            device=self._device,
        )
        logger.info("LocalBGEM3 모델 로드 완료")

    @staticmethod
    def _detect_device() -> str:
        """사용 가능한 가속기 자동 감지 (CUDA → MPS → CPU)."""
        try:
            import torch  # noqa: PLC0415
            if torch.cuda.is_available():
                return "cuda"
            if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
                return "mps"
        except ImportError:
            pass
        return "cpu"

    def encode(self, texts: list[str]) -> EmbeddingResult:
        """bge-m3로 dense + sparse 벡터 동시 생성."""
        if not texts:
            return EmbeddingResult(dense=[], sparse=[])

        result = self._model.encode(
            texts,
            return_dense=True,
            return_sparse=True,
            return_colbert_vecs=False,
        )

        dense_vecs = result["dense_vecs"]
        if isinstance(dense_vecs, np.ndarray):
            dense_list = dense_vecs.tolist()
        else:
            dense_list = [v.tolist() if isinstance(v, np.ndarray) else list(v) for v in dense_vecs]

        sparse_list = []
        for token_weights in result["lexical_weights"]:
            sparse_list.append({k: float(v) for k, v in token_weights.items()})

        return EmbeddingResult(dense=dense_list, sparse=sparse_list)


# ---------------------------------------------------------------------------
# OpenAIEmbedding — OpenAI API 임베딩 (dense만)
# ---------------------------------------------------------------------------

class OpenAIEmbedding(EmbeddingProvider):
    """OpenAI 임베딩 API (dense만)."""

    def __init__(
        self,
        config: EmbeddingProviderConfig,
        api_key: str = "",
    ) -> None:
        defaults = EMBEDDING_PROVIDER_DEFAULTS.get("openai", {})
        self._model = config.model or defaults.get("default_model", "text-embedding-3-small")
        self._base_url = config.base_url or defaults.get("default_base_url", "https://api.openai.com/v1")
        self._api_key = api_key or config.get_effective_api_key()

        if not self._api_key:
            raise ValueError("OpenAI API 키가 필요합니다. OPENAI_API_KEY 환경변수를 설정하세요.")

        try:
            from openai import OpenAI  # noqa: PLC0415
        except ImportError as exc:
            raise ImportError("openai 패키지가 필요합니다: pip install openai") from exc

        self._client = OpenAI(base_url=self._base_url, api_key=self._api_key)
        logger.info("OpenAIEmbedding 초기화: model=%s", self._model)

    def encode(self, texts: list[str]) -> EmbeddingResult:
        if not texts:
            return EmbeddingResult(dense=[], sparse=None)

        batch_size = 128
        all_dense: list[list[float]] = []

        for i in range(0, len(texts), batch_size):
            batch = texts[i : i + batch_size]
            response = self._client.embeddings.create(
                input=batch,
                model=self._model,
            )
            all_dense.extend(item.embedding for item in response.data)

        return EmbeddingResult(dense=all_dense, sparse=None)


# ---------------------------------------------------------------------------
# JinaEmbedding — Jina API 임베딩 (dense만)
# ---------------------------------------------------------------------------

class JinaEmbedding(EmbeddingProvider):
    """Jina AI 임베딩 API (dense만)."""

    def __init__(
        self,
        config: EmbeddingProviderConfig,
        api_key: str = "",
    ) -> None:
        defaults = EMBEDDING_PROVIDER_DEFAULTS.get("jina", {})
        self._model = config.model or defaults.get("default_model", "jina-embeddings-v3")
        self._base_url = config.base_url or defaults.get("default_base_url", "https://api.jina.ai/v1")
        self._api_key = api_key or config.get_effective_api_key()

        if not self._api_key:
            raise ValueError("Jina API 키가 필요합니다. JINA_API_KEY 환경변수를 설정하세요.")

        try:
            from openai import OpenAI  # noqa: PLC0415
        except ImportError as exc:
            raise ImportError("openai 패키지가 필요합니다: pip install openai") from exc

        self._client = OpenAI(base_url=self._base_url, api_key=self._api_key)
        logger.info("JinaEmbedding 초기화: model=%s", self._model)

    def encode(self, texts: list[str]) -> EmbeddingResult:
        if not texts:
            return EmbeddingResult(dense=[], sparse=None)

        batch_size = 128
        all_dense: list[list[float]] = []

        for i in range(0, len(texts), batch_size):
            batch = texts[i : i + batch_size]
            kwargs: dict = {"input": batch, "model": self._model}
            if "v3" in self._model:
                kwargs["dimensions"] = 1024
            response = self._client.embeddings.create(**kwargs)
            all_dense.extend(item.embedding for item in response.data)

        return EmbeddingResult(dense=all_dense, sparse=None)


# ---------------------------------------------------------------------------
# OllamaEmbedding — Ollama/OpenAI 호환 임베딩 (dense만)
# ---------------------------------------------------------------------------

class OllamaEmbedding(EmbeddingProvider):
    """로컬 Ollama 서버 임베딩 프로바이더 (OpenAI 호환 /v1/embeddings 엔드포인트)."""

    def __init__(
        self,
        config: EmbeddingProviderConfig,
        api_key: str = "",
    ) -> None:
        defaults = EMBEDDING_PROVIDER_DEFAULTS.get("ollama", {})
        self._model = config.model or defaults.get("default_model", "nomic-embed-text")
        self._base_url = config.base_url or defaults.get("default_base_url", "http://localhost:11434")
        self._dim = config.dim or defaults.get("default_dim", 768)
        self._api_key = api_key or config.get_effective_api_key() or "ollama"

        if not self._base_url.rstrip("/").endswith("/v1"):
            self._base_url = self._base_url.rstrip("/") + "/v1"

        try:
            from openai import OpenAI  # noqa: PLC0415
        except ImportError as exc:
            raise ImportError("openai 패키지가 필요합니다: pip install openai") from exc

        self._client = OpenAI(base_url=self._base_url, api_key=self._api_key or "ollama")
        logger.info("OllamaEmbedding 초기화: model=%s, base_url=%s, dim=%d", self._model, self._base_url, self._dim)

    def encode(self, texts: list[str]) -> EmbeddingResult:
        if not texts:
            return EmbeddingResult(dense=[], sparse=None)

        batch_size = 64
        all_dense: list[list[float]] = []

        for i in range(0, len(texts), batch_size):
            batch = texts[i : i + batch_size]
            response = self._client.embeddings.create(
                input=batch,
                model=self._model,
            )
            sorted_data = sorted(response.data, key=lambda x: x.index)
            all_dense.extend(item.embedding for item in sorted_data)

        return EmbeddingResult(dense=all_dense, sparse=None)


# ---------------------------------------------------------------------------
# CohereEmbedding — Cohere API 임베딩 (dense만)
# ---------------------------------------------------------------------------

class CohereEmbedding(EmbeddingProvider):
    """Cohere API 임베딩 프로바이더 (dense만)."""

    MODEL_DIMS = {
        "embed-multilingual-v3.0": 1024,
        "embed-english-v3.0": 1024,
        "embed-multilingual-light-v3.0": 384,
    }

    def __init__(
        self,
        config: EmbeddingProviderConfig,
        api_key: str = "",
    ) -> None:
        defaults = EMBEDDING_PROVIDER_DEFAULTS.get("cohere", {})
        self._model = config.model or defaults.get("default_model", "embed-multilingual-v3.0")
        self._api_key = api_key or config.get_effective_api_key()

        if not self._api_key:
            raise ValueError("Cohere API 키가 필요합니다. COHERE_API_KEY 환경변수를 설정하세요.")

        self._dim = self.MODEL_DIMS.get(self._model, 1024)

        try:
            import cohere  # noqa: PLC0415
        except ImportError as exc:
            raise ImportError("cohere 패키지가 필요합니다: pip install cohere") from exc

        self._client = cohere.ClientV2(api_key=self._api_key)
        logger.info("CohereEmbedding 초기화: model=%s, dim=%d", self._model, self._dim)

    def encode(self, texts: list[str]) -> EmbeddingResult:
        if not texts:
            return EmbeddingResult(dense=[], sparse=None)

        batch_size = 96
        all_dense: list[list[float]] = []

        try:
            import numpy as np  # noqa: PLC0415
        except ImportError:
            np = None  # type: ignore[assignment]

        for i in range(0, len(texts), batch_size):
            batch = texts[i : i + batch_size]
            response = self._client.embed(
                texts=batch,
                model=self._model,
                input_type="search_document",
                embedding_types=["float"],
            )

            if hasattr(response, 'embeddings') and response.embeddings:
                embeddings = response.embeddings
                if hasattr(embeddings, 'float') and embeddings.float:
                    batch_embeddings = embeddings.float
                else:
                    batch_embeddings = embeddings
            else:
                raise ValueError(f"Cohere 응답에서 임베딩을 찾을 수 없음: {response}")

            for emb in batch_embeddings:
                if np is not None and isinstance(emb, np.ndarray):
                    all_dense.append(emb.tolist())
                elif isinstance(emb, list):
                    all_dense.append(emb)
                else:
                    all_dense.append(list(emb))

        return EmbeddingResult(dense=all_dense, sparse=None)


# ---------------------------------------------------------------------------
# 팩토리 — ProviderSettingsStore 기반
# ---------------------------------------------------------------------------

_provider_instance: Optional[EmbeddingProvider] = None


def get_embedding_provider(force_new: bool = False) -> EmbeddingProvider:
    """ProviderSettingsStore에서 현재 임베딩 프로바이더 설정을 읽어 인스턴스 반환.

    Args:
        force_new: True면 기존 인스턴스 무시하고 새로 생성 (테스트용).

    Returns:
        LocalBGEM3, OpenAIEmbedding, JinaEmbedding, OllamaEmbedding,
        또는 CohereEmbedding 인스턴스.
    """
    global _provider_instance

    if _provider_instance is not None and not force_new:
        return _provider_instance

    store = ProviderSettingsStore.get()
    emb_config = store.get_active_embedding_provider()
    provider = emb_config.provider

    if provider == EmbeddingProviderType.LOCAL:
        _provider_instance = LocalBGEM3()
    elif provider == EmbeddingProviderType.OPENAI:
        _provider_instance = OpenAIEmbedding(config=emb_config)
    elif provider == EmbeddingProviderType.JINA:
        _provider_instance = JinaEmbedding(config=emb_config)
    elif provider == EmbeddingProviderType.OLLAMA:
        _provider_instance = OllamaEmbedding(config=emb_config)
    elif provider == EmbeddingProviderType.COHERE:
        _provider_instance = CohereEmbedding(config=emb_config)
    else:
        raise ValueError(
            f"알 수 없는 임베딩 프로바이더: {provider!r}  "
            "('local', 'openai', 'jina', 'ollama', 'cohere' 중 하나)"
        )

    logger.info(
        "임베딩 프로바이더 생성 완료: provider=%s, type=%s",
        provider.value, type(_provider_instance).__name__,
    )
    return _provider_instance


def reset_embedding_provider() -> None:
    """싱글톤 인스턴스 초기화 (설정 변경 시 사용)."""
    global _provider_instance
    _provider_instance = None
