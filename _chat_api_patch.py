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

    # 2. 하이브리드 검색
    try:
        search_result = hybrid_search(
            query=request.question,
            mode=request.mode,
            session_id=session_id,
            collection_name=collection_name,
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
            contexts=search_result.hits,
            mode=request.mode,
            chat_history=chat_history,
            reasoning_strength=request.reasoning_strength,
            workspace_id=request.workspace_id,
        )
    except Exception as exc:
        logger.error("LLM 오류: %s", exc, exc_info=True)
        return ChatResponse(
            answer=f"AI 모델 응답 생성 중 오류가 발생했습니다: {exc}",
            sources=search_result.hits if search_result.hits else None,
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
    if search_result.hits:
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
    return ChatResponse(
        answer=answer,
        sources=search_result.hits if search_result.hits else None,
        mode=request.mode,
        session_id=session_id,
    )