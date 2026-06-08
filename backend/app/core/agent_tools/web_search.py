"""mAI-Brain 에이전트 도구 — 웹 검색

웹 검색 도구. DuckDuckGo HTML 검색을 사용하여 키워드 기반 검색 결과를 반환.
외부 API 키 없이 동작하며, 검색 결과를 프론트엔드에 표 형태로 제공.
"""

from __future__ import annotations

import logging
import re
from typing import Any

import httpx

from app.core.agent_tools.base import BaseTool, ToolParameter, ToolResult, ParameterType

logger = logging.getLogger(__name__)


class WebSearchTool(BaseTool):
    """웹 검색 도구

    DuckDuckGo HTML 검색 엔진을 사용.
    검색어를 받아 상위 결과를 반환하며, 프론트엔드에서 표로 렌더링.
    """

    @property
    def name(self) -> str:
        return "web_search"

    @property
    def description(self) -> str:
        return (
            "웹에서 정보를 검색합니다. "
            "최신 뉴스, 사실 확인, 공개 데이터 조회에 사용합니다. "
            "검색어는 한국어 또는 영문 키워드를 지원합니다."
        )

    @property
    def parameters(self) -> list[ToolParameter]:
        return [
            ToolParameter(
                name="query",
                type=ParameterType.STRING,
                description="검색어",
                required=True,
            ),
            ToolParameter(
                name="max_results",
                type=ParameterType.NUMBER,
                description="최대 검색 결과 수 (기본값: 5)",
                required=False,
                default=5,
            ),
        ]

    async def _run(self, params: dict[str, Any]) -> ToolResult:
        query = params["query"]
        max_results = min(params.get("max_results", 5), 10)

        try:
            results = await self._search_duckduckgo(query, max_results)

            if not results:
                return ToolResult(
                    success=True,
                    tool_name=self.name,
                    data={"results": [], "query": query},
                    display=ToolResult.ToolDisplay(
                        type="text",
                        title=f"🔍 웹 검색: {query}",
                    ),
                    error="검색 결과가 없습니다.",
                )

            # 표 형태로 렌더링 정보 제공
            return ToolResult(
                success=True,
                tool_name=self.name,
                data={"results": results, "query": query, "count": len(results)},
                display=ToolResult.ToolDisplay(
                    type="table",
                    title=f"🔍 웹 검색: {query}",
                    columns=["제목", "URL", "요약"],
                    chart_data={
                        "rows": [
                            [r["title"], r["url"], r.get("snippet", "")]
                            for r in results
                        ],
                    },
                ),
            )

        except Exception as exc:
            logger.error("웹 검색 오류: %s", exc, exc_info=True)
            return ToolResult(
                success=False,
                tool_name=self.name,
                error=f"웹 검색 중 오류: {exc}",
            )

    async def _search_duckduckgo(
        self, query: str, max_results: int
    ) -> list[dict[str, str]]:
        """DuckDuckGo HTML 검색 API 호출"""
        url = "https://html.duckduckgo.com/html/"
        params = {"q": query, "kl": "kr-kr"}

        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
            response = await client.post(url, data=params)
            response.raise_for_status()

        html = response.text
        results: list[dict[str, str]] = []

        # DuckDuckGo HTML 파싱
        # 결과 블록 추출
        result_pattern = re.compile(
            r'<a rel="nofollow"[^>]*class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>'
            r'.*?<a class="result__snippet"[^>]*>(.*?)</a>',
            re.DOTALL,
        )
        matches = result_pattern.findall(html)

        for match in matches[:max_results]:
            url_str, title_html, snippet_html = match
            # HTML 태그 제거
            title = re.sub(r"<[^>]+>", "", title_html).strip()
            snippet = re.sub(r"<[^>]+>", "", snippet_html).strip()
            # DuckDuckGo 리다이렉트 URL 정리
            if url_str.startswith("//"):
                url_str = "https:" + url_str

            if title and url_str:
                results.append({
                    "title": title,
                    "url": url_str,
                    "snippet": snippet[:200] if snippet else "",
                })

        return results