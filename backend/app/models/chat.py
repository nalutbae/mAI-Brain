"""mAI-Brain AI 챗봇 — 채팅 관련 Pydantic 모델

채팅 요청, 검색 결과, LLM 응답, 채팅 API 응답, 에이전트 모델을 정의합니다.
"""

from datetime import datetime
from typing import Any, Optional

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
        description="사용자 질문 (한국어/영문 등 무관)",
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
    workspace_id: Optional[str] = Field(
        default=None,
        description="워크스페이스 ID (커스텀 프롬프트 사용 시 전달)",
    )
    query_expansion: Optional[str] = Field(
        default=None,
        description="쿼리 확장 전략: multi_query, hyde, korean_synonyms, auto, none",
    )
    service_mode: bool = Field(
        default=False,
        description="서비스 챗봇 모드: true 시 인용 마커/출처 생략, 친근한 문체로 응답",
    )


# --------------------------------------------------------------------------- #
# 응답 모델
# --------------------------------------------------------------------------- #

class Citation(BaseModel):
    """인라인 인용 정보 — 답변 텍스트의 [[N]] 마커와 매핑"""
    index: int = Field(..., description="인용 번호 (1부터 시작)")
    source: str = Field(..., description="출처 파일명")
    page: Optional[int] = Field(default=None, description="원본 문서 페이지 번호")
    text: str = Field(..., description="인용된 청크 원문 (최대 300자)")
    score: float = Field(default=0.0, description="검색 점수")


class ChatResponse(BaseModel):
    """채팅 응답

    POST /api/chat 응답 바디.
    """
    answer: str = Field(..., description="AI 답변 (한국어)")
    sources: Optional[list[SearchHit]] = Field(
        default=None,
        description="검색 출처 (출처 요청 시에만 포함)",
    )
    citations: Optional[list[Citation]] = Field(
        default=None,
        description="인라인 인용 목록 — [[N]] 마커와 매핑",
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


# --------------------------------------------------------------------------- #
# 에이전트 모드 모델
# --------------------------------------------------------------------------- #

class AgentStep(BaseModel):
    """에이전트 실행 단계"""
    type: str = Field(
        ...,
        description="단계 타입: thinking, tool_call, tool_result",
    )
    content: str = Field(..., description="단계 내용")
    tool_name: Optional[str] = Field(
        default=None,
        description="도구 이름 (tool_call, tool_result 타입에만)",
    )
    tool_success: Optional[bool] = Field(
        default=None,
        description="도구 실행 성공 여부 (tool_result 타입에만)",
    )
    tool_display: Optional[dict] = Field(
        default=None,
        description="도구 결과 시각화 정보 (tool_result 타입에만)",
    )


class AgentToolCall(BaseModel):
    """에이전트 도구 호출 기록 (API 응답 요약용)"""
    tool_name: str = Field(..., description="도구 이름")
    parameters: dict = Field(default={}, description="도구 파라미터")
    success: bool = Field(..., description="실행 성공 여부")


class AgentResponse(BaseModel):
    """에이전트 모드 응답"""
    answer: str = Field(..., description="에이전트 최종 답변 (한국어)")
    steps: list[AgentStep] = Field(
        default=[],
        description="에이전트 실행 단계 (사고 과정, 도구 호출 등)",
    )
    tool_calls: list[AgentStep] = Field(
        default=[],
        description="도구 호출 단계만 필터링 (프론트엔드 표시용)",
    )
    is_agent: bool = Field(default=True, description="에이전트 모드 응답 여부")


class AgentToolSpec(BaseModel):
    """에이전트 도구 스펙 (API 응답용)"""
    name: str = Field(..., description="도구 이름")
    description: str = Field(..., description="도구 설명")
    parameters: list[dict] = Field(default=[], description="파라미터 스펙 목록")