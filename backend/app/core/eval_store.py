"""mAI-Brain — RAG 평가 데이터 저장소

QA pairs와 평가 실행 결과를 JSON 파일로 영속화합니다.
프로덕션 환경에서는 DB로 교체 가능하도록 추상화되어 있습니다.
"""

from __future__ import annotations

import json
import logging
import os
import threading
from pathlib import Path
from typing import Optional

from app.models.evaluation import (
    EvaluationRun,
    EvaluationStats,
    QAPair,
)

logger = logging.getLogger(__name__)

# 기본 데이터 디렉토리
DEFAULT_DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "data", "evaluation")


class EvalStore:
    """JSON 파일 기반 평가 데이터 저장소.

    thread-safe: 모든 쓰기 작업은 lock으로 보호됩니다.
    """

    def __init__(self, data_dir: str = DEFAULT_DATA_DIR) -> None:
        self._data_dir = Path(data_dir)
        self._data_dir.mkdir(parents=True, exist_ok=True)
        self._qa_file = self._data_dir / "qa_pairs.json"
        self._runs_file = self._data_dir / "evaluation_runs.json"
        self._lock = threading.Lock()

        # 인메모리 캐시
        self._qa_pairs: dict[str, QAPair] = {}
        self._runs: dict[str, EvaluationRun] = {}

        self._load_data()

    # ------------------------------------------------------------------ #
    # 내부 유틸
    # ------------------------------------------------------------------ #

    def _load_data(self) -> None:
        """디스크에서 데이터를 로드합니다."""
        self._qa_pairs = self._load_json(self._qa_file, QAPair)
        self._runs = self._load_json(self._runs_file, EvaluationRun)
        logger.info(
            "평가 데이터 로드 완료: %d개 QA pair, %d개 평가 실행",
            len(self._qa_pairs), len(self._runs),
        )

    def _load_dataclass(self, model_cls, data: dict):
        """딕셔너리를 Pydantic 모델로 변환합니다."""
        return model_cls(**data)

    @staticmethod
    def _load_json(filepath: Path, model_cls: type) -> dict:
        """JSON 파일에서 Pydantic 모델 딕셔너리를 로드합니다."""
        if not filepath.exists():
            return {}
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data_list = json.load(f)
            return {item["id"]: model_cls(**item) for item in data_list}
        except (json.JSONDecodeError, KeyError) as exc:
            logger.error("평가 데이터 로드 실패 (%s): %s", filepath, exc)
            return {}

    def _save_json(self, filepath: Path, items: dict) -> None:
        """Pydantic 모델 딕셔너리를 JSON 파일로 저장합니다."""
        data_list = [item.model_dump() for item in items.values()]
        tmp = filepath.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data_list, f, ensure_ascii=False, indent=2)
        tmp.replace(filepath)

    # ------------------------------------------------------------------ #
    # QA Pair CRUD
    # ------------------------------------------------------------------ #

    def create_qa_pair(self, qa: QAPair) -> QAPair:
        """QA pair를 생성합니다."""
        with self._lock:
            self._qa_pairs[qa.id] = qa
            self._save_json(self._qa_file, self._qa_pairs)
        logger.info("QA pair 생성: %s", qa.id)
        return qa

    def get_qa_pair(self, qa_id: str) -> Optional[QAPair]:
        """QA pair를 조회합니다."""
        return self._qa_pairs.get(qa_id)

    def list_qa_pairs(
        self,
        mode: Optional[str] = None,
        tag: Optional[str] = None,
    ) -> list[QAPair]:
        """QA pair 목록을 조회합니다. mode와 tag로 필터링 가능."""
        pairs = list(self._qa_pairs.values())
        if mode:
            pairs = [p for p in pairs if p.mode == mode]
        if tag:
            pairs = [p for p in pairs if tag in p.tags]
        return pairs

    def update_qa_pair(self, qa_id: str, updates: dict) -> Optional[QAPair]:
        """QA pair를 업데이트합니다."""
        with self._lock:
            qa = self._qa_pairs.get(qa_id)
            if qa is None:
                return None
            updated = qa.model_copy(update=updates)
            self._qa_pairs[qa_id] = updated
            self._save_json(self._qa_file, self._qa_pairs)
        logger.info("QA pair 업데이트: %s", qa_id)
        return updated

    def delete_qa_pair(self, qa_id: str) -> bool:
        """QA pair를 삭제합니다."""
        with self._lock:
            if qa_id not in self._qa_pairs:
                return False
            del self._qa_pairs[qa_id]
            self._save_json(self._qa_file, self._qa_pairs)
        logger.info("QA pair 삭제: %s", qa_id)
        return True

    # ------------------------------------------------------------------ #
    # Evaluation Run CRUD
    # ------------------------------------------------------------------ #

    def create_run(self, run: EvaluationRun) -> EvaluationRun:
        """평가 실행을 생성합니다."""
        with self._lock:
            self._runs[run.id] = run
            self._save_json(self._runs_file, self._runs)
        logger.info("평가 실행 생성: %s", run.id)
        return run

    def get_run(self, run_id: str) -> Optional[EvaluationRun]:
        """평가 실행을 조회합니다."""
        return self._runs.get(run_id)

    def update_run(self, run: EvaluationRun) -> EvaluationRun:
        """평가 실행을 업데이트합니다."""
        with self._lock:
            self._runs[run.id] = run
            self._save_json(self._runs_file, self._runs)
        return run

    def list_runs(
        self,
        status: Optional[str] = None,
        limit: int = 20,
        offset: int = 0,
    ) -> list[EvaluationRun]:
        """평가 실행 목록을 조회합니다."""
        runs = sorted(
            self._runs.values(),
            key=lambda r: r.created_at,
            reverse=True,
        )
        if status:
            runs = [r for r in runs if r.status.value == status]
        return runs[offset: offset + limit]

    def get_stats(self) -> EvaluationStats:
        """평가 통계를 계산합니다."""
        all_pairs = list(self._qa_pairs.values())
        all_runs = list(self._runs.values())

        # 완료된 평가만 집계
        completed = [r for r in all_runs if r.status.value == "completed"]

        if not completed:
            return EvaluationStats(
                total_qa_pairs=len(all_pairs),
                total_evaluations=len(all_runs),
            )

        # 최근 10개 평가 ID
        recent_ids = [r.id for r in sorted(completed, key=lambda r: r.created_at, reverse=True)[:10]]

        # 평균 지표 계산
        n = len(completed)
        return EvaluationStats(
            total_qa_pairs=len(all_pairs),
            total_evaluations=len(all_runs),
            avg_precision=sum(r.avg_precision for r in completed) / n,
            avg_recall=sum(r.avg_recall for r in completed) / n,
            avg_mrr=sum(r.avg_mrr for r in completed) / n,
            avg_faithfulness=sum(r.avg_faithfulness for r in completed) / n,
            avg_answer_relevance=sum(r.avg_answer_relevance for r in completed) / n,
            avg_hallucination_score=sum(r.avg_hallucination_score for r in completed) / n,
            recent_evaluations=recent_ids,
        )


# ── 싱글톤 ────────────────────────────────────────────────────────────── #

_eval_store: Optional[EvalStore] = None


def get_eval_store() -> EvalStore:
    """EvalStore 싱글톤 인스턴스 반환."""
    global _eval_store
    if _eval_store is None:
        _eval_store = EvalStore()
    return _eval_store