"""mAI-Brain AI 챗봇 — 채팅 관련 Pydantic 모델

채팅 요청, 검색 결과, LLM 응답, 채팅 API 응답 모델을 정의합니다.
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

from app.config import ChatMode, ReasoningStrength


# --------------------------------------------------------------------------- #
# 검색 결과
# --------------------------------------------------------------------------- #

class SearchHit(BaseModel):
    """개별 검색 결과 항목"""
    text: str = Field(..., description="청크 원문")
    source: str = Field(..., description="출처 파일명")
    score: float = Field(..., description="검색 점수 (RRF)")
    chunk_index: Optional[int] = Field(
        default=None,
        description="문서 내 청크 순서",
    )
    page: Optional[int] = Field(
        default=None,
        description="원본 문서 페이지 번호",
    )


# --------------------------------------------------------------------------- #
# 요청 모델
# --------------------------------------------------------------------------- #

class ChatRequest(BaseModel):
    """채팅 요청

    POST /api/chat 요청 바디.
    """
    question: str = Field(
        ...,
        min_length=1,
        description="사용자 질문 (조선어/한국어/영문 등 무관)",
    )
    mode: ChatMode = Field(
        default=ChatMode.FACT,
        description="채팅 모드: fact(팩트,5), summary(요약,8), column(컬럼,18), reasoning(추론,15)",
    )
    session_id: Optional[str] = Field(
        default=None,
        description="세션 ID (기존 대화를 이어갈 때 전달)",
    )
    reasoning_strength: Optional[ReasoningStrength] = Field(
        default=None,
        description="추론 강도 필터 (추론 모드에서만 사용): all, strong, mid, weak",
    )


# --------------------------------------------------------------------------- #
# 응답 모델
# --------------------------------------------------------------------------- #

class ChatResponse(BaseModel):
    """채팅 응답

    POST /api/chat 응답 바디.
    """
    answer: str = Field(..., description="AI 답변 (한국어)")
    sources: Optional[list[SearchHit]] = Field(
        default=None,
        description="검색 출처 (출처 요청 시에만 포함)",
    )
    mode: ChatMode = Field(..., description="사용된 검색 모드")
    session_id: str = Field(..., description="세션 ID")


class ChatHistoryItem(BaseModel):
    """대화 기록 개별 항목"""
    role: str = Field(..., description="user 또는 assistant")
    content: str = Field(..., description="메시지 내용")
    mode: Optional[ChatMode] = Field(default=None, description="채팅 모드")
    sources: Optional[list[SearchHit]] = Field(
        default=None,
        description="검색 출처 (assistant 메시지에만)",
    )
    created_at: datetime = Field(..., description="메시지 생성 시각")