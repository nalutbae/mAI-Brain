"""mAI-Brain AI 챗봇 — 세션 관련 Pydantic 모델

세션 생성, 조회, 대화 내역 응답 모델을 정의합니다.
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


# --------------------------------------------------------------------------- #
# 요청 모델
# --------------------------------------------------------------------------- #

class SessionCreateRequest(BaseModel):
    """새 세션 생성 요청

    POST /api/sessions 요청 바디.
    """
    title: Optional[str] = Field(
        default=None,
        description="세션 제목 (미지정 시 자동 생성)",
    )


# --------------------------------------------------------------------------- #
# 응답 모델
# --------------------------------------------------------------------------- #

class SessionResponse(BaseModel):
    """세션 생성/조회 응답"""
    session_id: str = Field(..., description="세션 식별자 (UUID)")
    title: str = Field(..., description="세션 제목")
    created_at: datetime = Field(..., description="세션 생성 시각")
    updated_at: datetime = Field(..., description="마지막 대화 시각")
    message_count: int = Field(
        default=0,
        description="대화 메시지 수",
    )


class SessionListResponse(BaseModel):
    """세션 목록 응답"""
    sessions: list[SessionResponse] = Field(
        default_factory=list,
        description="세션 목록 (최근순)",
    )
    total: int = Field(..., description="전체 세션 수")


class SessionDetailResponse(BaseModel):
    """세션 상세 응답 (대화 내역 포함)"""
    session_id: str = Field(..., description="세션 식별자")
    title: str = Field(..., description="세션 제목")
    created_at: datetime = Field(..., description="세션 생성 시각")
    updated_at: datetime = Field(..., description="마지막 대화 시각")
    messages: list[dict] = Field(
        default_factory=list,
        description="대화 메시지 목록",
    )