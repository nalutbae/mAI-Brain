"""mAI-Brain AI 챗봇 — 채팅 API

엔드포인트:
- POST /api/chat: 채팅 요청 (질문 + 모드 → 검색 → LLM → 답변)
- GET /api/chat/history/{session_id}: 세션 대화 기록 조회

에이전트 모드:
- @agent 프리픽스 감지 → 에이전트 모드 활성화 → 도구 호출 → 결과 포함 응답
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException

from app.config import ChatMode
from app.core.agent_runner import detect_agent_mode, run_agent
from app.core.llm import get_llm_client
from app.core.search import hybrid_search
from app.core.session_store import get_session_store
from app.models.chat import (
    ChatHistoryItem,
    ChatRequest,
    ChatResponse,
    AgentResponse,
    AgentToolSpec,
    SearchHit,
)
from app.core.citation_parser import parse_citations

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("", response_model=ChatResponse | AgentResponse)
async def create_chat(request: ChatRequest):
    """채팅 요청 처리.

    플로우:
    1. @agent 프리픽스 감지 → 에이전트 모드
    2. 일반 모드: 질문 → 하이브리드 검색 → LLM 답변 생성 → 응답 + 대화 저장

    요청 바디:
        question: 사용자 질문
        mode: 채팅 모드 (fact/summary/column/reasoning)
        session_id: 세션 ID (선택, 없으면 자동 생성)
        workspace_id: 워크스페이스 ID (선택, 검색 범위 제한)
    """
    store = get_session_store()

    # ── 에이전트 모드 감지 ────────────────────────────────────────────── #
    is_agent, cleaned_query = detect_agent_mode(request.question)

    if is_agent:
        return await _handle_agent_mode(cleaned_query, request.session_id)

    # ── 일반 채팅 모드 ──────────────────────────────────────────────── #
    return await _handle_normal_mode(request, store)


async def _handle_agent_mode(query: str, session_id: Optional[str]) -> AgentResponse:
    """에이전트 모드 처리

    @agent 프리픽스가 감지된 경우:
    1. ToolRegistry에서 도구 목록 조회
    2. LLM이 도구 선택/실행
    3. 결과를 포함한 종합 응답 반환
    """
    logger.info("에이전트 모드 활성화: %s", query[:50])

    try:
        agent_response = await run_agent(query=query, session_id=session_id)
        return agent_response
    except Exception as exc:
        logger.error("에이전트 모드 오류: %s", exc, exc_info=True)
        return AgentResponse(
            answer=f"에이전트 모드 실행 중 오류가 발생했습니다: {exc}",
            steps=[],
            tool_calls=[],
        )


async def _handle_normal_mode(request: ChatRequest, store) -> ChatResponse:
    """일반 채팅 모드 처리 (기존 로직)"""
    # 1. 세션 확인 / 자동 생성
    session_id = request.session_id
    if session_id:
        # 기존 세션 확인
        session = store.get_session(session_id)
        if session is None:
            raise HTTPException(
                status_code=404,
                detail=f"세션을 찾을 수 없습니다: {session_id}",
            )
    else:
        # 새 세션 자동 생성
        title = request.question[:30] + ("..." if len(request.question) > 30 else "")
        session_data = store.create_session(title=title)
        session_id = session_data["session_id"]

    # 1.5 워크스페이스 컬렉션 결정
    collection_name = None
    if request.workspace_id:
        from app.core.workspace import get_workspace_store
        ws_store = get_workspace_store()
        collection_name = ws_store.get_collection_name(request.workspace_id)
        logger.info("워크스페이스 검색: workspace_id=%s, collection=%s",
                     request.workspace_id, collection_name)

    # 2. 하이브리드 검색 (creative 모드는 검색 생략)
    is_creative = request.mode == ChatMode.CREATIVE
    if is_creative:
        search_result = None
    else:
        try:
            search_result = hybrid_search(
                query=request.question,
                mode=request.mode,
                session_id=session_id,
                collection_name=collection_name,
                query_expansion=request.query_expansion,
            )
        except Exception as exc:
            logger.error("검색 오류: %s", exc, exc_info=True)
            raise HTTPException(
                status_code=500,
                detail=f"검색 중 오류가 발생했습니다: {exc}",
            ) from exc

    # 3. 이전 대화 기록 로드
    chat_history = store.get_chat_history(session_id, limit=10)

    # 4. LLM 답변 생성
    answer = None
    try:
        llm = get_llm_client()
        answer = llm.generate_answer(
            query=request.question,
            contexts=search_result.hits if search_result else [],
            mode=request.mode,
            chat_history=chat_history,
            reasoning_strength=request.reasoning_strength,
            workspace_id=request.workspace_id,
        )
    except Exception as exc:
        logger.error("LLM 오류: %s", exc, exc_info=True)
        return ChatResponse(
            answer=f"AI 모델 응답 생성 중 오류가 발생했습니다: {exc}",
            sources=search_result.hits if search_result and search_result.hits else None,
            mode=request.mode,
            session_id=session_id,
        )

    # 5. 대화 기록 저장
    store.add_message(
        session_id=session_id,
        role="user",
        content=request.question,
        mode=request.mode.value,
    )

    sources_for_db = None
    if search_result and search_result.hits:
        sources_for_db = [
            {
                "text": h.text[:200],
                "source": h.source,
                "score": h.score,
                "page": h.page,
            }
            for h in search_result.hits
        ]

    store.add_message(
        session_id=session_id,
        role="assistant",
        content=answer,
        mode=request.mode.value,
        sources=sources_for_db,
    )

    # 6. 응답 반환
    # 인용 마커 파싱 — [[N]] → Citation 매핑
    citations = None
    if search_result and search_result.hits and not is_creative:
        citations = parse_citations(answer, search_result.hits)

    return ChatResponse(
        answer=answer,
        sources=search_result.hits if search_result and search_result.hits else None,
        citations=citations,
        mode=request.mode,
        session_id=session_id,
    )


@router.get("/history/{session_id}", response_model=list[ChatHistoryItem])
async def get_chat_history(session_id: str):
    """세션 대화 기록 조회."""
    store = get_session_store()

    session = store.get_session(session_id)
    if session is None:
        raise HTTPException(
            status_code=404,
            detail=f"세션을 찾을 수 없습니다: {session_id}",
        )

    messages = store.get_messages(session_id)

    history = []
    for msg in messages:
        sources = None
        if msg.get("sources"):
            sources = [SearchHit(**s) for s in msg["sources"]]

        history.append(ChatHistoryItem(
            role=msg["role"],
            content=msg["content"],
            mode=ChatMode(msg["mode"]) if msg.get("mode") else None,
            sources=sources,
            created_at=msg["created_at"],
        ))

    return history


# ── 에이전트 도구 API ───────────────────────────────────────────────────── #

@router.get("/agent/tools", response_model=list[AgentToolSpec])
async def list_agent_tools():
    """사용 가능한 에이전트 도구 목록 조회"""
    from app.core.agent_tools.registry import get_tool_registry
    registry = get_tool_registry()
    tools = registry.list_tools()
    return [
        AgentToolSpec(
            name=tool.name,
            description=tool.description,
            parameters=[p.model_dump() for p in tool.parameters],
        )
        for tool in tools
    ]
