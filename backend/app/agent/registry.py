"""ToolRegistry — 에이전트 도구 등록 및 조회."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Optional

from app.agent.base import BaseTool

if TYPE_CHECKING:
    from app.models.agent import ToolInfo

logger = logging.getLogger(__name__)


class ToolRegistry:
    """도구 레지스트리.

    도구를 이름으로 등록하고 조회합니다. 싱글톤으로 관리합니다.
    """

    def __init__(self) -> None:
        self._tools: dict[str, BaseTool] = {}

    def register(self, tool: BaseTool) -> None:
        """도구를 레지스트리에 등록합니다.

        Args:
            tool: 등록할 도구 인스턴스
        """
        if tool.name in self._tools:
            logger.warning("도구 '%s'가 이미 등록되어 있어 덮어씁니다.", tool.name)
        self._tools[tool.name] = tool
        logger.info("도구 등록: %s (%s)", tool.name, tool.description)

    def get(self, name: str) -> Optional[BaseTool]:
        """도구를 이름으로 조회합니다.

        Args:
            name: 도구 이름

        Returns:
            도구 인스턴스, 없으면 None
        """
        return self._tools.get(name)

    def list_tools(self) -> list["ToolInfo"]:
        """등록된 모든 도구의 목록을 반환합니다.

        Returns:
            ToolInfo 객체 리스트
        """
        from app.models.agent import ToolInfo

        return [
            ToolInfo(
                name=tool.name,
                description=tool.description,
                display_type=tool.display_type,
            )
            for tool in self._tools.values()
        ]

    def get_tool_names(self) -> list[str]:
        """등록된 모든 도구 이름 목록을 반환합니다."""
        return list(self._tools.keys())


# 싱글톤
_registry: Optional[ToolRegistry] = None


def get_tool_registry() -> ToolRegistry:
    """ToolRegistry 싱글톤 인스턴스를 반환합니다."""
    global _registry
    if _registry is None:
        _registry = ToolRegistry()
    return _registry
