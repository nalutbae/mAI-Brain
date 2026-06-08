"""mAI-Brain — RAG 평가 엔진 단위 테스트

검색 품질 메트릭 (Precision@k, Recall@k, MRR)과
평가 엔진(RAGEvaluator)의 CRUD 동작을 검증합니다.
"""

import json
import os
import tempfile
from datetime import datetime, timezone

import pytest

from app.core.evaluator import RAGEvaluator, QAPairStore, EvalResultStore
from app.core.metrics import precision_at_k, recall_at_k, mean_reciprocal_rank, extract_score
from app.models.evaluation import (
    EvaluationRun,
    EvaluationStatus,
    QAPair,
    QAPairCreate,
    SingleEvalResult,
)


# ── 메트릭 테스트 ──────────────────────────────────────────────────────────

class TestPrecisionAtK:
    """Precision@k 메트릭 테스트."""

    def test_perfect_precision(self):
        result = precision_at_k(
            ["doc1.pdf", "doc2.pdf"],
            ["doc1.pdf", "doc2.pdf"],
        )
        assert result == 1.0

    def test_partial_precision(self):
        result = precision_at_k(
            ["doc1.pdf", "doc3.pdf"],
            ["doc1.pdf", "doc2.pdf"],
        )
        assert result == 0.5

    def test_no_match(self):
        result = precision_at_k(
            ["doc3.pdf", "doc4.pdf"],
            ["doc1.pdf", "doc2.pdf"],
        )
        assert result == 0.0

    def test_empty_retrieved(self):
        result = precision_at_k([], ["doc1.pdf"])
        assert result == 0.0

    def test_case_insensitive(self):
        result = precision_at_k(["Doc1.PDF"], ["doc1.pdf"])
        assert result == 1.0


class TestRecallAtK:
    """Recall@k 메트릭 테스트."""

    def test_perfect_recall(self):
        result = recall_at_k(
            ["doc1.pdf", "doc2.pdf", "doc3.pdf"],
            ["doc1.pdf", "doc2.pdf"],
        )
        assert result == 1.0

    def test_partial_recall(self):
        result = recall_at_k(
            ["doc1.pdf", "doc3.pdf"],
            ["doc1.pdf", "doc2.pdf"],
        )
        assert result == 0.5

    def test_no_match(self):
        result = recall_at_k(
            ["doc3.pdf", "doc4.pdf"],
            ["doc1.pdf", "doc2.pdf"],
        )
        assert result == 0.0

    def test_empty_expected(self):
        result = recall_at_k(["doc1.pdf"], [])
        assert result == 0.0


class TestMRR:
    """MRR (Mean Reciprocal Rank) 테스트."""

    def test_first_rank(self):
        result = mean_reciprocal_rank(
            ["doc1.pdf", "doc2.pdf"],
            ["doc1.pdf"],
        )
        assert result == 1.0

    def test_second_rank(self):
        result = mean_reciprocal_rank(
            ["doc3.pdf", "doc1.pdf"],
            ["doc1.pdf"],
        )
        assert result == 0.5

    def test_no_match(self):
        result = mean_reciprocal_rank(
            ["doc3.pdf", "doc4.pdf"],
            ["doc1.pdf"],
        )
        assert result == 0.0

    def test_empty_inputs(self):
        assert mean_reciprocal_rank([], ["doc1.pdf"]) == 0.0
        assert mean_reciprocal_rank(["doc1.pdf"], []) == 0.0


class TestExtractScore:
    """LLM 응답 점수 추출 테스트."""

    def test_decimal_score(self):
        assert extract_score("0.85") == 0.85

    def test_full_score(self):
        assert extract_score("1.0") == 1.0

    def test_zero_score(self):
        assert extract_score("0.0") == 0.0

    def test_embedded_score(self):
        result = extract_score("The faithfulness score is 0.72")
        assert 0.7 < result < 0.8

    def test_no_score(self):
        assert extract_score("no score here") == 0.0


# ── QAPairStore 테스트 ─────────────────────────────────────────────────────

class TestQAPairStore:
    """QA pair 파일 기반 저장소 테스트."""

    @pytest.fixture
    def store(self, tmp_path):
        qa_file = str(tmp_path / "qa_pairs.json")
        results_dir = str(tmp_path / "results")
        os.makedirs(results_dir, exist_ok=True)
        return QAPairStore(file_path=qa_file)

    def test_add_and_list(self, store):
        create = QAPairCreate(
            question="조선의 수도는?",
            expected_answer="평양",
            expected_sources=["northkorea.pdf"],
            mode="fact",
        )
        pair = store.add(create)
        assert pair.question == "조선의 수도는?"
        assert pair.id.startswith("qa_")

        pairs = store.list_all()
        assert len(pairs) == 1

    def test_get_by_id(self, store):
        create = QAPairCreate(question="Q1", expected_answer="A1")
        pair = store.add(create)
        found = store.get(pair.id)
        assert found is not None
        assert found.question == "Q1"

    def test_delete(self, store):
        create = QAPairCreate(question="Q1", expected_answer="A1")
        pair = store.add(create)
        assert store.delete(pair.id) is True
        assert store.get(pair.id) is None

    def test_get_by_mode(self, store):
        store.add(QAPairCreate(question="Q1", expected_answer="A1", mode="fact"))
        store.add(QAPairCreate(question="Q2", expected_answer="A2", mode="summary"))
        fact_pairs = store.get_by_mode("fact")
        assert len(fact_pairs) == 1


# ── 집계 지표 테스트 ──────────────────────────────────────────────────────

class TestAggregates:
    """평가 결과 집계 지표 테스트."""

    def test_compute_aggregates(self):
        results = [
            SingleEvalResult(
                qa_id="qa_1",
                question="Q1",
                expected_answer="A1",
                actual_answer="A1",
                precision_at_k=1.0,
                recall_at_k=0.5,
                mrr=1.0,
                faithfulness=0.8,
                answer_relevance=0.9,
                hallucination_score=0.1,
            ),
            SingleEvalResult(
                qa_id="qa_2",
                question="Q2",
                expected_answer="A2",
                actual_answer="A2",
                precision_at_k=0.5,
                recall_at_k=1.0,
                mrr=0.5,
                faithfulness=0.6,
                answer_relevance=0.7,
                hallucination_score=0.3,
            ),
        ]

        eval_run = EvaluationRun(
            qa_pair_ids=["qa_1", "qa_2"],
            status=EvaluationStatus.COMPLETED,
            results=results,
        )

        RAGEvaluator._compute_aggregates(eval_run)

        assert eval_run.avg_precision == 0.75
        assert eval_run.avg_recall == 0.75
        assert eval_run.avg_mrr == 0.75
        assert eval_run.avg_faithfulness == 0.7
        assert eval_run.avg_answer_relevance == 0.8
        assert eval_run.avg_hallucination_score == 0.2