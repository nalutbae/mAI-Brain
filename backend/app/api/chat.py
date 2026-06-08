"""mAI-Brain AI 챗봇 — 채팅 API

엔드포인트:
- POST /api/chat: 채팅 요청 (질문 + 모드 → 검색 → LLM → 답변)
- GET /api/chat/history/{session_id}: 세션 대화 기록 조회

핵심 플로우:
1. 사용자 질문 수신
2. 세션 ID 확인 (없으면 자동 생성)
3. 하이브리드 검색 (mode별 top-k)
4. 이전 대화 컨텍스트 로드
5. LLM 호출 (검색 결과 + 대화 기록)
6. 답변 + 검색 출처 반환
7. 대화 기록 저장
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException

from app.config import ChatMode
from app.core.llm import get_llm_client
from app.core.search import hybrid_search
from app.core.session_store import get_session_store
from app.models.chat import ChatHistoryItem, ChatRequest, ChatResponse, SearchHit
from app.models.session import SessionCreateRequest

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("", response_model=ChatResponse)
async def create_chat(request: ChatRequest):
    """채팅 요청 처리.

    플로우: 질문 → 하이브리드 검색 → LLM 답변 생성 → 응답 + 대화 저장

    요청 바디:
        question: 사용자 질문
        mode: 채팅 모드 (fact/summary/column)
        session_id: 세션 ID (선택, 없으면 자동 생성)

    응답:
        answer: AI 답변
        sources: 검색 출처 (출처 정보 포함)
        mode: 사용된 검색 모드
        session_id: 세션 ID
    """
    store = get_session_store()

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
        # 질문 앞부분을 세션 제목으로 사용
        title = request.question[:30] + ("..." if len(request.question) > 30 else "")
        session_data = store.create_session(title=title)
        session_id = session_data["session_id"]

    # 2. 하이브리드 검색
    try:
        search_result = hybrid_search(
            query=request.question,
            mode=request.mode,
            session_id=session_id,
        )
    except Exception as exc:
        logger.error("검색 오류: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"검색 중 오류가 발생했습니다: {exc}",
        ) from exc

    # 3. 이전 대화 기록 로드 (이어서 대화 컨텍스트)
    chat_history = store.get_chat_history(session_id, limit=10)

    # 4. LLM 답변 생성
    answer = None
    try:
        llm = get_llm_client()
        answer = llm.generate_answer(
            query=request.question,
            contexts=search_result.hits,
            mode=request.mode,
            chat_history=chat_history,
            reasoning_strength=request.reasoning_strength,
        )
    except Exception as exc:
        logger.error("LLM 오류: %s", exc, exc_info=True)
        # LLM 실패 시에도 검색 결과는 반환
        # 대화 기록은 저장하지 않음 (재시도 시 동일 질문 가능)
        return ChatResponse(
            answer=f"AI 모델 응답 생성 중 오류가 발생했습니다: {exc}",
            sources=search_result.hits if search_result.hits else None,
            mode=request.mode,
            session_id=session_id,
        )

    # 5. 대화 기록 저장
    # 사용자 메시지
    store.add_message(
        session_id=session_id,
        role="user",
        content=request.question,
        mode=request.mode.value,
    )

    # AI 응답 메시지 (sources 포함)
    sources_for_db = None
    if search_result.hits:
        sources_for_db = [
            {
                "text": h.text[:200],  # 저장 시 텍스트는 200자로 축약
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
    return ChatResponse(
        answer=answer,
        sources=search_result.hits if search_result.hits else None,
        mode=request.mode,
        session_id=session_id,
    )


@router.get("/history/{session_id}", response_model=list[ChatHistoryItem])
async def get_chat_history(session_id: str):
    """세션 대화 기록 조회.

    이전 대화 내용을 페이지에 표시할 때 사용.
    """
    store = get_session_store()

    # 세션 존재 확인
    session = store.get_session(session_id)
    if session is None:
        raise HTTPException(
            status_code=404,
            detail=f"세션을 찾을 수 없습니다: {session_id}",
        )

    messages = store.get_messages(session_id)

    history = []
    for msg in messages:
        # sources 파싱 (assistant 메시지만)
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