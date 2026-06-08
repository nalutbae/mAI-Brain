"""BaseTool — 에이전트 도구 추상 기본 클래스."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ToolResult:
    """도구 실행 결과.

    Attributes:
        tool_name: 실행된 도구 이름
        success: 실행 성공 여부
        data: 도구별 출력 데이터 (차트 데이터, 검색 결과 등)
        error: 실패 시 오류 메시지
        display_type: 프론트엔드에서의 표시 방식 ("text", "chart", "table", "file")
    """

    tool_name: str
    success: bool
    data: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    display_type: str = "text"


class BaseTool(ABC):
    """에이전트 도구 추상 기본 클래스.

    모든 도구는 이 클래스를 상속하여 구현합니다.

    Attributes:
        name: 도구 이름 (등록 키)
        description: 도구 설명 (프론트엔드 툴팁 등에 사용)
        display_type: 결과 표시 방식
    """

    name: str
    description: str
    display_type: str = "text"

    @abstractmethod
    async def execute(self, params: dict[str, Any]) -> ToolResult:
        """도구를 실행합니다.

        Args:
            params: 도구별 실행 파라미터 (query, text, title, file_path 등)

        Returns:
            실행 결과
        """
        ...
