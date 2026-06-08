"""mAI-Brain — RAG 평가 엔진

QA pairs 대비 RAG 검색·응답 품질을 정량 평가합니다.

핵심 지표:
- Precision@k: 검색 결과 중 기대 출처의 비율
- Recall@k: 기대 출처 중 검색 결과에 포함된 비율
- MRR (Mean Reciprocal Rank): 첫 번째 관련 출처의 순위 역수
- Faithfulness: 검색 컨텍스트에 근거한 답변 비율 (환각 탐지)
- Answer Relevance: 답변이 질문에 얼마나 관련성 있는지
- Hallucination Score: 답변이 컨텍스트에 없는 주장을 포함할 확률
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from app.config import ChatMode, get_settings
from app.core.llm import get_llm_client
from app.core.search import hybrid_search
from app.models.evaluation import (
    QAPair,
    QAPairCreate,
    QAPairUpdate,
    EvaluationRun,
    EvaluationStatus,
    SingleEvalResult,
    EvaluationStats,
)

logger = logging.getLogger(__name__)

# QA pairs 저장 경로
QA_PAIRS_FILE = "data/evaluation/qa_pairs.json"
EVAL_RESULTS_DIR = "data/evaluation/results"


# --------------------------------------------------------------------------- #
# QA Pair 스토어 (JSON 파일 기반)
# --------------------------------------------------------------------------- #

class QAPairStore:
    """QA pairs 파일 기반 저장소."""

    def __init__(self, file_path: str = QA_PAIRS_FILE) -> None:
        self._path = Path(file_path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._pairs: list[QAPair] = self._load()

    def _load(self) -> list[QAPair]:
        if not self._path.exists():
            return []
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
            return [QAPair(**item) for item in data]
        except (json.JSONDecodeError, KeyError) as exc:
            logger.error("QA pairs 로드 실패: %s", exc)
            return []

    def _save(self) -> None:
        self._path.write_text(
            json.dumps(
                [pair.model_dump() for pair in self._pairs],
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

    def list_all(self) -> list[QAPair]:
        return list(self._pairs)

    def get(self, qa_id: str) -> Optional[QAPair]:
        for pair in self._pairs:
            if pair.id == qa_id:
                return pair
        return None

    def add(self, create: QAPairCreate) -> QAPair:
        pair = QAPair(**create.model_dump())
        self._pairs.append(pair)
        self._save()
        return pair

    def update(self, qa_id: str, update: QAPairUpdate) -> Optional[QAPair]:
        pair = self.get(qa_id)
        if pair is None:
            return None
        update_data = update.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            setattr(pair, key, value)
        self._save()
        return pair

    def delete(self, qa_id: str) -> bool:
        original_len = len(self._pairs)
        self._pairs = [p for p in self._pairs if p.id != qa_id]
        if len(self._pairs) < original_len:
            self._save()
            return True
        return False

    def get_by_ids(self, qa_ids: list[str]) -> list[QAPair]:
        return [p for p in self._pairs if p.id in qa_ids]

    def get_by_mode(self, mode: str) -> list[QAPair]:
        return [p for p in self._pairs if p.mode == mode]


# --------------------------------------------------------------------------- #
# 평가 결과 스토어
# --------------------------------------------------------------------------- #

class EvalResultStore:
    """평가 결과 파일 기반 저장소."""

    def __init__(self, results_dir: str = EVAL_RESULTS_DIR) -> None:
        self._dir = Path(results_dir)
        self._dir.mkdir(parents=True, exist_ok=True)

    def save(self, eval_run: EvaluationRun) -> Path:
        file_path = self._dir / f"{eval_run.id}.json"
        file_path.write_text(
            json.dumps(eval_run.model_dump(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return file_path

    def get(self, eval_id: str) -> Optional[EvaluationRun]:
        file_path = self._dir / f"{eval_id}.json"
        if not file_path.exists():
            return None
        try:
            data = json.loads(file_path.read_text(encoding="utf-8"))
            return EvaluationRun(**data)
        except (json.JSONDecodeError, KeyError) as exc:
            logger.error("평가 결과 로드 실패: %s", exc)
            return None

    def list_all(self) -> list[EvaluationRun]:
        results = []
        for file_path in sorted(self._dir.glob("*.json"), reverse=True):
            try:
                data = json.loads(file_path.read_text(encoding="utf-8"))
                results.append(EvaluationRun(**data))
            except (json.JSONDecodeError, KeyError):
                continue
        return results


# --------------------------------------------------------------------------- #
# RAG 평가 엔진
# --------------------------------------------------------------------------- #

class RAGEvaluator:
    """RAG 평가 엔진.

    파이프라인:
    1. 각 QA pair의 질문을 RAG 시스템에 입력
    2. 검색된 출처와 실제 답변 수집
    3. 출처 기반 지표 계산 (Precision@k, Recall@k, MRR)
    4. 답변 품질 지표 계산 (Faithfulness, Relevance, Hallucination)
    """

    def __init__(self) -> None:
        self._qa_store = QAPairStore()
        self._result_store = EvalResultStore()

    @property
    def qa_store(self) -> QAPairStore:
        return self._qa_store

    @property
    def result_store(self) -> EvalResultStore:
        return self._result_store

    def run_evaluation(
        self,
        qa_pair_ids: list[str] | None = None,
        mode: str | None = None,
    ) -> EvaluationRun:
        """평가 실행 (동기)."""
        if qa_pair_ids:
            qa_pairs = self._qa_store.get_by_ids(qa_pair_ids)
        elif mode:
            qa_pairs = self._qa_store.get_by_mode(mode)
        else:
            qa_pairs = self._qa_store.list_all()

        if not qa_pairs:
            raise ValueError("평가할 QA pairs가 없습니다. 먼저 QA pairs를 등록하세요.")

        eval_run = EvaluationRun(
            qa_pair_ids=[p.id for p in qa_pairs],
            mode=mode,
            status=EvaluationStatus.RUNNING,
        )

        results: list[SingleEvalResult] = []
        for qa_pair in qa_pairs:
            try:
                result = self._evaluate_single(qa_pair)
                results.append(result)
            except Exception as exc:
                logger.error("QA pair %s 평가 실패: %s", qa_pair.id, exc)
                results.append(SingleEvalResult(
                    qa_id=qa_pair.id,
                    question=qa_pair.question,
                    expected_answer=qa_pair.expected_answer,
                    actual_answer=f"평가 오류: {exc}",
                ))

        eval_run.results = results
        eval_run.status = EvaluationStatus.COMPLETED
        eval_run.completed_at = datetime.now(timezone.utc).isoformat()
        self._compute_aggregates(eval_run)
        self._result_store.save(eval_run)
        return eval_run

    def _evaluate_single(self, qa_pair: QAPair) -> SingleEvalResult:
        """단일 QA pair 평가."""
        chat_mode = ChatMode(qa_pair.mode) if qa_pair.mode else ChatMode.FACT

        # 1. RAG 검색 실행
        search_result = hybrid_search(query=qa_pair.question, mode=chat_mode)
        retrieved_sources = list({hit.source for hit in search_result.hits if hit.source})

        # 2. LLM 답변 생성
        llm = get_llm_client()
        actual_answer = llm.generate_answer(
            query=qa_pair.question,
            contexts=search_result.hits,
            mode=chat_mode,
        )

        # 3. 출처 기반 지표 계산
        precision = self._compute_precision_at_k(retrieved_sources, qa_pair.expected_sources)
        recall = self._compute_recall_at_k(retrieved_sources, qa_pair.expected_sources)
        mrr = self._compute_mrr(retrieved_sources, qa_pair.expected_sources)

        # 4. 답변 품질 지표 (LLM 기반 자동 평가)
        context_texts = [hit.text for hit in search_result.hits[:5]]
        faithfulness, answer_relevance, hallucination_score = (
            self._compute_quality_metrics(
                qa_pair.question,
                actual_answer,
                qa_pair.expected_answer,
                context_texts,
            )
        )

        return SingleEvalResult(
            qa_id=qa_pair.id,
            question=qa_pair.question,
            expected_answer=qa_pair.expected_answer,
            actual_answer=actual_answer,
            retrieved_sources=retrieved_sources,
            expected_sources=qa_pair.expected_sources,
            precision_at_k=precision,
            recall_at_k=recall,
            mrr=mrr,
            faithfulness=faithfulness,
            answer_relevance=answer_relevance,
            hallucination_score=hallucination_score,
        )

    # ------------------------------------------------------------------- #
    # 출처 기반 지표
    # ------------------------------------------------------------------- #

    @staticmethod
    def _compute_precision_at_k(retrieved: list[str], expected: list[str]) -> float:
        """Precision@k: 검색 결과 중 기대 출처 비율."""
        if not retrieved:
            return 0.0
        if not expected:
            return 1.0
        retrieved_set = {s.lower().strip() for s in retrieved}
        expected_set = {s.lower().strip() for s in expected}
        hits = retrieved_set & expected_set
        return len(hits) / len(retrieved_set)

    @staticmethod
    def _compute_recall_at_k(retrieved: list[str], expected: list[str]) -> float:
        """Recall@k: 기대 출처 중 검색 결과 포함 비율."""
        if not expected:
            return 1.0
        retrieved_set = {s.lower().strip() for s in retrieved}
        expected_set = {s.lower().strip() for s in expected}
        hits = retrieved_set & expected_set
        return len(hits) / len(expected_set)

    @staticmethod
    def _compute_mrr(retrieved: list[str], expected: list[str]) -> float:
        """MRR: 첫 번째 관련 출처의 순위 역수."""
        if not expected or not retrieved:
            return 0.0
        expected_set = {s.lower().strip() for s in expected}
        for rank, source in enumerate(retrieved, 1):
            if source.lower().strip() in expected_set:
                return 1.0 / rank
        return 0.0

    # ------------------------------------------------------------------- #
    # 답변 품질 지표 (LLM 기반)
    # ------------------------------------------------------------------- #

    def _compute_quality_metrics(
        self,
        question: str,
        actual_answer: str,
        expected_answer: str,
        context_texts: list[str],
    ) -> tuple[float, float, float]:
        """LLM을 사용한 답변 품질 평가."""
        if not context_texts:
            return 0.0, 0.0, 1.0

        context = "\n---\n".join(context_texts)

        eval_prompt = f"""당신은 RAG 시스템 응답 품질 평가 전문가입니다. 다음을 정밀하게 평가하세요.

[원본 질문]
{question}

[검색 컨텍스트]
{context[:3000]}

[실제 답변]
{actual_answer}

[기대 정답]
{expected_answer}

다음 세 가지 지표를 0.0~1.0 사이로 평가하세요. 반드시 JSON 형식으로만 답변하세요.

1. faithfulness (충실도): 답변이 검색 컨텍스트에 근거하는 정도. 컨텍스트에 없는 내용을 답변이 포함하면 낮아짐.
2. answer_relevance (관련성): 답변이 원본 질문에 얼마나 직접적으로 답하는지.
3. hallucination_score (환각 점수): 컨텍스트에 없는 정보를 답변이 생성했을 확률. 높을수록 환각 위험.

반드시 아래 형식으로만 출력:
{{"faithfulness": 0.0, "answer_relevance": 0.0, "hallucination_score": 0.0}}"""

        try:
            llm = get_llm_client()
            # 평가 프롬프트는 빈 컨텍스트로 전송 (프롬프트 자체에 컨텍스트 포함)
            dummy_hit = type("obj", (object,), {"text": "", "source": "", "score": 0.0})()
            response = llm.generate_answer(
                query=eval_prompt,
                contexts=[],
                mode=ChatMode.FACT,
            )
            return self._parse_eval_response(response)
        except Exception as exc:
            logger.error("LLM 평가 실패: %s", exc)
            return 0.0, 0.0, 1.0

    @staticmethod
    def _parse_eval_response(response: str) -> tuple[float, float, float]:
        """LLM 평가 응답에서 지표값 파싱."""
        json_match = re.search(r'\{[^}]+\}', response, re.DOTALL)
        if json_match:
            try:
                data = json.loads(json_match.group())
                faithfulness = max(0.0, min(1.0, float(data.get("faithfulness", 0.0))))
                answer_relevance = max(0.0, min(1.0, float(data.get("answer_relevance", 0.0))))
                hallucination_score = max(0.0, min(1.0, float(data.get("hallucination_score", 1.0))))
                return faithfulness, answer_relevance, hallucination_score
            except (json.JSONDecodeError, ValueError) as exc:
                logger.warning("평가 응답 JSON 파싱 실패: %s", exc)
        return 0.0, 0.0, 1.0

    # ------------------------------------------------------------------- #
    # 집계 지표
    # ------------------------------------------------------------------- #

    @staticmethod
    def _compute_aggregates(eval_run: EvaluationRun) -> None:
        if not eval_run.results:
            return
        n = len(eval_run.results)
        eval_run.avg_precision = sum(r.precision_at_k for r in eval_run.results) / n
        eval_run.avg_recall = sum(r.recall_at_k for r in eval_run.results) / n
        eval_run.avg_mrr = sum(r.mrr for r in eval_run.results) / n
        eval_run.avg_faithfulness = sum(r.faithfulness for r in eval_run.results) / n
        eval_run.avg_answer_relevance = sum(r.answer_relevance for r in eval_run.results) / n
        eval_run.avg_hallucination_score = sum(r.hallucination_score for r in eval_run.results) / n

    # ------------------------------------------------------------------- #
    # 통계
    # ------------------------------------------------------------------- #

    def get_stats(self) -> EvaluationStats:
        all_pairs = self._qa_store.list_all()
        all_evals = self._result_store.list_all()

        stats = EvaluationStats(
            total_qa_pairs=len(all_pairs),
            total_evaluations=len(all_evals),
        )

        if all_evals:
            completed = [e for e in all_evals if e.status == EvaluationStatus.COMPLETED]
            if completed:
                stats.avg_precision = sum(e.avg_precision for e in completed) / len(completed)
                stats.avg_recall = sum(e.avg_recall for e in completed) / len(completed)
                stats.avg_mrr = sum(e.avg_mrr for e in completed) / len(completed)
                stats.avg_faithfulness = sum(e.avg_faithfulness for e in completed) / len(completed)
                stats.avg_answer_relevance = sum(e.avg_answer_relevance for e in completed) / len(completed)
                stats.avg_hallucination_score = sum(e.avg_hallucination_score for e in completed) / len(completed)
            stats.recent_evaluations = [e.id for e in all_evals[:10]]

        return stats


# --------------------------------------------------------------------------- #
# 싱글톤
# --------------------------------------------------------------------------- #

_evaluator: Optional[RAGEvaluator] = None


def get_evaluator() -> RAGEvaluator:
    """RAGEvaluator 싱글톤 인스턴스 반환."""
    global _evaluator
    if _evaluator is None:
        _evaluator = RAGEvaluator()
    return _evaluator