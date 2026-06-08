"""mAI-Brain 에이전트 러너

@agent 프리픽스 감지 → LLM이 도구 선택 → 도구 실행 → 결과를 응답에 포함.
에이전트 모드의 핵심 오케스트레이션 로직.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Optional

from app.core.agent_tools.registry import get_tool_registry
from app.core.agent_tools.base import ToolResult
from app.core.llm import get_llm_client
from app.models.chat import AgentToolCall, AgentStep, AgentResponse

logger = logging.getLogger(__name__)

# @agent 프리픽스 패턴
AGENT_PREFIX_RE = re.compile(r"^@agent\s+", re.IGNORECASE)

# 에이전트 시스템 프롬프트
AGENT_SYSTEM_PROMPT = """\
당신은 mAI-Brain의 에이전트 모드입니다. 사용자의 요청을 분석하여 적절한 도구를 선택하고 실행합니다.

사용 가능한 도구:
{tool_descriptions}

작동 규칙:
1. 사용자 요청을 분석하여 가장 적합한 도구를 선택합니다.
2. 도구 호출은 반드시 아래 JSON 형식으로 응답하세요.
3. 여러 도구를 순차적으로 사용해야 할 경우, 이전 도구 결과를 참고하여 다음 도구를 호출합니다.
4. 도구 호출이 완료되면, 결과를 한국어로 요약하여 최종 응답을 작성합니다.

도구 호출 형식:
```tool_call
{{"tool": "도구이름", "parameters": {{"파라미터1": "값1", "파라미터2": "값2"}}}}
```

도구 호출이 아닌 일반 응답은 그대로 한국어로 작성합니다.
"""

FINAL_RESPONSE_PROMPT = """\
다음 도구 실행 결과를 바탕으로 사용자에게 한국어로 답변하세요.
결과에서 중요한 정보를 추출하여 명확하게 설명하고, 필요시 출처를 표기하세요.

도구 실행 결과:
{tool_results}
"""

# 최대 도구 호출 횟수 (무한 루프 방지)
MAX_TOOL_CALLS = 5


def detect_agent_mode(message: str) -> tuple[bool, str]:
    """메시지에서 @agent 프리픽스 감지 및 제거.

    Returns:
        (is_agent, cleaned_message): 에이전트 모드 여부와 프리픽스 제거된 메시지
    """
    match = AGENT_PREFIX_RE.match(message)
    if match:
        return True, message[match.end():].strip()
    return False, message


async def run_agent(
    query: str,
    session_id: Optional[str] = None,
) -> AgentResponse:
    """에이전트 모드 실행.

    1. 도구 스펙을 포함한 프롬프트로 LLM 호출
    2. LLM이 도구 호출을 결정하면 해당 도구를 실행
    3. 도구 결과를 바탕으로 최종 응답 생성

    Args:
        query: 사용자 질문 (@agent 프리픽스 제거됨)
        session_id: 세션 ID (선택)

    Returns:
        AgentResponse: 에이전트 응답 (단계별 로그 + 최종 답변)
    """
    registry = get_tool_registry()
    llm = get_llm_client()
    steps: list[AgentStep] = []

    # 도구 스펙 목록 생성
    tool_specs = registry.list_specs()
    tool_descriptions = "\n".join(
        f"- {spec['name']}: {spec['description']}"
        for spec in tool_specs
    )

    system_prompt = AGENT_SYSTEM_PROMPT.format(tool_descriptions=tool_descriptions)

    # 대화 메시지 구성
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": query},
    ]

    # 도구 호출 루프
    for step_idx in range(MAX_TOOL_CALLS):
        # LLM 호출
        try:
            response_text = llm._call_ollama_cloud(messages, max_tokens=2048)
            if response_text is None:
                response_text = llm._call_deepseek(messages, max_tokens=2048)
            if response_text is None:
                raise RuntimeError("모든 LLM 제공자 호출 실패")
        except Exception as exc:
            logger.error("에이전트 LLM 호출 오류: %s", exc, exc_info=True)
            return AgentResponse(
                answer=f"에이전트 모드 오류: LLM 호출 실패 — {exc}",
                steps=steps,
                tool_calls=[],
            )

        # 도구 호출 감지
        tool_call_match = re.search(
            r"```tool_call\s*\n(.*?)\n```",
            response_text,
            re.DOTALL,
        )

        if not tool_call_match:
            # 도구 호출이 아님 → 최종 응답으로 처리
            # @agent가 없는 일반 텍스트 응답이면 그대로 반환
            final_answer = response_text.strip()
            # 도구 호출 블록이 없는 응답에서 tool_call 태그 제거 (정리)
            final_answer = re.sub(r"```tool_call.*?```", "", final_answer, flags=re.DOTALL).strip()

            if not steps:
                # 도구 호출 없이 바로 응답한 경우
                steps.append(AgentStep(
                    type="thinking",
                    content="요청을 분석했습니다. 도구 호출 없이 직접 응답합니다.",
                ))

            return AgentResponse(
                answer=final_answer,
                steps=steps,
                tool_calls=[s for s in steps if s.type == "tool_call"],
            )

        # 도구 호출 파싱
        try:
            call_json = json.loads(tool_call_match.group(1).strip())
            tool_name = call_json.get("tool", "")
            tool_params = call_json.get("parameters", {})
        except (json.JSONDecodeError, KeyError) as exc:
            logger.warning("도구 호출 JSON 파싱 오류: %s", exc)
            steps.append(AgentStep(
                type="thinking",
                content=f"도구 호출 형식 오류: {exc}",
            ))
            messages.append({
                "role": "assistant",
                "content": response_text,
            })
            messages.append({
                "role": "user",
                "content": "도구 호출 형식이 올바르지 않습니다. JSON 형식으로 다시 시도해주세요.",
            })
            continue

        # 도구 실행
        thinking = response_text[:tool_call_match.start()].strip()
        if thinking:
            steps.append(AgentStep(
                type="thinking",
                content=thinking,
            ))

        steps.append(AgentStep(
            type="tool_call",
            content=f"{tool_name}({json.dumps(tool_params, ensure_ascii=False)})",
        ))

        result: ToolResult = await registry.execute(tool_name, tool_params)

        steps.append(AgentStep(
            type="tool_result",
            content=result.error if not result.success else "도구 실행 완료",
            tool_name=tool_name,
            tool_success=result.success,
            tool_display=result.display.model_dump() if result.display else None,
        ))

        if not result.success:
            # 도구 실패 시 LLM에게 알리고 재시도
            messages.append({"role": "assistant", "content": response_text})
            messages.append({
                "role": "user",
                "content": f"도구 '{tool_name}' 실행 실패: {result.error}\n다른 방법으로 시도하거나 직접 답변해주세요.",
            })
            continue

        # 도구 성공 시 결과를 컨텍스트에 추가하고 다음 단계 진행
        result_summary = json.dumps(
            result.data, ensure_ascii=False, default=str
        )[:2000] if result.data else "(결과 없음)"

        messages.append({"role": "assistant", "content": response_text})
        messages.append({
            "role": "user",
            "content": f"도구 '{tool_name}' 실행 결과:\n{result_summary}\n\n"
                       f"이 결과를 바탕으로 추가 도구 호출이 필요하면 하고, "
                       f"그렇지 않으면 최종 답변을 작성해주세요.",
        })

    # 최대 호출 횟수 도달 → 마지막 결과로 종합 응답 생성
    final_prompt = FINAL_RESPONSE_PROMPT.format(
        tool_results=json.dumps(
            [s.model_dump() for s in steps],
            ensure_ascii=False,
            default=str,
        )
    )

    try:
        final_answer = llm._call_ollama_cloud(
            [{"role": "system", "content": final_prompt}, {"role": "user", "content": query}],
            max_tokens=2048,
        )
        if final_answer is None:
            final_answer = llm._call_deepseek(
                [{"role": "system", "content": final_prompt}, {"role": "user", "content": query}],
                max_tokens=2048,
            )
    except Exception as exc:
        final_answer = f"에이전트 모드 종합 응답 생성 오류: {exc}"

    return AgentResponse(
        answer=final_answer or "에이전트 모드에서 응답을 생성하지 못했습니다.",
        steps=steps,
        tool_calls=[s for s in steps if s.type == "tool_call"],
    )