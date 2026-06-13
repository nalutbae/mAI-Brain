"""mAI-Brain AI 챗봇 — 컨텍스트 윈도우 관리 모듈

대화 기록이 길어질 때:
1. 이전 대화를 LLM으로 요약하여 컨텍스트 윈도우 내에 유지
2. 특정 문서를 "고정"(Pin)하여 항상 컨텍스트에 포함
3. 최종 컨텍스트 = 요약 + 고정 문서 + 최근 대화 기록

저장소:
- 요약: messages 테이블 (role='system', mode='summary')
- 고정 문서: pinned_documents 테이블 (SQLite)
"""

from __future__ import annotations

import logging
from typing import Optional

from app.core.llm import get_llm_client
from app.core.session_store import get_session_store
from app.config import ChatMode

logger = logging.getLogger(__name__)

# 요약 프롬프트 (한국어)
_SUMMARIZE_PROMPT = """\
아래 대화 기록을 간결하게 요약하십시오. 중요한 정보, 결정, 질문-답변의 핵심 내용을 보존하십시오.
요약은 이후 대화에서 컨텍스트로 활용되므로, 사실과 맥락을 정확하게 담아야 합니다.

대화 기록:
{history}

요약:"""


class ContextManager:
    """컨텍스트 윈도우 관리자.

    대화 기록이 길어지면 이전 메시지를 요약하고,
    고정된 문서를 항상 컨텍스트에 포함시킵니다.

    Args:
        max_history_messages: 최근 유지할 대화 메시지 수 (기본 10)
        summarize_threshold: 이 메시지 수를 넘으면 자동 요약 (기본 20)
    """

    def __init__(
        self,
        max_history_messages: int = 10,
        summarize_threshold: int = 20,
    ) -> None:
        self.max_history_messages = max_history_messages
        self.summarize_threshold = summarize_threshold
        self._store = get_session_store()

    # ------------------------------------------------------------------- #
    # 대화 요약
    # ------------------------------------------------------------------- #

    def summarize_history(
        self,
        session_id: str,
        max_recent: int = 10,
    ) -> Optional[str]:
        """이전 대화 기록을 LLM으로 요약하여 저장.

        현재 대화 기록이 summarize_threshold를 초과하면,
        최근 max_recent개를 제외한 이전 메시지를 요약합니다.

        Args:
            session_id: 세션 ID
            max_recent: 최근 유지할 메시지 수 (요약 대상에서 제외)

        Returns:
            생성된 요약 텍스트, 또는 요약이 필요 없으면 None
        """
        store = self._store

        # 전체 메시지 수 확인
        total_count = store.get_message_count(session_id)
        if total_count <= self.summarize_threshold:
            logger.info(
                "요약 불필요: 메시지 수(%d) ≤ 임계값(%d)",
                total_count, self.summarize_threshold,
            )
            return None

        # 기존 요약 포함 전체 메시지 조회
        all_messages = store.get_messages(session_id, limit=10000)

        # 기존 요약 텍스트 수집 (role=system, mode=summary)
        existing_summaries = []
        for msg in all_messages:
            if msg["role"] == "system" and msg.get("mode") == "summary":
                existing_summaries.append(msg["content"])

        # 최근 max_recent개를 제외한 이전 메시지 수집
        # (user/assistant만, system/summary는 제외)
        user_assistant_msgs = [
            m for m in all_messages
            if m["role"] in ("user", "assistant")
        ]

        if len(user_assistant_msgs) <= max_recent:
            logger.info("요약 불필요: user/assistant 메시지가 충분하지 않음")
            return None

        # 요약할 이전 메시지 (최근 max_recent개 제외)
        older_messages = user_assistant_msgs[:-max_recent]

        if not older_messages:
            return None

        # 대화 기록 텍스트 구성
        history_text = ""
        if existing_summaries:
            history_text += "[이전 요약]\n" + "\n".join(existing_summaries) + "\n\n"
        history_text += "[이전 대화]\n"
        for msg in older_messages:
            role_label = "사용자" if msg["role"] == "user" else "AI"
            content = msg["content"][:500]  # 각 메시지 최대 500자
            history_text += f"{role_label}: {content}\n"

        # LLM으로 요약 생성
        try:
            llm = get_llm_client()
            prompt = _SUMMARIZE_PROMPT.format(history=history_text)

            # LLM 호출 — generate_answer를 활용하되 빈 컨텍스트로 전달
            summary = llm.generate_answer(
                query=prompt,
                contexts=[],
                mode=ChatMode.FACT,
                chat_history=[
                    {"role": "system", "content": "당신은 대화 요약 도우미입니다. 주어진 대화를 간결하고 정확하게 요약하십시오."},
                ],
            )

            if not summary:
                logger.warning("LLM 요약 결과가 비어있음")
                return None

            # 기존 요약 메시지 삭제 후 새 요약 저장
            store.delete_summary_messages(session_id)
            store.add_message(
                session_id=session_id,
                role="system",
                content=summary.strip(),
                mode="summary",
            )

            logger.info(
                "대화 요약 완료: session=%s, 요약된 메시지 수=%d, 요약 길이=%d",
                session_id[:8], len(older_messages), len(summary),
            )
            return summary.strip()

        except Exception as exc:
            logger.error("요약 생성 실패: %s", exc, exc_info=True)
            return None

    def get_summary(self, session_id: str) -> Optional[str]:
        """세션의 현재 요약 텍스트를 반환.

        Returns:
            요약 텍스트, 없으면 None
        """
        store = self._store
        messages = store.get_messages(session_id, limit=10000)

        summaries = []
        for msg in messages:
            if msg["role"] == "system" and msg.get("mode") == "summary":
                summaries.append(msg["content"])

        if summaries:
            return "\n".join(summaries)
        return None

    # ------------------------------------------------------------------- #
    # 문서 고정 (Pin)
    # ------------------------------------------------------------------- #

    def pin_document(self, session_id: str, document_id: str) -> dict:
        """문서를 세션에 고정.

        고정된 문서의 청크는 컨텍스트 구성 시 항상 포함됩니다.

        Args:
            session_id: 세션 ID
            document_id: 문서 ID

        Returns:
            고정 정보 딕셔너리
        """
        return self._store.pin_document(session_id, document_id)

    def unpin_document(self, session_id: str, document_id: str) -> bool:
        """문서 고정 해제.

        Args:
            session_id: 세션 ID
            document_id: 문서 ID

        Returns:
            해제 성공 여부
        """
        return self._store.unpin_document(session_id, document_id)

    def get_pinned_documents(self, session_id: str) -> list[dict]:
        """세션에 고정된 문서 목록 반환.

        Args:
            session_id: 세션 ID

        Returns:
            고정된 문서 정보 리스트
        """
        return self._store.get_pinned_documents(session_id)

    # ------------------------------------------------------------------- #
    # 컨텍스트 구성
    # ------------------------------------------------------------------- #

    def get_context_for_chat(
        self,
        session_id: str,
        limit: Optional[int] = None,
    ) -> dict:
        """LLM 호출용 최종 컨텍스트 구성.

        최종 컨텍스트 = 요약 + 고정 문서 + 최근 대화 기록

        Args:
            session_id: 세션 ID
            limit: 최근 대화 기록 수 (기본값: max_history_messages)

        Returns:
            {
                "summary": str | None,           # 대화 요약 텍스트
                "pinned_docs": list[dict],        # 고정 문서 정보
                "pinned_contexts": list[SearchHit],  # 고정 문서 검색 결과
                "chat_history": list[dict],       # 최근 대화 기록
                "needs_summarization": bool,      # 자동 요약 필요 여부
            }
        """
        limit = limit or self.max_history_messages

        # 1. 대화 요약
        summary = self.get_summary(session_id)

        # 2. 고정 문서
        pinned_docs = self.get_pinned_documents(session_id)
        pinned_contexts = []

        # 고정 문서의 청크를 검색하여 컨텍스트에 포함
        if pinned_docs:
            try:
                from app.core.search import hybrid_search as _hybrid_search
                from app.models.chat import SearchHit

                for doc in pinned_docs:
                    doc_id = doc["document_id"]
                    # 고정 문서 검색 — document_id를 쿼리로 활용
                    # 빈 쿼리로 검색할 수 없으므로 document_id를 키워드로 사용
                    try:
                        search_result = _hybrid_search(
                            query=doc_id,
                            mode=ChatMode.FACT,
                            session_id=session_id,
                        )
                        if search_result and search_result.hits:
                            # 최대 3개 청크만 포함
                            pinned_contexts.extend(search_result.hits[:3])
                    except Exception as exc:
                        logger.warning(
                            "고정 문서 검색 실패: document_id=%s, %s",
                            doc_id, exc,
                        )
            except Exception as exc:
                logger.error("고정 문서 컨텍스트 구성 실패: %s", exc)

        # 3. 최근 대화 기록 (요약 제외)
        chat_history = self._store.get_chat_history(session_id, limit=limit)

        # 4. 메시지 수가 임계값 초과 시 자동 요약 플래그
        total_count = self._store.get_message_count(session_id)
        needs_summarization = total_count > self.summarize_threshold and summary is None

        if needs_summarization:
            logger.info(
                "자동 요약 권장: 메시지 수(%d) > 임계값(%d)",
                total_count, self.summarize_threshold,
            )

        return {
            "summary": summary,
            "pinned_docs": pinned_docs,
            "pinned_contexts": pinned_contexts,
            "chat_history": chat_history,
            "needs_summarization": needs_summarization,
        }


# --------------------------------------------------------------------------- #
# 싱글톤
# --------------------------------------------------------------------------- #

_context_manager: Optional[ContextManager] = None


def get_context_manager() -> ContextManager:
    """ContextManager 싱글톤 인스턴스 반환."""
    global _context_manager
    if _context_manager is None:
        _context_manager = ContextManager()
    return _context_manager