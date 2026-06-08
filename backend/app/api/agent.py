"""mAI-Brain Agent — 에이전트 API

@agent 프리픽스로 트리거되는 에이전트 모드의 API 엔드포인트입니다.

엔드포인트:
- POST /api/agent/chat: 도구 실행 + AI 종합 답변
- GET  /api/agent/tools: 사용 가능한 도구 목록 조회

핵심 플로우:
1. 사용자 질문 + 도구 선택 수신
2. 선택된 도구들을 순차 실행
3. 도구 실행 결과를 바탕으로 LLM 종합 답변 생성
4. 도구 결과 + AI 답변 반환
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException

from app.agent.base import ToolResult
from app.agent.registry import get_tool_registry
from app.config import ChatMode
from app.core.llm import get_llm_client
from app.models.agent import (
    AgentRequest,
    AgentResponse,
    AgentToolsResponse,
    ToolResultModel,
)

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/tools", response_model=AgentToolsResponse)
async def list_agent_tools():
    """사용 가능한 에이전트 도구 목록을 반환합니다."""
    registry = get_tool_registry()
    tools = registry.list_tools()
    return AgentToolsResponse(tools=tools)


@router.post("/chat", response_model=AgentResponse)
async def agent_chat(request: AgentRequest):
    """에이전트 채팅 요청 처리.

    선택된 도구들을 실행하고, 결과를 바탕으로 AI 종합 답변을 생성합니다.

    요청 바디:
        question: 사용자 질문
        tools: 실행할 도구 이름 목록 (예: ["web_search", "summarize_document"])
        tool_params: 도구별 추가 파라미터 (선택)
        session_id: 세션 ID (선택)

    응답:
        answer: AI 종합 답변
        tool_results: 각 도구의 실행 결과
        session_id: 세션 ID
    """
    registry = get_tool_registry()

    # 도구 유효성 검증
    for tool_name in request.tools:
        tool = registry.get(tool_name)
        if tool is None:
            valid_tools = registry.get_tool_names()
            raise HTTPException(
                status_code=400,
                detail=f"알 수 없는 도구입니다: '{tool_name}' (사용 가능: {', '.join(valid_tools)})",
            )

    # 각 도구 실행
    tool_results: list[ToolResult] = []
    for tool_name in request.tools:
        tool = registry.get(tool_name)
        if tool is None:
            continue

        # 도구별 파라미터 구성
        params = {}
        if request.tool_params and tool_name in request.tool_params:
            params = request.tool_params[tool_name]
        # 기본: 질문을 query로 전달
        if "query" not in params:
            params["query"] = request.question

        try:
            result = await tool.execute(params)
            tool_results.append(result)
        except Exception as exc:
            logger.error("도구 '%s' 실행 중 예외: %s", tool_name, exc, exc_info=True)
            tool_results.append(
                ToolResult(
                    tool_name=tool_name,
                    success=False,
                    error=f"도구 실행 중 예외 발생: {exc}",
                )
            )

    # 도구 결과를 바탕으로 LLM 종합 답변 생성
    answer = await _generate_agent_answer(
        question=request.question,
        tool_results=tool_results,
    )

    # 응답 구성
    result_models = [
        ToolResultModel(
            tool_name=r.tool_name,
            success=r.success,
            data=r.data,
            error=r.error,
            display_type=r.display_type,
        )
        for r in tool_results
    ]

    return AgentResponse(
        answer=answer,
        tool_results=result_models,
        session_id=request.session_id,
    )


async def _generate_agent_answer(
    question: str,
    tool_results: list[ToolResult],
) -> str:
    """도구 실행 결과를 바탕으로 LLM 종합 답변을 생성합니다."""
    if not tool_results:
        return "도구 실행 결과가 없습니다."

    # 도구 결과를 컨텍스트로 구성
    context_parts = []
    for r in tool_results:
        if r.success:
            context_parts.append(f"[{r.tool_name} 결과]\n{r.data}")
        else:
            context_parts.append(f"[{r.tool_name} 오류]\n{r.error}")

    context_text = "\n\n".join(context_parts)

    prompt = f"""다음은 여러 도구의 실행 결과입니다. 이를 바탕으로 사용자 질문에 종합적으로 답변해 주세요.

[사용자 질문]
{question}

[도구 실행 결과]
{context_text}

규칙:
1. 한국어로 답변하세요.
2. 각 도구의 결과를 구분하여 설명하세요.
3. 검색 결과가 있으면 출처를 표기하세요.
4. 도구 실행에 실패한 경우 그 사실을 언급하세요.
5. 차트 데이터가 있으면 그 의미를 설명하세요."""

    try:
        llm = get_llm_client()
        answer = llm.generate_answer(
            query=prompt,
            contexts=[],
            mode=ChatMode.FACT,
        )
        return answer
    except Exception as exc:
        logger.error("에이전트 답변 생성 오류: %s", exc)
        # LLM 실패 시에도 도구 결과는 반환
        results_text = "\n".join(
            f"- {r.tool_name}: {'성공' if r.success else '실패 - ' + (r.error or '')}"
            for r in tool_results
        )
        return f"도구 실행 결과:\n{results_text}\n\n(죄송합니다. LLM 응답 생성 중 오류가 발생했습니다.)"
