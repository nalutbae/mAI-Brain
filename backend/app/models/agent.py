"""mAI-Brain Agent — 에이전트 관련 Pydantic 모델."""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field


# --------------------------------------------------------------------------- #
# 도구 정보
# --------------------------------------------------------------------------- #

class ToolInfo(BaseModel):
    """도구 메타데이터 (프론트엔드 표시용)."""
    name: str = Field(..., description="도구 이름")
    description: str = Field(..., description="도구 설명")
    display_type: str = Field(default="text", description="결과 표시 방식 (text/chart/table/file)")


# --------------------------------------------------------------------------- #
# 요청 모델
# --------------------------------------------------------------------------- #

class AgentRequest(BaseModel):
    """에이전트 채팅 요청.

    POST /api/agent/chat 요청 바디.
    """
    question: str = Field(
        ...,
        min_length=1,
        description="사용자 질문",
    )
    tools: list[str] = Field(
        ...,
        min_length=1,
        description="실행할 도구 이름 목록",
    )
    tool_params: Optional[dict[str, dict[str, Any]]] = Field(
        default=None,
        description="도구별 추가 파라미터 (예: {\"web_search\": {\"query\": \"...\"}})",
    )
    session_id: Optional[str] = Field(
        default=None,
        description="세션 ID",
    )


# --------------------------------------------------------------------------- #
# 응답 모델
# --------------------------------------------------------------------------- #

class ToolResultModel(BaseModel):
    """개별 도구 실행 결과."""
    tool_name: str = Field(..., description="도구 이름")
    success: bool = Field(..., description="실행 성공 여부")
    data: dict[str, Any] = Field(default_factory=dict, description="도구 출력 데이터")
    error: Optional[str] = Field(default=None, description="오류 메시지")
    display_type: str = Field(default="text", description="표시 방식")


class AgentResponse(BaseModel):
    """에이전트 채팅 응답.

    POST /api/agent/chat 응답 바디.
    """
    answer: str = Field(..., description="AI 종합 답변")
    tool_results: list[ToolResultModel] = Field(
        default_factory=list,
        description="각 도구의 실행 결과",
    )
    session_id: Optional[str] = Field(default=None, description="세션 ID")


class AgentToolsResponse(BaseModel):
    """사용 가능한 도구 목록 응답.

    GET /api/agent/tools 응답 바디.
    """
    tools: list[ToolInfo] = Field(..., description="사용 가능한 도구 목록")
