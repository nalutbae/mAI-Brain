"""mAI-Brain 에이전트 도구 — ToolRegistry

도구 등록, 조회, 실행을 관리하는 싱글톤 레지스트리.
LLM이 도구를 선택할 수 있도록 스펙 목록도 제공.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from app.core.agent_tools.base import BaseTool, ToolResult

logger = logging.getLogger(__name__)


class ToolRegistry:
    """에이전트 도구 레지스트리

    도구를 이름으로 등록/조회/실행.
    싱글톤 패턴으로 전역에서 하나의 인스턴스만 사용.
    """

    def __init__(self) -> None:
        self._tools: dict[str, BaseTool] = {}

    def register(self, tool: BaseTool) -> None:
        """도구 등록"""
        if tool.name in self._tools:
            logger.warning("도구 '%s'가 이미 등록되어 있어 덮어씁니다.", tool.name)
        self._tools[tool.name] = tool
        logger.info("도구 등록: %s", tool.name)

    def get(self, name: str) -> Optional[BaseTool]:
        """이름으로 도구 조회"""
        return self._tools.get(name)

    def list_tools(self) -> list[BaseTool]:
        """등록된 모든 도구 목록 반환"""
        return list(self._tools.values())

    def list_specs(self) -> list[dict]:
        """모든 도구의 스펙을 dict 목록으로 반환 (API 응답용)"""
        return [tool.to_dict() for tool in self._tools.values()]

    async def execute(self, name: str, params: dict[str, Any]) -> ToolResult:
        """도구 이름으로 실행

        Args:
            name: 도구 이름
            params: 도구 파라미터

        Returns:
            ToolResult: 실행 결과

        Raises:
            KeyError: 등록되지 않은 도구 이름
        """
        tool = self._tools.get(name)
        if tool is None:
            return ToolResult(
                success=False,
                tool_name=name,
                error=f"등록되지 않은 도구: {name}",
            )
        logger.info("도구 실행: %s, 파라미터: %s", name, list(params.keys()))
        return await tool.execute(params)


# --------------------------------------------------------------------------- #
# 싱글톤
# --------------------------------------------------------------------------- #

_registry: Optional[ToolRegistry] = None


def get_tool_registry() -> ToolRegistry:
    """ToolRegistry 싱글톤 반환 (초기화 시 기본 도구 자동 등록)"""
    global _registry
    if _registry is None:
        _registry = ToolRegistry()
        _register_default_tools(_registry)
    return _registry


def _register_default_tools(registry: ToolRegistry) -> None:
    """기본 도구들을 레지스트리에 등록"""
    from app.core.agent_tools.web_search import WebSearchTool
    from app.core.agent_tools.summarize import SummarizeDocumentTool
    from app.core.agent_tools.chart import GenerateChartTool
    from app.core.agent_tools.save_file import SaveFileTool

    registry.register(WebSearchTool())
    registry.register(SummarizeDocumentTool())
    registry.register(GenerateChartTool())
    registry.register(SaveFileTool())