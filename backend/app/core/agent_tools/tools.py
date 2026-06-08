"""Concrete agent tools — web_search, summarize_document, generate_chart, save_file."""

from __future__ import annotations

import json
import logging
from typing import Any

import httpx

from app.core.agent_tools.base import BaseAgentTool, ToolDisplay, ToolParameter, ToolResult
from app.config import ChatMode

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# WebSearchTool
# --------------------------------------------------------------------------- #

class WebSearchTool(BaseAgentTool):
    """DuckDuckGo 기반 웹 검색 도구."""

    name = "web_search"
    description = "웹에서 최신 정보를 검색합니다. 검색어(query) 파라미터가 필요합니다."
    parameters = [
        ToolParameter(name="query", type="string", description="검색어", required=True),
    ]
    display_type = "text"

    async def execute(self, params: dict[str, Any]) -> ToolResult:
        query = params.get("query", "").strip()
        if not query:
            return ToolResult(
                tool_name=self.name,
                success=False,
                error="검색어(query)가 필요합니다.",
            )

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.get(
                    "https://api.duckduckgo.com/",
                    params={"q": query, "format": "json", "no_html": 1, "skip_disambig": 1},
                )
                response.raise_for_status()
                data = response.json()

            results: list[dict[str, str]] = []
            if data.get("AbstractText"):
                results.append({
                    "title": data.get("AbstractSource", "DuckDuckGo"),
                    "snippet": data["AbstractText"],
                    "url": data.get("AbstractURL", ""),
                })
            for topic in data.get("RelatedTopics", [])[:5]:
                if isinstance(topic, dict) and topic.get("Text"):
                    results.append({
                        "title": topic.get("FirstURL", "").split("/")[-1].replace("_", " ").title() if topic.get("FirstURL") else "관련 주제",
                        "snippet": topic["Text"],
                        "url": topic.get("FirstURL", ""),
                    })

            if not results:
                return ToolResult(
                    tool_name=self.name,
                    success=True,
                    data={"query": query, "results": [], "message": f"'{query}'에 대한 검색 결과가 없습니다."},
                )

            return ToolResult(
                tool_name=self.name,
                success=True,
                data={"query": query, "results": results},
                display=ToolDisplay(
                    type="text",
                    title=f"웹 검색: {query}",
                    data={"results": results},
                ),
            )

        except Exception as exc:
            logger.error("웹 검색 오류: %s", exc)
            return ToolResult(
                tool_name=self.name,
                success=False,
                error=f"웹 검색 중 오류 발생: {exc}",
            )


# --------------------------------------------------------------------------- #
# SummarizeDocumentTool
# --------------------------------------------------------------------------- #

class SummarizeDocumentTool(BaseAgentTool):
    """LLM 기반 문서 요약 도구."""

    name = "summarize_document"
    description = "문서 내용을 요약합니다. 텍스트(text) 파라미터가 필요합니다."
    parameters = [
        ToolParameter(name="text", type="string", description="요약할 문서 텍스트", required=True),
    ]
    display_type = "text"

    async def execute(self, params: dict[str, Any]) -> ToolResult:
        text = params.get("text", "").strip()
        if not text:
            return ToolResult(
                tool_name=self.name,
                success=False,
                error="요약할 텍스트(text)가 필요합니다.",
            )

        max_chars = 8000
        if len(text) > max_chars:
            text = text[:max_chars] + "\n...(생략)"

        try:
            from app.core.llm import get_llm_client

            llm = get_llm_client()
            summary = llm.generate_answer(
                query=f"다음 문서를 3-5문장으로 간결하게 요약해 주세요:\n\n{text}",
                contexts=[],
                mode=ChatMode.SUMMARY,
            )

            return ToolResult(
                tool_name=self.name,
                success=True,
                data={"original_length": len(params.get("text", "")), "summary": summary},
                display=ToolDisplay(
                    type="text",
                    title="문서 요약",
                    data={"summary": summary},
                ),
            )

        except Exception as exc:
            logger.error("문서 요약 오류: %s", exc)
            return ToolResult(
                tool_name=self.name,
                success=False,
                error=f"문서 요약 중 오류 발생: {exc}",
            )


# --------------------------------------------------------------------------- #
# GenerateChartTool
# --------------------------------------------------------------------------- #

class GenerateChartTool(BaseAgentTool):
    """차트 데이터 생성 도구."""

    name = "generate_chart"
    description = "데이터로 차트를 생성합니다. chart_type(bar/line/pie), labels, values 파라미터가 필요합니다."
    parameters = [
        ToolParameter(name="chart_type", type="string", description="차트 타입: bar, line, pie", required=True),
        ToolParameter(name="title", type="string", description="차트 제목", required=False),
        ToolParameter(name="labels", type="array", description="레이블 목록", required=True),
        ToolParameter(name="values", type="array", description="데이터 값 목록", required=True),
    ]
    display_type = "chart"

    async def execute(self, params: dict[str, Any]) -> ToolResult:
        chart_type = params.get("chart_type", "bar")
        title = params.get("title", "차트")
        labels = params.get("labels", [])
        values = params.get("values", [])

        if isinstance(labels, str):
            try:
                labels = json.loads(labels)
            except json.JSONDecodeError:
                labels = [labels]

        if isinstance(values, str):
            try:
                values = json.loads(values)
            except json.JSONDecodeError:
                return ToolResult(
                    tool_name=self.name,
                    success=False,
                    error="values가 올바른 JSON 배열 형식이 아닙니다.",
                )

        if not labels:
            return ToolResult(
                tool_name=self.name,
                success=False,
                error="차트 레이블(labels)이 필요합니다.",
            )

        if not values:
            return ToolResult(
                tool_name=self.name,
                success=False,
                error="차트 데이터(values)가 필요합니다.",
            )

        if chart_type not in ("bar", "line", "pie"):
            return ToolResult(
                tool_name=self.name,
                success=False,
                error=f"지원하지 않는 차트 타입입니다: {chart_type} (bar, line, pie 중 선택)",
            )

        chart_data = {
            "type": chart_type,
            "title": title,
            "labels": labels,
            "datasets": [{"label": title, "data": values}],
        }

        return ToolResult(
            tool_name=self.name,
            success=True,
            data=chart_data,
            display=ToolDisplay(
                type="chart",
                title=title,
                data=chart_data,
            ),
        )


# --------------------------------------------------------------------------- #
# SaveFileTool
# --------------------------------------------------------------------------- #

class SaveFileTool(BaseAgentTool):
    """파일 저장 도구."""

    name = "save_file"
    description = "내용을 파일로 저장합니다. content와 file_path 파라미터가 필요합니다."
    parameters = [
        ToolParameter(name="content", type="string", description="저장할 내용", required=True),
        ToolParameter(name="file_path", type="string", description="저장할 파일 경로", required=True),
    ]
    display_type = "file"

    async def execute(self, params: dict[str, Any]) -> ToolResult:
        content = params.get("content", "")
        file_path = params.get("file_path", "").strip()

        if not content:
            return ToolResult(
                tool_name=self.name,
                success=False,
                error="저장할 내용(content)이 필요합니다.",
            )

        if not file_path:
            return ToolResult(
                tool_name=self.name,
                success=False,
                error="저장할 파일 경로(file_path)가 필요합니다.",
            )

        try:
            from pathlib import Path

            path = Path(file_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")

            return ToolResult(
                tool_name=self.name,
                success=True,
                data={
                    "file_path": str(path.absolute()),
                    "file_size": len(content),
                    "message": f"파일이 저장되었습니다: {path.name}",
                },
                display=ToolDisplay(
                    type="file",
                    title="파일 저장 완료",
                    data={
                        "file_path": str(path.absolute()),
                        "file_size": len(content),
                    },
                ),
            )

        except Exception as exc:
            logger.error("파일 저장 오류: %s", exc)
            return ToolResult(
                tool_name=self.name,
                success=False,
                error=f"파일 저장 중 오류 발생: {exc}",
            )
