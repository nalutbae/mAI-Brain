"""mAI-Brain 에이전트 도구 — 기본 클래스 및 타입 정의

BaseTool 인터페이스, ToolResult, ToolParameter 데이터 모델.
모든 도구는 BaseTool을 상속하여 name/description/parameters/execute를 구현해야 함.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


# --------------------------------------------------------------------------- #
# 도구 파라미터 정의
# --------------------------------------------------------------------------- #

class ParameterType(str, Enum):
    """도구 파라미터 타입"""
    STRING = "string"
    NUMBER = "number"
    BOOLEAN = "boolean"
    ARRAY = "array"
    OBJECT = "object"


class ToolParameter(BaseModel):
    """도구 파라미터 스펙"""
    name: str = Field(..., description="파라미터 이름")
    type: ParameterType = Field(..., description="파라미터 타입")
    description: str = Field(..., description="파라미터 설명")
    required: bool = Field(default=True, description="필수 여부")
    default: Optional[Any] = Field(default=None, description="기본값")


# --------------------------------------------------------------------------- #
# 도구 실행 결과
# --------------------------------------------------------------------------- #

class ToolResult(BaseModel):
    """도구 실행 결과

    성공/실패 여부, 결과 데이터, 시각화 정보(차트/표)를 포함.
    프론트엔드는 result_type에 따라 결과를 렌더링.
    """
    success: bool = Field(..., description="실행 성공 여부")
    tool_name: str = Field(..., description="실행된 도구 이름")
    data: Any = Field(default=None, description="결과 데이터")
    error: Optional[str] = Field(default=None, description="오류 메시지")
    display: Optional[ToolDisplay] = Field(default=None, description="시각화 정보")

    class ToolDisplay(BaseModel):
        """프론트엔드 렌더링을 위한 시각화 메타데이터"""
        type: str = Field(..., description="표시 타입: text, table, chart, file")
        title: Optional[str] = Field(default=None, description="표시 제목")
        columns: Optional[list[str]] = Field(default=None, description="표 컬럼 (table 타입)")
        chart_type: Optional[str] = Field(default=None, description="차트 타입: bar, line, pie, scatter")
        chart_data: Optional[dict] = Field(default=None, description="차트 데이터")
        file_path: Optional[str] = Field(default=None, description="저장된 파일 경로 (file 타입)")


# --------------------------------------------------------------------------- #
# 도구 기본 클래스
# --------------------------------------------------------------------------- #

class BaseTool(ABC):
    """에이전트 도구 기본 클래스

    모든 도구는 이 클래스를 상속하여 구현:
    - name: 도구 식별자 (예: "web_search")
    - description: LLM이 도구를 선택할 때 참고하는 설명
    - parameters: 도구가 받는 파라미터 스펙
    - execute(params): 실제 도구 실행 로직
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """도구 이름 (고유 식별자)"""
        ...

    @property
    @abstractmethod
    def description(self) -> str:
        """도구 설명 (LLM이 도구 선택 시 참고)"""
        ...

    @property
    @abstractmethod
    def parameters(self) -> list[ToolParameter]:
        """도구 파라미터 스펙 목록"""
        ...

    async def execute(self, params: dict[str, Any]) -> ToolResult:
        """도구 실행

        Args:
            params: 파라미터 이름 → 값 매핑

        Returns:
            ToolResult: 실행 결과
        """
        try:
            # 필수 파라미터 검증
            validated = self._validate_params(params)
            result = await self._run(validated)
            return result
        except Exception as exc:
            return ToolResult(
                success=False,
                tool_name=self.name,
                error=f"{self.name} 실행 오류: {exc}",
            )

    def _validate_params(self, params: dict[str, Any]) -> dict[str, Any]:
        """필수 파라미터 검증 및 기본값 적용"""
        validated = {}
        for param in self.parameters:
            if param.name in params:
                validated[param.name] = params[param.name]
            elif param.required:
                raise ValueError(f"필수 파라미터 누락: {param.name}")
            elif param.default is not None:
                validated[param.name] = param.default
        return validated

    @abstractmethod
    async def _run(self, params: dict[str, Any]) -> ToolResult:
        """실제 도구 실행 로직 (서브클래스에서 구현)"""
        ...

    def to_dict(self) -> dict:
        """도구 스펙을 딕셔너리로 변환 (API 응답 및 LLM 프롬프트용)"""
        return {
            "name": self.name,
            "description": self.description,
            "parameters": [p.model_dump() for p in self.parameters],
        }