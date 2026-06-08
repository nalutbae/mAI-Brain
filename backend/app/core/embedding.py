"""mAI-Brain AI 챗봇 — 임베딩 파이프라인

EmbeddingProvider 추상 인터페이스 기반:
- LocalBGEM3: FlagEmbedding bge-m3 로컬 실행 (dense + sparse)
- APIEmbedding: OpenAI/Cohere API 임베딩 (dense만, sparse=None)
- OllamaEmbedding: Ollama/OpenAI 호환 임베딩 (dense만, sparse=None)

팩토리 함수 get_embedding_provider()가 config.embedding_provider에 따라
적절한 인스턴스를 반환.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional

import numpy as np

from app.config import EmbeddingProviderType, get_settings

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
    """임베딩 제공자 추상 인터페이스.

    개발/운영 환경 전환을 위한 추상화 계층.  encode() 하나만 구현하면 됨.
    """

    @abstractmethod
    def encode(self, texts: list[str]) -> EmbeddingResult:
        """텍스트 리스트 → dense + sparse 임베딩 결과.

        Args:
            texts: 임베딩할 텍스트 리스트.

        Returns:
            EmbeddingResult: dense(필수) + sparse(선택) 벡터.
        """
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
        s = get_settings()
        model_name = model_name or "BAAI/bge-m3"
        self._device = self._detect_device()
        logger.info("LocalBGEM3 초기화: model=%s, device=%s", model_name, self._device)

        # 지연 임포트 — FlagEmbedding은 무거운 패키지
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

        # dense_vecs: numpy.ndarray → list[list[float]]
        dense_vecs = result["dense_vecs"]
        if isinstance(dense_vecs, np.ndarray):
            dense_list = dense_vecs.tolist()
        else:
            dense_list = [v.tolist() if isinstance(v, np.ndarray) else list(v) for v in dense_vecs]

        # lexical_weights: List[Dict[str, float]]
        # bge-m3가 numpy.float16을 반환하므로 순수 float로 변환
        sparse_list = []
        for token_weights in result["lexical_weights"]:
            sparse_list.append({k: float(v) for k, v in token_weights.items()})

        return EmbeddingResult(dense=dense_list, sparse=sparse_list)


# ---------------------------------------------------------------------------
# APIEmbedding — 원격 API 임베딩 (dense만)
# ---------------------------------------------------------------------------

class APIEmbedding(EmbeddingProvider):
    """OpenAI 호환 임베딩 API 기반 (dense만).

    OpenAI, Jina, Cohere 등 OpenAI 호환 엔드포인트를 지원.
    sparse 벡터는 None 반환.  운영 환경에서 Qdrant BM25로 대체.

    지원 프로바이더:
    - OpenAI: base_url=https://api.openai.com/v1, model=text-embedding-3-small
    - Jina:   base_url=https://api.jina.ai/v1, model=jina-embeddings-v3
    """

    # 프로바이더별 기본 설정
    PROVIDER_DEFAULTS = {
        "openai": {
            "base_url": "https://api.openai.com/v1",
            "model": "text-embedding-3-small",
            "env_key": "OPENAI_API_KEY",
            "dim": 1536,
        },
        "jina": {
            "base_url": "https://api.jina.ai/v1",
            "model": "jina-embeddings-v3",
            "env_key": "JINA_API_KEY",
            "dim": 1024,
        },
    }

    def __init__(
        self,
        model: str | None = None,
        base_url: str | None = None,
        api_key: str | None = None,
        provider: str | None = None,
    ) -> None:
        s = get_settings()

        # 프로바이더 자동 감지 (base_url 또는 env_key 기준)
        self._provider = provider or s.embedding_api_provider or "openai"
        defaults = self.PROVIDER_DEFAULTS.get(self._provider, self.PROVIDER_DEFAULTS["openai"])

        self._model = model or s.embedding_api_model or defaults["model"]
        self._base_url = base_url or s.embedding_api_base_url or defaults["base_url"]
        self._api_key = api_key or s.embedding_api_key or s.openai_api_key or ""

        # API 키: 명시값 → 설정값 → 환경변수 자동 탐색
        if not self._api_key:
            import os  # noqa: PLC0415
            for prov_name, prov_defaults in self.PROVIDER_DEFAULTS.items():
                env_val = os.environ.get(prov_defaults["env_key"], "")
                if env_val:
                    self._api_key = env_val
                    if not provider and not s.embedding_api_provider:
                        self._provider = prov_name
                        self._model = model or s.embedding_api_model or prov_defaults["model"]
                        self._base_url = base_url or s.embedding_api_base_url or prov_defaults["base_url"]
                    logger.info("API 키 자동 감지: %s", prov_defaults["env_key"])
                    break

        if not self._api_key:
            raise ValueError(
                "임베딩 API 키가 필요합니다. "
                "OPENAI_API_KEY, JINA_API_KEY 중 하나를 환경변수로 설정하거나 "
                ".env 파일에 EMBEDDING_API_KEY를 추가하세요."
            )

        # 지연 임포트 — openai는 선택 의존성
        try:
            from openai import OpenAI  # noqa: PLC0415
        except ImportError as exc:
            raise ImportError(
                "openai 패키지가 필요합니다: pip install mai-brain-backend[api-embedding]"
            ) from exc

        self._client = OpenAI(base_url=self._base_url, api_key=self._api_key)
        logger.info(
            "APIEmbedding 초기화: provider=%s, model=%s, base_url=%s",
            self._provider, self._model, self._base_url,
        )

    def encode(self, texts: list[str]) -> EmbeddingResult:
        """임베딩 API로 dense 벡터만 생성 (sparse=None)."""
        if not texts:
            return EmbeddingResult(dense=[], sparse=None)

        # Jina v3는 dimensions 파라미터 지원 (1024차원 유지)
        kwargs: dict = {"input": texts, "model": self._model}
        if self._provider == "jina" and "v3" in self._model:
            kwargs["dimensions"] = 1024

        # 배치 처리: 한 번에 너무 많으면 API 에러 → 128개씩 분할
        batch_size = 128
        all_dense: list[list[float]] = []

        for i in range(0, len(texts), batch_size):
            batch = texts[i : i + batch_size]
            kwargs["input"] = batch
            response = self._client.embeddings.create(**kwargs)
            all_dense.extend(item.embedding for item in response.data)

        return EmbeddingResult(dense=all_dense, sparse=None)


# ---------------------------------------------------------------------------
# OllamaEmbedding — Ollama/OpenAI 호환 임베딩 (dense만, sparse=None)
# ---------------------------------------------------------------------------

class OllamaEmbedding(EmbeddingProvider):
    """로컬 Ollama 서버 임베딩 프로바이더 (OpenAI 호환 /v1/embeddings 엔드포인트).

    ⚠️ ollama-cloud는 임베딩 API를 지원하지 않습니다.
    반드시 로컬에 Ollama(https://ollama.ai)를 설치하고 임베딩 모델을 pull해야 합니다.

    사용 방법:
    1. Ollama 설치: https://ollama.ai
    2. 임베딩 모델 pull: ollama pull nomic-embed-text
    3. .env 설정: EMBEDDING_PROVIDER=ollama, OLLAMA_BASE_URL=http://localhost:11434
    4. Qdrant 컬렉션 재인덱싱 필요 (차원이 다르므로)

    주의: 모델 변경 시 Qdrant 컬렉션 차원이 달라지므로 반드시 재인덱싱해야 합니다.

    지원 모델 예:
    - nomic-embed-text (768차원, 기본, 빠르고 가벼움)
    - mxbai-embed-large (1024차원)
    - snowflake-arctic-embed (1024차원)
    """

    def __init__(
        self,
        model: str | None = None,
        base_url: str | None = None,
        api_key: str | None = None,
        dim: int | None = None,
    ) -> None:
        import os  # noqa: PLC0415

        s = get_settings()

        self._model = model or s.ollama_embedding_model or "nomic-embed-text"
        self._base_url = base_url or s.ollama_base_url or "http://localhost:11434"
        self._dim = dim or s.ollama_embedding_dim or 768

        # API 키: 명시값 → 설정 → 환경변수
        self._api_key = api_key or os.environ.get("OLLAMA_API_KEY", "")

        # base_url이 /v1로 끝나지 않으면 보정
        if not self._base_url.rstrip("/").endswith("/v1"):
            self._base_url = self._base_url.rstrip("/") + "/v1"

        # 지연 임포트 — openai는 선택 의존성
        try:
            from openai import OpenAI  # noqa: PLC0415
        except ImportError as exc:
            raise ImportError(
                "openai 패키지가 필요합니다: pip install openai"
            ) from exc

        self._client = OpenAI(
            base_url=self._base_url,
            api_key=self._api_key or "ollama",  # 로컬은 더미값
        )

        logger.info(
            "OllamaEmbedding 초기화: model=%s, base_url=%s, dim=%d, api_key=%s",
            self._model, self._base_url, self._dim,
            "설정됨" if self._api_key else "없음(로컬)",
        )

    def encode(self, texts: list[str]) -> EmbeddingResult:
        """Ollama 임베딩 API로 dense 벡터 생성 (sparse=None)."""
        if not texts:
            return EmbeddingResult(dense=[], sparse=None)

        # 배치 처리: 한 번에 너무 많으면 타임아웃 → 64개씩 분할
        batch_size = 64
        all_dense: list[list[float]] = []

        for i in range(0, len(texts), batch_size):
            batch = texts[i : i + batch_size]
            response = self._client.embeddings.create(
                input=batch,
                model=self._model,
            )
            # 응답을 input 순서대로 정렬
            sorted_data = sorted(response.data, key=lambda x: x.index)
            all_dense.extend(item.embedding for item in sorted_data)

        return EmbeddingResult(dense=all_dense, sparse=None)


# ---------------------------------------------------------------------------
# CohereEmbedding — Cohere API 임베딩 (dense만)
# ---------------------------------------------------------------------------

class CohereEmbedding(EmbeddingProvider):
    """Cohere API 임베딩 프로바이더 (dense만, sparse=None).

    지원 모델:
    - embed-multilingual-v3.0 (1024차원, 다국어 지원)
    - embed-english-v3.0 (1024차원, 영어 특화)
    - embed-multilingual-light-v3.0 (384차원, 가벼운 다국어)

    API 키는 COHERE_API_KEY 환경변수 또는 .env 파일의 cohere_api_key로 설정.
    """

    # 모델별 기본 차원
    MODEL_DIMS = {
        "embed-multilingual-v3.0": 1024,
        "embed-english-v3.0": 1024,
        "embed-multilingual-light-v3.0": 384,
    }

    def __init__(
        self,
        model: str | None = None,
        api_key: str | None = None,
    ) -> None:
        import os  # noqa: PLC0415

        s = get_settings()

        self._model = model or s.embedding_api_model or "embed-multilingual-v3.0"
        self._api_key = api_key or s.cohere_api_key or os.environ.get("COHERE_API_KEY", "")

        if not self._api_key:
            raise ValueError(
                "Cohere API 키가 필요합니다. "
                "COHERE_API_KEY 환경변수를 설정하거나 "
                ".env 파일에 COHERE_API_KEY를 추가하세요."
            )

        # 차원 수 자동 감지
        self._dim = self.MODEL_DIMS.get(self._model, 1024)

        # 지연 임포트 — cohere는 선택 의존성
        try:
            import cohere  # noqa: PLC0415
        except ImportError as exc:
            raise ImportError(
                "cohere 패키지가 필요합니다: pip install cohere"
            ) from exc

        self._client = cohere.ClientV2(api_key=self._api_key)
        logger.info(
            "CohereEmbedding 초기화: model=%s, dim=%d",
            self._model, self._dim,
        )

    def encode(self, texts: list[str]) -> EmbeddingResult:
        """Cohere 임베딩 API로 dense 벡터만 생성 (sparse=None).

        Cohere API는 입력 유형(input_type)을 요구합니다:
        - 검색 쿼리: "search_query"
        - 문서 인덱싱: "search_document"
        현재는 문서 인덱싱으로 통일 (배치 검색 시에도 문서 임베딩 사용).
        """
        if not texts:
            return EmbeddingResult(dense=[], sparse=None)

        # 배치 처리: Cohere API는 한 번에 최대 96개 지원
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

            # 응답에서 임베딩 추출
            if hasattr(response, 'embeddings') and response.embeddings:
                embeddings = response.embeddings
                if hasattr(embeddings, 'float') and embeddings.float:
                    batch_embeddings = embeddings.float
                else:
                    # v1 응답 형식
                    batch_embeddings = embeddings
            else:
                raise ValueError(f"Cohere 응답에서 임베딩을 찾을 수 없음: {response}")

            # numpy → list 변환
            for emb in batch_embeddings:
                if np is not None and isinstance(emb, np.ndarray):
                    all_dense.append(emb.tolist())
                elif isinstance(emb, list):
                    all_dense.append(emb)
                else:
                    all_dense.append(list(emb))

        return EmbeddingResult(dense=all_dense, sparse=None)


# ---------------------------------------------------------------------------
# 팩토리
# ---------------------------------------------------------------------------

_provider_instance: Optional[EmbeddingProvider] = None


def get_embedding_provider(force_new: bool = False) -> EmbeddingProvider:
    """설정에 따라 적절한 EmbeddingProvider 인스턴스 반환 (싱글톤).

    Args:
        force_new: True면 기존 인스턴스 무시하고 새로 생성 (테스트용).

    Returns:
        LocalBGEM3, APIEmbedding, OllamaEmbedding, 또는 CohereEmbedding 인스턴스.
    """
    global _provider_instance

    if _provider_instance is not None and not force_new:
        return _provider_instance

    s = get_settings()
    provider = s.embedding_provider

    if provider == EmbeddingProviderType.LOCAL:
        _provider_instance = LocalBGEM3()
    elif provider == EmbeddingProviderType.API:
        _provider_instance = APIEmbedding()
    elif provider == EmbeddingProviderType.OLLAMA:
        _provider_instance = OllamaEmbedding()
    elif provider == EmbeddingProviderType.COHERE:
        _provider_instance = CohereEmbedding()
    else:
        raise ValueError(
            f"알 수 없는 EMBEDDING_PROVIDER: {provider!r}  "
            "('local', 'api', 'ollama', 'cohere' 중 하나)"
        )

    return _provider_instance


def reset_embedding_provider() -> None:
    """싱글톤 인스턴스 초기화 (테스트/설정 변경 시 사용)."""
    global _provider_instance
    _provider_instance = None