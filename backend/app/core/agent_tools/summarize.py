"""mAI-Brain 에이전트 도구 — 문서 요약

RAG 검색 결과를 바탕으로 문서 요약을 생성하는 도구.
기존 하이브리드 검색 + LLM을 활용하여 요약을 수행하며,
프론트엔드에 텍스트 형태로 결과를 제공.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from app.core.agent_tools.base import BaseTool, ToolParameter, ToolResult, ParameterType
from app.core.llm import get_llm_client
from app.core.search import hybrid_search
from app.config import ChatMode

logger = logging.getLogger(__name__)


class SummarizeDocumentTool(BaseTool):
    """문서 요약 도구

    주어진 쿼리로 RAG 검색을 수행한 뒤, LLM이 결과를 요약.
    챗봇의 요약 모드와 동일한 파이프라인을 사용.
    """

    @property
    def name(self) -> str:
        return "summarize_document"

    @property
    def description(self) -> str:
        return (
            "업로드된 문서에서 키워드로 검색하여 요약을 생성합니다. "
            "문서 내 특정 주제의 핵심 내용을 파악할 때 사용합니다. "
            "검색 결과의 출처도 함께 제공합니다."
        )

    @property
    def parameters(self) -> list[ToolParameter]:
        return [
            ToolParameter(
                name="query",
                type=ParameterType.STRING,
                description="검색/요약할 키워드 또는 질문",
                required=True,
            ),
            ToolParameter(
                name="session_id",
                type=ParameterType.STRING,
                description="세션 ID (기존 대화 컨텍스트 유지 시)",
                required=False,
            ),
        ]

    async def _run(self, params: dict[str, Any]) -> ToolResult:
        query = params["query"]
        session_id = params.get("session_id")

        try:
            # RAG 하이브리드 검색 수행 (요약 모드: top-8)
            search_result = hybrid_search(
                query=query,
                mode=ChatMode.SUMMARY,
                session_id=session_id,
            )

            if not search_result.hits:
                return ToolResult(
                    success=True,
                    tool_name=self.name,
                    data={"summary": "관련 문서를 찾을 수 없습니다.", "sources": []},
                    display=ToolResult.ToolDisplay(
                        type="text",
                        title=f"📋 문서 요약: {query}",
                    ),
                )

            # LLM으로 요약 생성
            llm = get_llm_client()
            summary = llm.generate_answer(
                query=query,
                contexts=search_result.hits,
                mode=ChatMode.SUMMARY,
            )

            # 출처 정보 구성
            sources = [
                {
                    "source": h.source,
                    "page": h.page,
                    "score": h.score,
                    "text_snippet": h.text[:100],
                }
                for h in search_result.hits
            ]

            return ToolResult(
                success=True,
                tool_name=self.name,
                data={
                    "summary": summary,
                    "sources": sources,
                    "query": query,
                    "hit_count": len(search_result.hits),
                },
                display=ToolResult.ToolDisplay(
                    type="text",
                    title=f"📋 문서 요약: {query}",
                ),
            )

        except Exception as exc:
            logger.error("문서 요약 오류: %s", exc, exc_info=True)
            return ToolResult(
                success=False,
                tool_name=self.name,
                error=f"문서 요약 중 오류: {exc}",
            )