"""mAI-Brain — RAG 평가 데이터 모델

평가 질문-정답 셋(QA pairs)과 평가 결과를 정의합니다.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


# --------------------------------------------------------------------------- #
# QA Pair (평가용 질문-정답 셋)
# --------------------------------------------------------------------------- #

class QAPair(BaseModel):
    """평가용 질문-정답 쌍.

    Attributes:
        id: QA pair 고유 ID
        question: 평가 질문
        expected_answer: 기대 정답
        expected_sources: 기대 출처 파일명 리스트 (선택)
        mode: 채팅 모드 (fact/summary/column/reasoning)
        tags: 태그 (도메인 분류 등)
    """

    id: str = Field(default_factory=lambda: f"qa_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}")
    question: str
    expected_answer: str
    expected_sources: list[str] = Field(default_factory=list)
    mode: str = "fact"
    tags: list[str] = Field(default_factory=list)


class QAPairCreate(BaseModel):
    """QA pair 생성 요청."""
    question: str
    expected_answer: str
    expected_sources: list[str] = Field(default_factory=list)
    mode: str = "fact"
    tags: list[str] = Field(default_factory=list)


class QAPairUpdate(BaseModel):
    """QA pair 수정 요청."""
    question: Optional[str] = None
    expected_answer: Optional[str] = None
    expected_sources: Optional[list[str]] = None
    mode: Optional[str] = None
    tags: Optional[list[str]] = None


# --------------------------------------------------------------------------- #
# 평가 결과
# --------------------------------------------------------------------------- #

class EvaluationStatus(str, Enum):
    """평가 실행 상태."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class SingleEvalResult(BaseModel):
    """단일 QA pair 평가 결과.

    Attributes:
        qa_id: 평가된 QA pair ID
        question: 원본 질문
        expected_answer: 기대 정답
        actual_answer: 실제 생성된 답변
        retrieved_sources: 검색된 출처 리스트
        expected_sources: 기대 출처 리스트
        precision_at_k: Precision@k (검색 출처 정밀도)
        recall_at_k: Recall@k (검색 출재 재현율)
        mrr: Mean Reciprocal Rank
        faithfulness: 충실도 (0~1, 컨텍스트 대비 답변 근거 비율)
        answer_relevance: 답변 관련성 (0~1)
        hallucination_score: 환각 점수 (0~1, 높을수록 환각 의심)
    """

    qa_id: str
    question: str
    expected_answer: str
    actual_answer: str
    retrieved_sources: list[str] = Field(default_factory=list)
    expected_sources: list[str] = Field(default_factory=list)
    precision_at_k: float = 0.0
    recall_at_k: float = 0.0
    mrr: float = 0.0
    faithfulness: float = 0.0
    answer_relevance: float = 0.0
    hallucination_score: float = 0.0


class EvaluationRun(BaseModel):
    """평가 실행 단위.

    Attributes:
        id: 평가 실행 ID
        status: 실행 상태
        qa_pair_ids: 평가에 사용된 QA pair ID 리스트
        mode: 채팅 모드 필터 (선택)
        results: 개별 평가 결과
        created_at: 생성 시각
        completed_at: 완료 시각
        avg_precision: 평균 Precision@k
        avg_recall: 평균 Recall@k
        avg_mrr: 평균 MRR
        avg_faithfulness: 평균 충실도
        avg_answer_relevance: 평균 답변 관련성
        avg_hallucination_score: 평균 환각 점수
    """

    id: str = Field(default_factory=lambda: f"eval_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}")
    status: EvaluationStatus = EvaluationStatus.PENDING
    qa_pair_ids: list[str] = Field(default_factory=list)
    mode: Optional[str] = None
    results: list[SingleEvalResult] = Field(default_factory=list)
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    completed_at: Optional[str] = None

    # 집계 지표
    avg_precision: float = 0.0
    avg_recall: float = 0.0
    avg_mrr: float = 0.0
    avg_faithfulness: float = 0.0
    avg_answer_relevance: float = 0.0
    avg_hallucination_score: float = 0.0


class EvaluationRunRequest(BaseModel):
    """평가 실행 요청.

    Attributes:
        qa_pair_ids: 특정 QA pair ID 리스트 (빈 값이면 전체 실행)
        mode: 채팅 모드 필터 (선택)
    """

    qa_pair_ids: list[str] = Field(default_factory=list)
    mode: Optional[str] = None


class EvaluationStats(BaseModel):
    """평가 통계.

    Attributes:
        total_qa_pairs: 등록된 QA pair 총수
        total_evaluations: 실행된 평가 총수
        avg_precision: 전체 평균 Precision@k
        avg_recall: 전체 평균 Recall@k
        avg_mrr: 전체 평균 MRR
        avg_faithfulness: 전체 평균 충실도
        avg_answer_relevance: 전체 평균 답변 관련성
        avg_hallucination_score: 전체 평균 환각 점수
        recent_evaluations: 최근 평가 IDs (최대 10)
    """

    total_qa_pairs: int = 0
    total_evaluations: int = 0
    avg_precision: float = 0.0
    avg_recall: float = 0.0
    avg_mrr: float = 0.0
    avg_faithfulness: float = 0.0
    avg_answer_relevance: float = 0.0
    avg_hallucination_score: float = 0.0
    recent_evaluations: list[str] = Field(default_factory=list)