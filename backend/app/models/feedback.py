"""mAI-Brain — Human-in-the-Loop RAG 데이터 모델

사용자 피드백 수집 및 RAG 품질 개선을 위한 데이터 구조.

핵심 개념:
- Feedback: 사용자의 응답 평가 (긍정/부정 + 태그 + 코멘트)
- Correction: 사용자가 제공한 정정 정보 (검색 결과 정정 또는 응답 정정)
- FeedbackStats: 피드백 통계 (금융 지표 수집)
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


# --------------------------------------------------------------------------- #
# 피드백 유형
# --------------------------------------------------------------------------- #

class FeedbackType(str, Enum):
    """피드백 유형."""
    THUMBS_UP = "thumbs_up"       # 긍정 평가
    THUMBS_DOWN = "thumbs_down"   # 부정 평가
    CORRECTION = "correction"       # 정정 제안


class FeedbackTag(str, Enum):
    """피드백 태그 (부정 평가 사유)."""
    IRRELEVANT = "irrelevant"          # 관련 없는 검색 결과
    INCOMPLETE = "incomplete"          # 불완전한 응답
    OUTDATED = "outdated"              # 구식 정보
    HALLUCINATION = "hallucination"    # 환각 (사실과 다름)
    WRONG_SOURCE = "wrong_source"      # 잘못된 출처
    BIASED = "biased"                  # 편향된 응답
    UNCLEAR = "unclear"                # 불분명한 응답


class CorrectionType(str, Enum):
    """정정 유형."""
    RETRIEVAL = "retrieval"  # 검색 결과 정정
    ANSWER = "answer"        # 응답 내용 정정


# --------------------------------------------------------------------------- #
# 피드백 모델
# --------------------------------------------------------------------------- #

class Feedback(BaseModel):
    """사용자 피드백.

    Attributes:
        id: 피드백 고유 ID
        session_id: 세션 ID
        query: 원본 질문
        answer: AI 응답 내용 (요약)
        feedback_type: 긍정/부정/정정
        tags: 피드백 태그 (부정 평가 사유)
        comment: 자유 코멘트
        correction_type: 정정 유형 (검색/응답)
        correction_text: 정정 내용
        created_at: 생성 시각
    """

    id: str = Field(default_factory=lambda: f"fb_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')}")
    session_id: str = ""
    query: str = ""
    answer: str = ""
    feedback_type: FeedbackType
    tags: list[FeedbackTag] = Field(default_factory=list)
    comment: str = ""
    correction_type: Optional[CorrectionType] = None
    correction_text: str = ""
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class FeedbackCreate(BaseModel):
    """피드백 생성 요청."""
    session_id: str = ""
    query: str = ""
    answer: str = ""
    feedback_type: FeedbackType
    tags: list[FeedbackTag] = Field(default_factory=list)
    comment: str = ""
    correction_type: Optional[CorrectionType] = None
    correction_text: str = ""


class FeedbackStats(BaseModel):
    """피드백 통계.

    Attributes:
        total_feedbacks: 전체 피드백 수
        thumbs_up: 긍정 평가 수
        thumbs_down: 부정 평가 수
        corrections: 정정 제안 수
        satisfaction_rate: 만족률 (0.0 ~ 1.0)
        tag_distribution: 태그별 분포
        recent_trend: 최근 트렌드 (긍정/부정 비율)
    """

    total_feedbacks: int = 0
    thumbs_up: int = 0
    thumbs_down: int = 0
    corrections: int = 0
    satisfaction_rate: float = 0.0
    tag_distribution: dict[str, int] = Field(default_factory=dict)
    recent_trend: dict[str, int] = Field(default_factory=dict)


class ImprovementTarget(str, Enum):
    """개선 대상 유형."""
    TOP_K = "top_k"              # 검색 결과 수 (top-k)
    CHUNK_SIZE = "chunk_size"    # 청킹 크기
    EMBEDDING_MODEL = "embedding_model"  # 임베딩 모델
    PROMPT = "prompt"            # 시스템 프롬프트
    REINDEX = "reindex"          # 문서 재인덱싱


class FeedbackSuggestion(BaseModel):
    """자동 개선 제안.

    Attributes:
        id: 제안 ID
        target: 개선 대상 (top_k, chunk_size, embedding_model, prompt, reindex)
        title: 제안 제목
        description: 제안 상세 설명
        priority: 우선순위 (high/medium/low)
        affected_feedback_ids: 관련 피드백 ID 목록
        data: 추가 데이터 (태그 카운트, 만족률 등)
        is_applied: 적용 여부
        created_at: 생성 시각
    """

    id: str = Field(default_factory=lambda: f"sg_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')}")
    target: ImprovementTarget
    title: str
    description: str
    priority: str = "medium"
    affected_feedback_ids: list[str] = Field(default_factory=list)
    data: dict = Field(default_factory=dict)
    is_applied: bool = False
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())