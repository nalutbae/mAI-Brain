"""mAI-Brain AI 챗봇 — 리랭커 모듈

검색 결과를 질문과의 관련성 순으로 재정렬합니다.

설계:
- FlagEmbedding bge-reranker-v2-m3 모델 사용 (bge-m3 임베딩과 동일 계열)
- MPS(Apple Silicon) / CUDA(NVIDIA) 자동 감지 및 가속
- 리랭커가 비활성화된 경우 투과(pass-through) 처리
- 초기 검색에서 더 많은 후보를 가져온 후 리랭크하여 최종 k개 선택

파이프라인:
  hybrid_search(top_k_initial=20~30) → rerank() → top_k_final(5~12)

지원 모델:
- BAAI/bge-reranker-v2-m3 (기본, 한국어+다국어)
- FlagEmbedding의 FlagReranker 래퍼 사용
"""

from __future__ import annotations

import logging
from typing import Optional

from app.config import ChatMode, get_settings
from app.models.chat import SearchHit

logger = logging.getLogger(__name__)


class Reranker:
    """검색 결과 재정렬 (re-ranking) 모듈.

    bge-reranker-v2-m3 모델을 사용하여 질문-문서 쌍의 관련성 점수를
    재계산하고, 점수 순으로 결과를 재정렬합니다.
    """

    def __init__(self, model_name: str | None = None) -> None:
        self._model_name = model_name or "BAAI/bge-reranker-v2-m3"
        self._device = self._detect_device()
        self._model = None
        self._initialized = False
        logger.info(
            "Reranker 초기화 예약: model=%s, device=%s (지연 로드)",
            self._model_name, self._device,
        )

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

    def _ensure_model(self) -> None:
        """모델 지연 로드 (첫 호출 시에만 초기화)."""
        if self._initialized:
            return

        try:
            from FlagEmbedding import FlagReranker  # noqa: PLC0415
        except ImportError:
            raise ImportError(
                "FlagEmbedding 패키지가 필요합니다: pip install FlagEmbedding"
            )

        logger.info(
            "Reranker 모델 로드 시작: %s (device=%s)",
            self._model_name, self._device,
        )
        self._model = FlagReranker(
            self._model_name,
            use_fp16=True,
            device=self._device,
        )
        self._initialized = True
        logger.info("Reranker 모델 로드 완료")

    def rerank(
        self,
        query: str,
        hits: list[SearchHit],
        top_k: int | None = None,
        min_score: float = 0.0,
    ) -> list[SearchHit]:
        """검색 결과를 리랭크합니다.

        Args:
            query: 사용자 질문
            hits: 하이브리드 검색 결과 (initial top_k)
            top_k: 리랭크 후 반환할 최대 결과 수 (None이면 모드별 기본값)
            min_score: 최소 관련성 점수 (이 이하면 제외)

        Returns:
            리랭크된 SearchHit 리스트 (점수 내림차순)
        """
        if not hits:
            return hits

        self._ensure_model()

        # 질문-문서 쌍 구성
        pairs = [(query, hit.text) for hit in hits]

        # 리랭크 점수 계산
        logger.info("리랭크 시작: %d개 문서, query='%s'", len(pairs), query[:50])
        raw_scores = self._model.compute_score(pairs)  # type: ignore[union-attr]

        # FlagReranker는 float, list[float], ndarray 등 다양한 타입 반환 가능
        import numpy as np  # noqa: PLC0415

        if isinstance(raw_scores, np.ndarray):
            scores_list: list[float] = raw_scores.tolist()  # type: ignore[assignment]
        elif isinstance(raw_scores, list):
            scores_list = [float(s) for s in raw_scores]
        elif isinstance(raw_scores, (int, float)):
            scores_list = [float(raw_scores)]
        else:
            scores_list = [float(raw_scores)]  # type: ignore[arg-type]

        # 점수 반영하여 SearchHit 재구성
        reranked: list[SearchHit] = []
        for hit, score in zip(hits, scores_list):
            reranked.append(SearchHit(
                text=hit.text,
                source=hit.source,
                score=float(score),  # 리랭커 점수로 덮어씀
                chunk_index=hit.chunk_index,
                page=hit.page,
            ))

        # 점수 내림차순 정렬
        reranked.sort(key=lambda h: h.score, reverse=True)

        # 최소 점수 필터링
        if min_score > 0:
            reranked = [h for h in reranked if h.score >= min_score]

        # top-k 잘라내기
        if top_k is not None and top_k > 0:
            reranked = reranked[:top_k]

        logger.info(
            "리랭크 완료: %d→%d개 결과 (min_score=%.2f)",
            len(hits), len(reranked), min_score,
        )
        return reranked

    @property
    def is_initialized(self) -> bool:
        """모델이 로드되었는지 여부."""
        return self._initialized

    def reset(self) -> None:
        """모델 해제 (메모리 절약)."""
        if self._model is not None:
            del self._model
            self._model = None
            self._initialized = False
            logger.info("Reranker 모델 해제 완료")


# --------------------------------------------------------------------------- #
# 모드별 리랭크 설정
# --------------------------------------------------------------------------- #

# 리랭커 입력용 초기 검색 후보 수 (기존 top_k보다 많이 가져와야 효과적)
RERANK_INITIAL_K = {
    ChatMode.FACT: 20,
    ChatMode.SUMMARY: 25,
    ChatMode.COLUMN: 30,
    ChatMode.REASONING: 30,
    ChatMode.CREATIVE: 0,  # 검색 안 함
}

# 리랭크 후 최종 반환 수 (기존 top_k와 동일 또는 약간 적게)
RERANK_FINAL_K = {
    ChatMode.FACT: 5,
    ChatMode.SUMMARY: 8,
    ChatMode.COLUMN: 12,
    ChatMode.REASONING: 10,
    ChatMode.CREATIVE: 0,
}


# --------------------------------------------------------------------------- #
# 싱글톤
# --------------------------------------------------------------------------- #

_reranker_instance: Optional[Reranker] = None


def get_reranker() -> Reranker | None:
    """리랭커 인스턴스 반환.

    설정에서 reranker_enabled=False면 None을 반환하여
    검색 결과를 그대로 통과시킵니다.
    """
    global _reranker_instance

    settings = get_settings()

    if not settings.reranker_enabled:
        logger.debug("리랭커 비활성화 — 검색 결과를 그대로 반환")
        return None

    if _reranker_instance is None:
        model_name = settings.reranker_model or None
        _reranker_instance = Reranker(model_name=model_name)

    return _reranker_instance


def reset_reranker() -> None:
    """리랭커 싱글톤 초기화 (설정 변경 시 사용)."""
    global _reranker_instance
    if _reranker_instance is not None:
        _reranker_instance.reset()
    _reranker_instance = None