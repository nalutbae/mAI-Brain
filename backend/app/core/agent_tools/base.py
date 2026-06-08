"""mAI-Brain 에이전트 도구 모듈 — 기본 클래스와 타입."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, Field


class ToolParameter(BaseModel):
    """도구 파라미터 스펙."""
    name: str = Field(..., description="파라미터 이름")
    type: str = Field(default="string", description="파라미터 타입")
    description: str = Field(default="", description="파라미터 설명")
    required: bool = Field(default=False, description="필수 여부")


class ToolDisplay(BaseModel):
    """도구 결과의 프론트엔드 표시 정보."""
    type: str = Field(default="text", description="표시 타입: text, chart, table, file")
    title: str = Field(default="", description="표시 제목")
    data: dict[str, Any] = Field(default_factory=dict, description="표시 데이터")


@dataclass
class ToolResult:
    """도구 실행 결과.

    Attributes:
        tool_name: 실행된 도구 이름
        success: 실행 성공 여부
        data: 도구별 출력 데이터
        error: 실패 시 오류 메시지
        display: 프론트엔드 표시 정보 (선택)
    """
    tool_name: str
    success: bool
    data: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    display: ToolDisplay | None = None


class BaseAgentTool(ABC):
    """에이전트 도구 추상 기본 클래스.

    Attributes:
        name: 도구 이름 (등록 키)
        description: 도구 설명
        parameters: 파라미터 스펙 목록
        display_type: 기본 표시 타입
    """

    name: str
    description: str
    parameters: list[ToolParameter] = []
    display_type: str = "text"

    @abstractmethod
    async def execute(self, params: dict[str, Any]) -> ToolResult:
        """도구를 실행합니다.

        Args:
            params: 도구별 실행 파라미터

        Returns:
            실행 결과
        """
        ...

    def to_spec(self) -> dict[str, Any]:
        """도구 스펙을 dict로 변환 (LLM 프롬프트용)."""
        param_str = ", ".join(
            f"{p.name}: {p.type}" + (" (필수)" if p.required else "")
            for p in self.parameters
        ) if self.parameters else "없음"
        return {
            "name": self.name,
            "description": self.description,
            "parameters": param_str,
        }
