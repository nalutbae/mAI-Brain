"""mAI-Brain 에이전트 도구 모듈

ToolRegistry + BaseTool 인터페이스 + 기본 도구 구현체.
채팅에서 @agent 프리픽스 감지 → 에이전트 모드 활성화 →
선택적 도구 호출 → 결과를 응답에 포함.
"""

from app.core.agent_tools.registry import ToolRegistry, get_tool_registry
from app.core.agent_tools.base import BaseTool, ToolResult, ToolParameter
from app.core.agent_tools.web_search import WebSearchTool
from app.core.agent_tools.summarize import SummarizeDocumentTool
from app.core.agent_tools.chart import GenerateChartTool
from app.core.agent_tools.save_file import SaveFileTool

__all__ = [
    "ToolRegistry",
    "get_tool_registry",
    "BaseTool",
    "ToolResult",
    "ToolParameter",
    "WebSearchTool",
    "SummarizeDocumentTool",
    "GenerateChartTool",
    "SaveFileTool",
]