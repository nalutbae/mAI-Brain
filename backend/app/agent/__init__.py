"""mAI-Brain Agent Module — 선택적 도구 호출 프레임워크.

@agent 프리픽스로 트리거되는 에이전트 모드에서 사용할 도구들을 정의합니다.
BaseTool 인터페이스, ToolRegistry, 그리고 기본 도구들을 제공합니다.
"""

from app.agent.base import BaseTool, ToolResult
from app.agent.registry import ToolRegistry, get_tool_registry
from app.agent.tools import (
    WebSearchTool,
    SummarizeDocumentTool,
    GenerateChartTool,
    SaveFileTool,
)

__all__ = [
    "BaseTool",
    "ToolResult",
    "ToolRegistry",
    "get_tool_registry",
    "WebSearchTool",
    "SummarizeDocumentTool",
    "GenerateChartTool",
    "SaveFileTool",
]
