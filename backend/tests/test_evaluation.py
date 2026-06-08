"""mAI-Brain — RAG 평가 메트릭 및 저장소 단위 테스트

검색 품질 메트릭 (Precision@k, Recall@k, MRR)과
평가 데이터 모델의 동작을 검증합니다.
순수 메트릭/모델 테스트는 LLM/Qdrant 의존성 없이 실행 가능합니다.
RAGEvaluator 테스트는 전체 의존성이 설치된 환경에서만 실행됩니다.
"""

import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import pytest

# 순수 메트릭 -- LLM/검색 의존성 없음
from app.core.metrics import (
    extract_score,
    mean_reciprocal_rank,
    precision_at_k,
    recall_at_k,
)
from app.models.evaluation import (
    EvaluationRun,
    EvaluationStatus,
    QAPair,
    QAPairCreate,
    QAPairUpdate,
    SingleEvalResult,
)

# RAGEvaluator는 무거운 의존성(PIL, FlagEmbedding 등)을 필요로 함
# 설치되지 않은 환경에서는 스킵
try:
    from app.core.evaluator import RAGEvaluator
    HAS_EVALUATOR = True
except ImportError:
    HAS_EVALUATOR = False


# ========================================================================== #
# Precision@k 테스트
# ========================================================================== #

class TestPrecisionAtK:
    """Precision@k 메트릭 테스트."""

    def test_perfect_precision(self):
        """모든 검색 결과가 기대 출처에 포함된 경우."""
        retrieved = ["doc1.pdf", "doc2.pdf", "doc3.pdf"]
        expected = ["doc1.pdf", "doc2.pdf"]
        assert precision_at_k(retrieved, expected) == pytest.approx(2 / 3)

    def test_no_match(self):
        """검색 결과에 기대 출처가 전혀 없는 경우."""
        retrieved = ["doc4.pdf", "doc5.pdf"]
        expected = ["doc1.pdf", "doc2.pdf"]
        assert precision_at_k(retrieved, expected) == 0.0

    def test_empty_retrieved(self):
        """검색 결과가 빈 경우."""
        assert precision_at_k([], ["doc1.pdf"]) == 0.0

    def test_empty_expected(self):
        """기대 출처가 빈 경우."""
        assert precision_at_k(["doc1.pdf"], []) == 0.0

    def test_case_insensitive(self):
        """대소문자 구분 없이 매칭."""
        retrieved = ["Doc1.PDF", "doc2.pdf"]
        expected = ["doc1.pdf", "DOC2.PDF"]
        assert precision_at_k(retrieved, expected) == 1.0

    def test_whitespace_stripped(self):
        """공백이 제거되어 매칭."""
        retrieved = ["  doc1.pdf  ", "doc2.pdf"]
        expected = ["doc1.pdf", "doc2.pdf"]
        assert precision_at_k(retrieved, expected) == 1.0


# ========================================================================== #
# Recall@k 테스트
# ========================================================================== #

class TestRecallAtK:
    """Recall@k 메트릭 테스트."""

    def test_perfect_recall(self):
        """모든 기대 출처가 검색 결과에 포함된 경우."""
        retrieved = ["doc1.pdf", "doc2.pdf", "doc3.pdf"]
        expected = ["doc1.pdf", "doc2.pdf"]
        assert recall_at_k(retrieved, expected) == 1.0

    def test_partial_recall(self):
        """일부 기대 출처만 검색 결과에 포함된 경우."""
        retrieved = ["doc1.pdf", "doc3.pdf"]
        expected = ["doc1.pdf", "doc2.pdf"]
        assert recall_at_k(retrieved, expected) == 0.5

    def test_no_match(self):
        """검색 결과에 기대 출처가 전혀 없는 경우."""
        retrieved = ["doc4.pdf", "doc5.pdf"]
        expected = ["doc1.pdf", "doc2.pdf"]
        assert recall_at_k(retrieved, expected) == 0.0

    def test_empty_expected(self):
        """기대 출처가 빈 경우."""
        assert recall_at_k(["doc1.pdf"], []) == 0.0


# ========================================================================== #
# MRR 테스트
# ========================================================================== #

class TestMRR:
    """MRR (Mean Reciprocal Rank) 테스트."""

    def test_first_position(self):
        """첫 번째 결과가 관련 출처인 경우."""
        retrieved = ["doc1.pdf", "doc2.pdf", "doc3.pdf"]
        expected = ["doc1.pdf"]
        assert mean_reciprocal_rank(retrieved, expected) == 1.0

    def test_second_position(self):
        """두 번째 결과가 첫 번째 관련 출처인 경우."""
        retrieved = ["doc4.pdf", "doc1.pdf", "doc2.pdf"]
        expected = ["doc1.pdf"]
        assert mean_reciprocal_rank(retrieved, expected) == pytest.approx(0.5)

    def test_third_position(self):
        """세 번째 결과가 첫 번째 관련 출처인 경우."""
        retrieved = ["doc4.pdf", "doc5.pdf", "doc1.pdf"]
        expected = ["doc1.pdf"]
        assert mean_reciprocal_rank(retrieved, expected) == pytest.approx(1 / 3)

    def test_no_match(self):
        """관련 출처가 검색 결과에 없는 경우."""
        retrieved = ["doc4.pdf", "doc5.pdf"]
        expected = ["doc1.pdf"]
        assert mean_reciprocal_rank(retrieved, expected) == 0.0

    def test_empty_retrieved(self):
        assert mean_reciprocal_rank([], ["doc1.pdf"]) == 0.0

    def test_empty_expected(self):
        assert mean_reciprocal_rank(["doc1.pdf"], []) == 0.0


# ========================================================================== #
# extract_score 테스트
# ========================================================================== #

class TestExtractScore:
    """LLM 응답에서 점수 추출 테스트."""

    def test_pure_number(self):
        assert extract_score("0.85") == pytest.approx(0.85)

    def test_integer_zero(self):
        assert extract_score("0") == 0.0

    def test_integer_one(self):
        assert extract_score("1") == 1.0

    def test_score_in_text(self):
        """숫자가 텍스트 사이에 있는 경우."""
        assert extract_score("충실도: 0.72") == pytest.approx(0.72)

    def test_out_of_range_clamped(self):
        """1.0 초과 값은 1.0으로 클램핑."""
        assert extract_score("1.5") == 1.0

    def test_negative_clamped(self):
        """음수 값은 0.0으로 클램핑."""
        assert extract_score("-0.5") == 0.0

    def test_no_number(self):
        """숫자가 없는 경우."""
        assert extract_score("숫자 없음") == 0.0


# ========================================================================== #
# Pydantic 모델 테스트 (의존성 없음)
# ========================================================================== #

class TestQAPairModel:
    """QAPair Pydantic 모델 테스트."""

    def test_create_qa_pair(self):
        """QA pair 기본 생성."""
        qa = QAPair(
            question="테스트 질문",
            expected_answer="테스트 정답",
            expected_sources=["doc1.pdf"],
            mode="fact",
        )
        assert qa.question == "테스트 질문"
        assert qa.expected_answer == "테스트 정답"
        assert qa.expected_sources == ["doc1.pdf"]
        assert qa.mode == "fact"
        assert qa.id.startswith("qa_")

    def test_create_qa_pair_with_tags(self):
        """태그가 포함된 QA pair."""
        qa = QAPair(
            question="질문",
            expected_answer="정답",
            tags=["정치", "경제"],
        )
        assert qa.tags == ["정치", "경제"]

    def test_qa_pair_create_model(self):
        """QAPairCreate 요청 모델."""
        create = QAPairCreate(
            question="생성 질문",
            expected_answer="생성 정답",
        )
        assert create.question == "생성 질문"
        assert create.mode == "fact"  # 기본값

    def test_qa_pair_update_model(self):
        """QAPairUpdate 부분 업데이트 모델."""
        update = QAPairUpdate(question="수정된 질문")
        assert update.question == "수정된 질문"
        assert update.expected_answer is None  # 수정하지 않음


class TestEvaluationRunModel:
    """EvaluationRun Pydantic 모델 테스트."""

    def test_create_evaluation_run(self):
        """평가 실행 생성."""
        run = EvaluationRun(
            qa_pair_ids=["qa_001", "qa_002"],
            mode="fact",
        )
        assert run.id.startswith("eval_")
        assert run.status == EvaluationStatus.PENDING
        assert run.qa_pair_ids == ["qa_001", "qa_002"]

    def test_single_eval_result(self):
        """단일 평가 결과 생성."""
        result = SingleEvalResult(
            qa_id="qa_001",
            question="질문",
            expected_answer="정답",
            actual_answer="실제 답변",
            precision_at_k=0.8,
            recall_at_k=0.6,
            mrr=0.75,
            faithfulness=0.9,
            answer_relevance=0.85,
            hallucination_score=0.1,
        )
        assert result.qa_id == "qa_001"
        assert result.precision_at_k == 0.8
        assert result.hallucination_score == 0.1


# ========================================================================== #
# RAGEvaluator 테스트 (무거운 의존성 필요)
# ========================================================================== #

@pytest.mark.skipif(not HAS_EVALUATOR, reason="RAGEvaluator 의존성 미설치")
class TestRAGEvaluatorMetrics:
    """RAGEvaluator 내부 메트릭 계산 테스트 (모킹 없이 직접 접근)."""

    def test_precision_at_k_matches_static_method(self):
        """정밀도 @k 모듈 함수와 정적 메서드 일치 확인."""
        retrieved = ["a.pdf", "b.pdf", "c.pdf"]
        expected = ["a.pdf", "b.pdf"]

        module_result = precision_at_k(retrieved, expected)
        class_result = RAGEvaluator._compute_precision_at_k(retrieved, expected)
        assert module_result == pytest.approx(class_result)

    def test_recall_at_k_matches_static_method(self):
        """재현율 @k 모듈 함수와 정적 메서드 일치 확인."""
        retrieved = ["a.pdf", "c.pdf"]
        expected = ["a.pdf", "b.pdf"]

        module_result = recall_at_k(retrieved, expected)
        class_result = RAGEvaluator._compute_recall_at_k(retrieved, expected)
        assert module_result == pytest.approx(class_result)

    def test_mrr_matches_static_method(self):
        """MRR 모듈 함수와 정적 메서드 일치 확인."""
        retrieved = ["c.pdf", "a.pdf", "b.pdf"]
        expected = ["a.pdf"]

        module_result = mean_reciprocal_rank(retrieved, expected)
        class_result = RAGEvaluator._compute_mrr(retrieved, expected)
        assert module_result == pytest.approx(class_result)

    def test_parse_eval_response_valid_json(self):
        """LLM 평가 응답 JSON 파싱."""
        response = '{"faithfulness": 0.85, "answer_relevance": 0.72, "hallucination_score": 0.15}'
        f, r, h = RAGEvaluator._parse_eval_response(response)
        assert f == pytest.approx(0.85)
        assert r == pytest.approx(0.72)
        assert h == pytest.approx(0.15)

    def test_parse_eval_response_invalid_json(self):
        """잘못된 JSON 응답 파싱 - 기본값 반환."""
        response = "평가 결과를 파싱할 수 없습니다"
        f, r, h = RAGEvaluator._parse_eval_response(response)
        assert f == 0.0
        assert r == 0.0
        assert h == 1.0  # 환각 점수 기본값 = 1.0 (위험)

    def test_parse_eval_response_with_surrounding_text(self):
        """JSON 앞뒤에 텍스트가 있는 경우."""
        response = '평가 결과: {"faithfulness": 0.9, "answer_relevance": 0.8, "hallucination_score": 0.1} 완료'
        f, r, h = RAGEvaluator._parse_eval_response(response)
        assert f == pytest.approx(0.9)
        assert r == pytest.approx(0.8)
        assert h == pytest.approx(0.1)

    def test_aggregates_computation(self):
        """집계 지표 계산."""
        run = EvaluationRun(
            qa_pair_ids=["qa_1", "qa_2"],
            status=EvaluationStatus.COMPLETED,
            results=[
                SingleEvalResult(
                    qa_id="qa_1", question="q1", expected_answer="a1", actual_answer="r1",
                    precision_at_k=0.8, recall_at_k=0.6, mrr=0.75,
                    faithfulness=0.9, answer_relevance=0.85, hallucination_score=0.1,
                ),
                SingleEvalResult(
                    qa_id="qa_2", question="q2", expected_answer="a2", actual_answer="r2",
                    precision_at_k=0.6, recall_at_k=0.8, mrr=0.5,
                    faithfulness=0.7, answer_relevance=0.75, hallucination_score=0.3,
                ),
            ],
        )
        RAGEvaluator._compute_aggregates(run)
        assert run.avg_precision == pytest.approx(0.7)  # (0.8 + 0.6) / 2
        assert run.avg_recall == pytest.approx(0.7)   # (0.6 + 0.8) / 2
        assert run.avg_mrr == pytest.approx(0.625)     # (0.75 + 0.5) / 2
        assert run.avg_faithfulness == pytest.approx(0.8)   # (0.9 + 0.7) / 2
        assert run.avg_answer_relevance == pytest.approx(0.8)  # (0.85 + 0.75) / 2
        assert run.avg_hallucination_score == pytest.approx(0.2)  # (0.1 + 0.3) / 2