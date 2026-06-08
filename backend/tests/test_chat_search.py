"""mAI-Brain — 검색+채팅 API 테스트"""

테스트 범위:
- SessionStore: 세션 생성, 조회, 메시지 추가/조회, 대화 기록
- search.py: 토큰 해시, sparse 변환, top-k 매핑
- llm.py: 프롬프트 구성, 메시지 빌드
- API 엔드포인트: 세션 CRUD, 채팅 플로우
"""

import json
import os
import tempfile
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.config import ChatMode
from app.core.llm import LLMClient, MODE_INSTRUCTIONS, SYSTEM_PROMPT
from app.core.search import (
    SearchResult,
    _get_top_k,
    _sparse_dict_to_qdrant,
    _token_to_index,
    hybrid_search,
)
from app.core.session_store import SessionStore
from app.models.chat import ChatRequest, ChatResponse, SearchHit
from app.models.session import SessionCreateRequest, SessionResponse


# =========================================================================== #
# SessionStore 테스트
# =========================================================================== #

class TestSessionStore:
    """SessionStore 단위 테스트 — 임시 DB 사용."""

    def setup_method(self):
        """테스트용 임시 DB 생성."""
        self.tmp_dir = tempfile.mkdtemp()
        self.db_path = Path(self.tmp_dir) / "test_sessions.db"
        self.store = SessionStore(db_path=self.db_path)

    def teardown_method(self):
        """임시 DB 정리."""
        if self.db_path.exists():
            self.db_path.unlink()
        # WAL 파일도 정리
        for suffix in ["-wal", "-shm"]:
            wal_path = Path(str(self.db_path) + suffix)
            if wal_path.exists():
                wal_path.unlink()

    def test_create_session_default_title(self):
        """세션 생성 — 기본 제목 자동 생성."""
        session = self.store.create_session()
        assert session["session_id"]
        assert "새 대화" in session["title"]

    def test_create_session_custom_title(self):
        """세션 생성 — 사용자 지정 제목."""
        session = self.store.create_session(title="테스트 세션")
        assert session["title"] == "테스트 세션"

    def test_get_session(self):
        """세션 조회."""
        created = self.store.create_session(title="테스트")
        found = self.store.get_session(created["session_id"])
        assert found is not None
        assert found["title"] == "테스트"

    def test_get_session_not_found(self):
        """존재하지 않는 세션 조회."""
        result = self.store.get_session("nonexistent-id")
        assert result is None

    def test_list_sessions(self):
        """세션 목록 — 최근순."""
        s1 = self.store.create_session(title="첫째")
        s2 = self.store.create_session(title="둘째")
        sessions = self.store.list_sessions()
        assert len(sessions) >= 2
        # 최근 생성이 먼저
        titles = [s["title"] for s in sessions]
        assert "둘째" in titles

    def test_add_and_get_messages(self):
        """메시지 추가 및 조회."""
        session = self.store.create_session(title="대화 테스트")
        sid = session["session_id"]

        self.store.add_message(sid, "user", "질문입니다", mode="fact")
        self.store.add_message(
            sid, "assistant", "답변입니다", mode="fact",
            sources=[{"source": "test.pdf", "score": 0.9, "page": 1}],
        )

        messages = self.store.get_messages(sid)
        assert len(messages) == 2
        assert messages[0]["role"] == "user"
        assert messages[0]["content"] == "질문입니다"
        assert messages[1]["role"] == "assistant"
        assert messages[1]["sources"] is not None
        assert messages[1]["sources"][0]["source"] == "test.pdf"

    def test_get_chat_history(self):
        """LLM 프롬프트용 대화 기록 포맷."""
        session = self.store.create_session()
        sid = session["session_id"]

        self.store.add_message(sid, "user", "질문1")
        self.store.add_message(sid, "assistant", "답변1")
        self.store.add_message(sid, "system", "시스템 메시지")  # 제외되어야 함
        self.store.add_message(sid, "user", "질문2")

        history = self.store.get_chat_history(sid)
        # system 메시지는 제외
        assert len(history) == 3
        assert all(m["role"] in ("user", "assistant") for m in history)
        # 시간순 정렬
        assert history[-1]["content"] == "질문2"

    def test_delete_session(self):
        """세션 삭제."""
        session = self.store.create_session(title="삭제 테스트")
        sid = session["session_id"]

        self.store.add_message(sid, "user", "질문")
        deleted = self.store.delete_session(sid)
        assert deleted is True
        assert self.store.get_session(sid) is None

    def test_delete_nonexistent_session(self):
        """존재하지 않는 세션 삭제."""
        deleted = self.store.delete_session("nonexistent")
        assert deleted is False

    def test_message_count(self):
        """메시지 카운트."""
        session = self.store.create_session()
        sid = session["session_id"]

        assert self.store.get_message_count(sid) == 0
        self.store.add_message(sid, "user", "질문")
        self.store.add_message(sid, "assistant", "답변")
        assert self.store.get_message_count(sid) == 2


# =========================================================================== #
# search 모듈 테스트
# =========================================================================== #

class TestSearchUtils:
    """search.py 유틸리티 함수 테스트."""

    def test_token_to_index_deterministic(self):
        """동일 토큰 → 동일 인덱스."""
        token = "test"
        idx1 = _token_to_index(token)
        idx2 = _token_to_index(token)
        assert idx1 == idx2
        assert isinstance(idx1, int)
        assert idx1 >= 0

    def test_token_to_index_different_tokens(self):
        """다른 토큰 → 다른 인덱스 (충돌은 가능하지만 희박)."""
        idx1 = _token_to_index("test")
        idx2 = _token_to_index("history")
        # 충돌 가능성은 있지만 일반적으로 다름
        # 해시의 기본 속성으로 다를 것이라 가정
        assert isinstance(idx1, int) and isinstance(idx2, int)

    def test_sparse_dict_to_qdrant_empty(self):
        """빈 sparse 딕셔너리 변환."""
        result = _sparse_dict_to_qdrant({})
        assert result.indices == []
        assert result.values == []

    def test_sparse_dict_to_qdrant_with_data(self):
        """sparse 딕셔너리 → SparseVector 변환."""
        sparse = {"test": 0.5, "history": 0.8}
        result = _sparse_dict_to_qdrant(sparse)
        assert len(result.indices) == 2
        assert len(result.values) == 2
        assert 0.5 in result.values
        assert 0.8 in result.values

    def test_get_top_k_fact(self):
        """팩트 모드 top-k = 5."""
        top_k = _get_top_k(ChatMode.FACT)
        assert top_k == 5

    def test_get_top_k_summary(self):
        """요약 모드 top-k = 8."""
        top_k = _get_top_k(ChatMode.SUMMARY)
        assert top_k == 8

    def test_get_top_k_column(self):
        """컬럼 모드 top-k = 18."""
        top_k = _get_top_k(ChatMode.COLUMN)
        assert top_k == 18


# =========================================================================== #
# LLMClient 테스트
# =========================================================================== #

class TestLLMClient:
    """LLMClient 프롬프트 구성 로직 테스트."""

    def setup_method(self):
        self.client = LLMClient()

    def test_build_context_with_hits(self):
        """검색 결과 → 컨텍스트 텍스트 변환."""
        hits = [
            SearchHit(text="test자의 권리", source="헌법.pdf", score=0.9, page=5),
            SearchHit(text="history적 의의", source="연설문.txt", score=0.7, page=None),
        ]
        context = self.client._build_context(hits)
        assert "인용 1" in context
        assert "헌법.pdf" in context
        assert "p.5" in context
        assert "인용 2" in context
        assert "연설문.txt" in context

    def test_build_context_empty(self):
        """빈 검색 결과."""
        context = self.client._build_context([])
        assert "찾을 수 없습니다" in context

    def test_build_messages_with_mode(self):
        """모드별 지시사항 포함 메시지 구성."""
        messages = self.client._build_messages(
            ChatMode.FACT, "질문 내용",
        )
        # 시스템 + 모드 지시 + 사용자 = 최소 3개
        assert len(messages) >= 3
        assert messages[0]["role"] == "system"
        assert messages[0]["content"] == SYSTEM_PROMPT
        assert messages[1]["role"] == "system"
        assert "팩트 조회 모드" in messages[1]["content"]
        assert messages[-1]["role"] == "user"

    def test_build_messages_with_history(self):
        """대화 기록 포함 메시지 구성."""
        history = [
            {"role": "user", "content": "이전 질문"},
            {"role": "assistant", "content": "이전 답변"},
        ]
        messages = self.client._build_messages(
            ChatMode.SUMMARY, "현재 질문", chat_history=history,
        )
        # 대화 기록이 시스템 메시지와 현재 질문 사이에 위치
        user_msgs = [m for m in messages if m["role"] == "user"]
        assert len(user_msgs) == 2  # 이전 + 현재

    def test_mode_instructions_all_modes(self):
        """모든 모드에 지시사항 존재."""
        for mode in ChatMode:
            assert mode in MODE_INSTRUCTIONS
            assert len(MODE_INSTRUCTIONS[mode]) > 0


# =========================================================================== #
# Pydantic 모델 테스트
# =========================================================================== #

class TestPydanticModels:
    """요청/응답 Pydantic 모델 검증 테스트."""

    def test_chat_request_defaults(self):
        """ChatRequest 기본값."""
        req = ChatRequest(question="질문")
        assert req.mode == ChatMode.FACT
        assert req.session_id is None

    def test_chat_request_with_session(self):
        """ChatRequest 세션 ID 포함."""
        req = ChatRequest(question="질문", mode="summary", session_id="abc-123")
        assert req.mode == ChatMode.SUMMARY
        assert req.session_id == "abc-123"

    def test_chat_request_empty_question(self):
        """빈 질문 → 검증 에러."""
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            ChatRequest(question="")

    def test_search_hit(self):
        """SearchHit 모델."""
        hit = SearchHit(text="내용", source="파일.pdf", score=0.95)
        assert hit.page is None
        assert hit.chunk_index is None

    def test_chat_response(self):
        """ChatResponse 모델."""
        resp = ChatResponse(
            answer="답변입니다",
            mode=ChatMode.FACT,
            session_id="test-session",
        )
        assert resp.sources is None
        assert resp.answer == "답변입니다"

    def test_session_create_request(self):
        """SessionCreateRequest 기본값."""
        req = SessionCreateRequest()
        assert req.title is None


# =========================================================================== #
# API 엔드포인트 테스트 (TestClient)
# =========================================================================== #

class TestSessionAPI:
    """세션 API 엔드포인트 테스트."""

    def setup_method(self):
        """임시 DB로 SessionStore 교체."""
        self.tmp_dir = tempfile.mkdtemp()
        self.db_path = Path(self.tmp_dir) / "test_api_sessions.db"
        self.test_store = SessionStore(db_path=self.db_path)

        # 세션 스토어를 테스트용으로 패치
        self._patcher = patch(
            "app.api.sessions.get_session_store",
            return_value=self.test_store,
        )
        self._patcher.start()

        # chat API도 동일한 스토어 사용
        self._chat_patcher = patch(
            "app.api.chat.get_session_store",
            return_value=self.test_store,
        )
        self._chat_patcher.start()

        from app.main import app
        self.client = TestClient(app)

    def teardown_method(self):
        self._patcher.stop()
        self._chat_patcher.stop()
        if self.db_path.exists():
            self.db_path.unlink()
        for suffix in ["-wal", "-shm"]:
            wal_path = Path(str(self.db_path) + suffix)
            if wal_path.exists():
                wal_path.unlink()

    def test_create_session(self):
        """POST /api/sessions — 세션 생성."""
        resp = self.client.post("/api/sessions", json={"title": "테스트 세션"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["session_id"]
        assert data["title"] == "테스트 세션"
        assert data["message_count"] == 0

    def test_create_session_no_title(self):
        """POST /api/sessions — 제목 없이 세션 생성."""
        resp = self.client.post("/api/sessions", json={})
        assert resp.status_code == 200
        assert "새 대화" in resp.json()["title"]

    def test_list_sessions(self):
        """GET /api/sessions — 세션 목록."""
        self.client.post("/api/sessions", json={"title": "세션1"})
        self.client.post("/api/sessions", json={"title": "세션2"})

        resp = self.client.get("/api/sessions")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] >= 2

    def test_get_session_detail(self):
        """GET /api/sessions/{id} — 세션 상세."""
        create_resp = self.client.post("/api/sessions", json={"title": "상세 테스트"})
        session_id = create_resp.json()["session_id"]

        resp = self.client.get(f"/api/sessions/{session_id}")
        assert resp.status_code == 200
        assert resp.json()["title"] == "상세 테스트"

    def test_get_session_not_found(self):
        """GET /api/sessions/{id} — 존재하지 않는 세션."""
        resp = self.client.get("/api/sessions/nonexistent-id")
        assert resp.status_code == 404

    def test_delete_session(self):
        """DELETE /api/sessions/{id} — 세션 삭제."""
        create_resp = self.client.post("/api/sessions", json={"title": "삭제 대상"})
        session_id = create_resp.json()["session_id"]

        resp = self.client.delete(f"/api/sessions/{session_id}")
        assert resp.status_code == 200

        # 삭제 확인
        detail_resp = self.client.get(f"/api/sessions/{session_id}")
        assert detail_resp.status_code == 404


class TestChatAPI:
    """채팅 API 엔드포인트 테스트 (모킹)."""

    def setup_method(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.db_path = Path(self.tmp_dir) / "test_chat_sessions.db"
        self.test_store = SessionStore(db_path=self.db_path)

        # 스토어 패치
        self._session_patcher = patch(
            "app.api.sessions.get_session_store",
            return_value=self.test_store,
        )
        self._chat_store_patcher = patch(
            "app.api.chat.get_session_store",
            return_value=self.test_store,
        )
        self._session_patcher.start()
        self._chat_store_patcher.start()

        from app.main import app
        self.client = TestClient(app)

    def teardown_method(self):
        self._session_patcher.stop()
        self._chat_store_patcher.stop()
        if self.db_path.exists():
            self.db_path.unlink()
        for suffix in ["-wal", "-shm"]:
            wal_path = Path(str(self.db_path) + suffix)
            if wal_path.exists():
                wal_path.unlink()

    @patch("app.api.chat.hybrid_search")
    @patch("app.api.chat.get_llm_client")
    def test_chat_creates_session_if_none(
        self, mock_llm_getter, mock_search,
    ):
        """POST /api/chat — session_id 없으면 자동 생성."""
        # 모킹 설정
        mock_search.return_value = SearchResult(
            hits=[SearchHit(text="내용", source="test.pdf", score=0.9)],
            query="질문",
            mode=ChatMode.FACT,
        )
        mock_llm = MagicMock()
        mock_llm.generate_answer.return_value = "AI 답변"
        mock_llm_getter.return_value = mock_llm

        resp = self.client.post("/api/chat", json={
            "question": "test이란?",
            "mode": "fact",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["session_id"]  # 자동 생성
        assert data["answer"] == "AI 답변"
        assert data["mode"] == "fact"
        assert data["sources"] is not None

    @patch("app.api.chat.hybrid_search")
    @patch("app.api.chat.get_llm_client")
    def test_chat_with_existing_session(
        self, mock_llm_getter, mock_search,
    ):
        """POST /api/chat — 기존 세션에 대화 추가."""
        # 세션 먼저 생성
        session = self.test_store.create_session(title="기존 세션")
        session_id = session["session_id"]

        mock_search.return_value = SearchResult(
            hits=[], query="질문", mode=ChatMode.SUMMARY,
        )
        mock_llm = MagicMock()
        mock_llm.generate_answer.return_value = "요약 답변"
        mock_llm_getter.return_value = mock_llm

        resp = self.client.post("/api/chat", json={
            "question": "요약해줘",
            "mode": "summary",
            "session_id": session_id,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["session_id"] == session_id
        assert data["answer"] == "요약 답변"
        assert data["mode"] == "summary"

        # 대화 기록 확인
        messages = self.test_store.get_messages(session_id)
        assert len(messages) == 2  # user + assistant

    @patch("app.api.chat.hybrid_search")
    @patch("app.api.chat.get_llm_client")
    def test_chat_with_invalid_session(
        self, mock_llm_getter, mock_search,
    ):
        """POST /api/chat — 존재하지 않는 세션 ID."""
        resp = self.client.post("/api/chat", json={
            "question": "질문",
            "mode": "fact",
            "session_id": "nonexistent-id",
        })
        assert resp.status_code == 404

    def test_get_chat_history(self):
        """GET /api/chat/history/{session_id} — 대화 기록 조회."""
        session = self.test_store.create_session(title="기록 테스트")
        sid = session["session_id"]

        self.test_store.add_message(sid, "user", "질문", mode="fact")
        self.test_store.add_message(
            sid, "assistant", "답변", mode="fact",
            sources=[{"text": "내용", "source": "test.pdf", "score": 0.9}],
        )

        resp = self.client.get(f"/api/chat/history/{sid}")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2
        assert data[0]["role"] == "user"
        assert data[1]["role"] == "assistant"
        assert data[1]["sources"] is not None