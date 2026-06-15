"""mAI-Brain AI 챗봇 — 스트리밍 채팅 API

엔드포인트:
- POST /api/chat/stream: SSE 스트리밍 채팅 (질문 + 모드 → 검색 → LLM 스트리밍 → 답변)

SSE 이벤트 형식:
- event: token     data: {"content": "단어"}      — LLM 토큰 조각
- event: sources   data: {"sources": [...]}        — 검색 출처 (토큰 스트림 완료 후)
- event: done      data: {"session_id": "..."}    — 스트리밍 완료
- event: error     data: {"error": "..."}          — 오류 발생
"""

from __future__ import annotations

import json
import logging
from typing import Optional

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from app.config import ChatMode, get_settings
from app.core.agent_runner import detect_agent_mode, run_agent
from app.core.context_manager import get_context_manager
from app.core.llm_stream import get_llm_stream_client
from app.core.search import hybrid_search, SearchResult
from app.core.session_store import get_session_store
from app.models.chat import ChatRequest
from app.core.citation_parser import parse_citations

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("")
async def stream_chat(request: ChatRequest, req: Request):
    """채팅 스트리밍 요청 처리.

    SSE(Server-Sent Events) 형식으로 LLM 응답을 점진적으로 전송한다.
    클라이언트는 EventSource 또는 fetch + ReadableStream으로 수신.

    플로우:
    1. (에이전트 모드 감지 → 에이전트는 스트리밍 미지원, 일반 응답)
    2. 하이브리드 검색 (비동기 아님, 빠름)
    3. 세션 확인/생성
    4. LLM 스트리밍 생성 (토큰 단위 전송)
    5. 검색 출처 전송
    6. 대화 기록 저장
    7. 완료 이벤트 전송
    """

    # ── 에이전트 모드는 현재 스트리밍 미지원 → 일반 응답으로 폴백 ── #
    is_agent, cleaned_query = detect_agent_mode(request.question)
    if is_agent:
        # 에이전트 모드는 비스트리밍으로 처리 후 SSE로 래핑
        async def agent_stream():
            try:
                agent_response = await run_agent(query=cleaned_query, session_id=request.session_id)
                yield f"event: token\ndata: {json.dumps({'content': agent_response.answer}, ensure_ascii=False)}\n\n"
                if agent_response.steps:
                    steps_data = [
                        {"type": s.type, "content": s.content, "tool_name": s.tool_name}
                        for s in agent_response.steps
                    ]
                    yield f"event: steps\ndata: {json.dumps({'steps': steps_data}, ensure_ascii=False)}\n\n"
                yield f"event: done\ndata: {json.dumps({'session_id': request.session_id or ''}, ensure_ascii=False)}\n\n"
            except Exception as exc:
                logger.error("에이전트 스트리밍 오류: %s", exc, exc_info=True)
                yield f"event: error\ndata: {json.dumps({'error': str(exc)}, ensure_ascii=False)}\n\n"

        return StreamingResponse(
            agent_stream(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",  # nginx 버퍼링 방지
            },
        )

    # ── 일반 채팅 스트리밍 ────────────────────────────────────────── #
    store = get_session_store()

    # 1. 세션 확인 / 자동 생성
    session_id = request.session_id
    if session_id:
        session = store.get_session(session_id)
        if session is None:
            error_json = json.dumps({"error": f"세션을 찾을 수 없습니다: {session_id}"}, ensure_ascii=False)
            async def error_stream():
                yield f"event: error\ndata: {error_json}\n\n"
            return StreamingResponse(error_stream(), media_type="text/event-stream")
    else:
        title = request.question[:30] + ("..." if len(request.question) > 30 else "")
        session_data = store.create_session(title=title)
        session_id = session_data["session_id"]

    # 2. 워크스페이스 컬렉션 결정
    collection_name = None
    workspace_doc_ids: list[str] | None = None
    # "전체" 또는 빈 문자열이면 모든 워크스페이스에서 검색 (workspace_id=None)
    effective_workspace_id = request.workspace_id if request.workspace_id and request.workspace_id != "전체" else None
    if effective_workspace_id:
        from app.core.workspace import get_workspace_store
        ws_store = get_workspace_store()
        collection_name = ws_store.get_collection_name(effective_workspace_id)
        # 워크스페이스에 할당된 문서 ID 목록 (폴백 필터링용)
        workspace = ws_store.get_workspace(effective_workspace_id)
        if workspace:
            workspace_doc_ids = workspace.document_ids

    # 3. 하이브리드 검색 (creative 모드는 검색 생략)
    is_creative = request.mode == ChatMode.CREATIVE
    search_result = None
    if not is_creative:
        try:
            search_result = hybrid_search(
                query=request.question,
                mode=request.mode,
                session_id=session_id,
                collection_name=collection_name,
                workspace_doc_ids=workspace_doc_ids,
                query_expansion=request.query_expansion,
            )
        except Exception as exc:
            logger.error("검색 오류: %s", exc, exc_info=True)

    # 4. 컨텍스트 관리자로 대화 기록 로드 (요약 + 고정 문서 + 최근 대화)
    ctx_manager = get_context_manager()
    context_data = ctx_manager.get_context_for_chat(session_id)

    # 요약이 있으면 chat_history 앞에 요약 시스템 메시지 추가
    chat_history = context_data["chat_history"]
    summary = context_data.get("summary")
    if summary:
        chat_history = [
            {"role": "system", "content": f"[이전 대화 요약]\n{summary}"},
        ] + chat_history

    # 고정 문서 컨텍스트가 있으면 검색 결과에 추가
    pinned_contexts = context_data.get("pinned_contexts", [])
    if search_result and search_result.hits and pinned_contexts:
        existing_sources = {h.source for h in search_result.hits}
        for ph in pinned_contexts:
            if ph.source not in existing_sources:
                search_result.hits.insert(0, ph)
    elif pinned_contexts and not is_creative:
        if not search_result:
            search_result = SearchResult(hits=pinned_contexts, query=request.question, mode=request.mode)
        else:
            search_result.hits = pinned_contexts

    # 5. LLM 스트리밍 생성
    llm_stream = get_llm_stream_client()

    # 서비스 모드: 설정에 따라 출처/인용 노출 제어
    show_sources = not request.service_mode or get_settings().service_chat_show_sources

    async def event_stream():
        full_answer = ""
        try:
            async for chunk in llm_stream.generate_answer_stream(
                query=request.question,
                contexts=search_result.hits if search_result else [],
                mode=request.mode,
                chat_history=chat_history,
                reasoning_strength=request.reasoning_strength,
                workspace_id=request.workspace_id,
                service_mode=request.service_mode,
            ):
                full_answer += chunk
                yield f"event: token\ndata: {json.dumps({'content': chunk}, ensure_ascii=False)}\n\n"

            # 6. 검색 출처 전송 (토큰 스트림 완료 후)
            # 서비스 모드: show_sources=False 시 출처/인용 이벤트 생략
            if search_result and search_result.hits and show_sources:
                sources_data = [
                    {
                        "text": h.text[:200],
                        "source": h.source,
                        "score": h.score,
                        "page": h.page,
                    }
                    for h in search_result.hits
                ]
                yield f"event: sources\ndata: {json.dumps({'sources': sources_data}, ensure_ascii=False)}\n\n"

                # 6.5. 인용 마커 파싱 — [[N]] → Citation 매핑
                if not is_creative:
                    citations = parse_citations(full_answer, search_result.hits)
                    if citations:
                        citations_data = [
                            {
                                "index": c.index,
                                "source": c.source,
                                "page": c.page,
                                "text": c.text,
                                "score": c.score,
                            }
                            for c in citations
                        ]
                        yield f"event: citations\ndata: {json.dumps({'citations': citations_data}, ensure_ascii=False)}\n\n"

            # 7. 대화 기록 저장
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
                content=full_answer,
                mode=request.mode.value,
                sources=sources_for_db,
            )

            # 8. 완료 이벤트
            yield f"event: done\ndata: {json.dumps({'session_id': session_id}, ensure_ascii=False)}\n\n"

        except Exception as exc:
            logger.error("LLM 스트리밍 오류: %s", exc, exc_info=True)
            yield f"event: error\ndata: {json.dumps({'error': str(exc)}, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # nginx 버퍼링 방지
        },
    )