"""mAI-Brain — 교차 문서 추론(Cross-Document Reasoning) 데이터 모델

문서 간 교차 검증, 모순 탐지, 일치 분석 결과를 정의합니다.

핵심 개념:
- SubQuery: 원본 질문에서 분해된 하위 질문
- SubQueryResult: 각 하위 질문의 검색 결과
- DocumentConflict: 문서 간 모순/불일치
- DocumentAgreement: 문서 간 일치/상호 보완
- CrossReasoningReport: 전체 분석 보고서
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field

from app.config import ChatMode


# --------------------------------------------------------------------------- #
# 하위 질문 분해 결과
# --------------------------------------------------------------------------- #

class SubQuery(BaseModel):
    """원본 질문에서 분해된 하위 질문.

    Attributes:
        id: 하위 질문 ID
        query: 분해된 질문 문장
        aspect: 질문 측면 (사실, 원인, 결과, 비교 등)
        order: 원본 질문 내 순서
    """
    id: str = Field(default_factory=lambda: f"sq_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')}")
    query: str = Field(..., description="분해된 하위 질문")
    aspect: str = Field(default="general", description="질문 측면: fact, cause, effect, comparison 등")
    order: int = Field(default=0, description="원본 질문 내 순서")


class SubQueryResult(BaseModel):
    """하위 질문의 검색 결과.

    Attributes:
        sub_query: 하위 질문 정보
        hits: 검색 결과 리스트
        summary: 검색 결과 요약
    """
    sub_query: SubQuery
    hits: list[dict] = Field(default_factory=list, description="SearchHit 딕셔너리 리스트")
    summary: str = Field(default="", description="검색 결과 요약")


# --------------------------------------------------------------------------- #
# 문서 간 관계 분석
# --------------------------------------------------------------------------- #

class ConflictType(str, Enum):
    """문서 간 모순 유형"""
    DIRECT_CONTRADICTION = "direct_contradiction"    # 직접적 모순 (A는 X, B는 NOT X)
    TEMPORAL_CONFLICT = "temporal_conflict"          # 시간적 충돌 (시기별 상이한 주장)
    PARTIAL_DISAGREEMENT = "partial_disagreement"    # 부분적 불일치
    EVIDENCE_GAP = "evidence_gap"                    # 근거 차이 (한쪽엔 있고 다른쪽엔 없음)


class DocumentConflict(BaseModel):
    """문서 간 모순/불일치.

    Attributes:
        conflict_type: 모순 유형
        description: 모순 내용 설명
        document_a: 문서 A 정보 (출처 파일명)
        document_b: 문서 B 정보 (출처 파일명)
        claim_a: 문서 A의 주장
        claim_b: 문서 B의 주장
        severity: 심각도 (low, medium, high)
        resolution_hint: 모순 해소 힌트 (선택)
    """
    conflict_type: ConflictType = Field(default=ConflictType.PARTIAL_DISAGREEMENT)
    description: str = Field(..., description="모순 내용 설명")
    document_a: str = Field(..., description="문서 A 출처 파일명")
    document_b: str = Field(..., description="문서 B 출처 파일명")
    claim_a: str = Field(..., description="문서 A의 주장")
    claim_b: str = Field(..., description="문서 B의 주장")
    severity: str = Field(default="medium", description="심각도: low, medium, high")
    resolution_hint: Optional[str] = Field(default=None, description="모순 해소 힌트")


class DocumentAgreement(BaseModel):
    """문서 간 일치/상호 보완.

    Attributes:
        description: 일치 내용 설명
        documents: 일치하는 문서 출처 리스트
        theme: 공통 주제
        strength: 일치 강도 (weak, moderate, strong)
    """
    description: str = Field(..., description="일치 내용 설명")
    documents: list[str] = Field(..., description="일치하는 문서 출처 리스트")
    theme: str = Field(default="", description="공통 주제")
    strength: str = Field(default="moderate", description="일치 강도: weak, moderate, strong")


# --------------------------------------------------------------------------- #
# 전체 분석 결과
# --------------------------------------------------------------------------- #

class CrossReasoningStatus(str, Enum):
    """교차 추론 상태"""
    PENDING = "pending"
    ANALYZING = "analyzing"
    COMPLETED = "completed"
    FAILED = "failed"


class CrossReasoningRequest(BaseModel):
    """교차 문서 추론 요청.

    Attributes:
        query: 원본 질문
        mode: 채팅 모드 (기본 REASONING)
        session_id: 세션 ID (선택)
        reasoning_strength: 추론 강도 필터 (선택)
        sub_queries: 수동 지정 하위 질문 (선택, 없으면 자동 생성)
    """
    query: str = Field(
        ...,
        min_length=1,
        description="원본 질문",
    )
    mode: ChatMode = Field(
        default=ChatMode.REASONING,
        description="채팅 모드 (기본: reasoning)",
    )
    session_id: Optional[str] = Field(
        default=None,
        description="세션 ID",
    )
    reasoning_strength: Optional[str] = Field(
        default=None,
        description="추론 강도: all, strong, mid, weak",
    )
    sub_queries: Optional[list[str]] = Field(
        default=None,
        description="수동 지정 하위 질문 (없으면 자동 생성)",
    )


class CrossReasoningReport(BaseModel):
    """교차 문서 추론 전체 보고서.

    Attributes:
        id: 보고서 ID
        status: 분석 상태
        original_query: 원본 질문
        sub_queries: 분해된 하위 질문
        sub_query_results: 각 하위 질문의 검색 결과
        conflicts: 발견된 모순
        agreements: 발견된 일치
        synthesis: 종합 분석 결과 (LLM 생성)
        confidence: 추론 신뢰도 (0~1)
        mode: 사용된 채팅 모드
        created_at: 생성 시각
    """
    id: str = Field(
        default_factory=lambda: f"cr_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
    )
    status: CrossReasoningStatus = Field(default=CrossReasoningStatus.PENDING)
    original_query: str = Field(..., description="원본 질문")
    sub_queries: list[SubQuery] = Field(default_factory=list, description="분해된 하위 질문")
    sub_query_results: list[SubQueryResult] = Field(
        default_factory=list, description="각 하위 질문의 검색 결과"
    )
    conflicts: list[DocumentConflict] = Field(
        default_factory=list, description="발견된 문서 간 모순"
    )
    agreements: list[DocumentAgreement] = Field(
        default_factory=list, description="발견된 문서 간 일치"
    )
    synthesis: str = Field(default="", description="종합 분석 결과")
    confidence: float = Field(default=0.0, description="추론 신뢰도 (0~1)")
    mode: ChatMode = Field(default=ChatMode.REASONING)
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


class CrossReasoningResponse(BaseModel):
    """교차 문서 추론 API 응답.

    Attributes:
        report: 분석 보고서
        answer: 최종 답변 (synthesis와 동일, 프론트엔드 호환성)
    """
    report: CrossReasoningReport
    answer: str = Field(default="", description="최종 답변 (synthesis 요약)")