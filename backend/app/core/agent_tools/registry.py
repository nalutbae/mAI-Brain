"""ToolRegistry — 에이전트 도구 등록, 조회, 실행."""

from __future__ import annotations

import logging
from typing import Any, Optional

from app.core.agent_tools.base import BaseAgentTool, ToolResult

logger = logging.getLogger(__name__)


class ToolRegistry:
    """도구 레지스트리.

    도구를 이름으로 등록하고 조회/실행합니다. 싱글톤으로 관리합니다.
    """

    def __init__(self) -> None:
        self._tools: dict[str, BaseAgentTool] = {}

    def register(self, tool: BaseAgentTool) -> None:
        """도구를 레지스트리에 등록합니다."""
        if tool.name in self._tools:
            logger.warning("도구 '%s'가 이미 등록되어 있어 덮어씁니다.", tool.name)
        self._tools[tool.name] = tool
        logger.info("도구 등록: %s (%s)", tool.name, tool.description)

    def get(self, name: str) -> Optional[BaseAgentTool]:
        """도구를 이름으로 조회합니다."""
        return self._tools.get(name)

    def list_tools(self) -> list[BaseAgentTool]:
        """등록된 모든 도구 인스턴스 목록을 반환합니다."""
        return list(self._tools.values())

    def list_specs(self) -> list[dict[str, Any]]:
        """등록된 모든 도구의 스펙을 dict 목록으로 반환합니다 (LLM 프롬프트용)."""
        return [tool.to_spec() for tool in self._tools.values()]

    def get_tool_names(self) -> list[str]:
        """등록된 모든 도구 이름 목록을 반환합니다."""
        return list(self._tools.keys())

    async def execute(self, name: str, params: dict[str, Any]) -> ToolResult:
        """도구를 이름으로 찾아 실행합니다.

        Args:
            name: 도구 이름
            params: 실행 파라미터

        Returns:
            실행 결과 (도구를 찾을 수 없으면 실패 결과)
        """
        tool = self._tools.get(name)
        if tool is None:
            return ToolResult(
                tool_name=name,
                success=False,
                error=f"알 수 없는 도구입니다: '{name}' (사용 가능: {', '.join(self._tools.keys())})",
            )

        try:
            return await tool.execute(params)
        except Exception as exc:
            logger.error("도구 '%s' 실행 중 예외: %s", name, exc, exc_info=True)
            return ToolResult(
                tool_name=name,
                success=False,
                error=str(exc),
            )


# 싱글톤
_registry: Optional[ToolRegistry] = None


def get_tool_registry() -> ToolRegistry:
    """ToolRegistry 싱글톤 인스턴스를 반환합니다."""
    global _registry
    if _registry is None:
        _registry = ToolRegistry()
    return _registry
