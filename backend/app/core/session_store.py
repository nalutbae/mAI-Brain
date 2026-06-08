"""mAI-Brain AI 챗봇 — 세션 대화 기록 저장소

SQLite 기반 세션별 대화 기록 관리.
- 세션 생성/조회/목록
- 메시지 추가/조회
- 이전 대화 컨텍스트를 LLM 프롬프트에 포함 가능

저장 위치: backend/data/sessions.db (환경변수 SESSIONS_DB_PATH로 오버라이드 가능)
"""

from __future__ import annotations

import json
import logging
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import sqlite3

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# DB 경로
# --------------------------------------------------------------------------- #

def _get_db_path() -> Path:
    """sessions.db 파일 경로 반환.

    기본: 프로젝트 루트/data/sessions.db
    환경변수 SESSIONS_DB_PATH로 오버라이드 가능.
    """
    env_path = os.environ.get("SESSIONS_DB_PATH")
    if env_path:
        return Path(env_path)

    project_root = Path(__file__).resolve().parent.parent.parent.parent
    db_dir = project_root / "data"
    db_dir.mkdir(parents=True, exist_ok=True)
    return db_dir / "sessions.db"


# --------------------------------------------------------------------------- #
# 스키마
# --------------------------------------------------------------------------- #

_SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    session_id  TEXT PRIMARY KEY,
    title       TEXT NOT NULL,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS messages (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id  TEXT NOT NULL,
    role        TEXT NOT NULL CHECK(role IN ('user', 'assistant', 'system')),
    content     TEXT NOT NULL,
    mode        TEXT,                    -- 채팅 모드 (fact/summary/column), nullable
    sources     TEXT,                    -- JSON: 검색 출처 (assistant만), nullable
    created_at  TEXT NOT NULL,
    FOREIGN KEY (session_id) REFERENCES sessions(session_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id, created_at);
CREATE INDEX IF NOT EXISTS idx_sessions_updated ON sessions(updated_at DESC);
"""


# --------------------------------------------------------------------------- #
# 세션 저장소
# --------------------------------------------------------------------------- #

class SessionStore:
    """SQLite 기반 세션/메시지 저장소.

    스레드 안전: 각 메서드 호출 시 새 커넥션을 열고 닫음.
    (FastAPI는 비동기이지만 DB 작업은 동기 실행 컨텍스트에서 처리)
    """

    def __init__(self, db_path: Optional[Path] = None) -> None:
        self._db_path = db_path or _get_db_path()
        self._init_db()

    def _init_db(self) -> None:
        """DB 스키마 초기화 (최초 1회)."""
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(str(self._db_path)) as conn:
            conn.executescript(_SCHEMA)
        logger.info("sessions.db 초기화 완료: %s", self._db_path)

    def _get_conn(self) -> sqlite3.Connection:
        """SQLite 커넥션 반환 (row factory 설정)."""
        conn = sqlite3.connect(str(self._db_path))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")  # 동시 읽기 허용
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    # --------------------------------------------------------------- #
    # 세션 CRUD
    # --------------------------------------------------------------- #

    def create_session(self, title: Optional[str] = None) -> dict:
        """새 세션 생성.

        Args:
            title: 세션 제목 (미지정 시 "새 대화" + 타임스탬프)

        Returns:
            세션 정보 딕셔너리
        """
        session_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        if not title:
            title = f"새 대화 ({datetime.now().strftime('%m/%d %H:%M')})"

        with self._get_conn() as conn:
            conn.execute(
                "INSERT INTO sessions (session_id, title, created_at, updated_at) VALUES (?, ?, ?, ?)",
                (session_id, title, now, now),
            )

        logger.info("세션 생성: id=%s, title=%s", session_id[:8], title)
        return {
            "session_id": session_id,
            "title": title,
            "created_at": now,
            "updated_at": now,
        }

    def get_session(self, session_id: str) -> Optional[dict]:
        """세션 정보 조회.

        Returns:
            세션 정보 딕셔너리, 없으면 None
        """
        with self._get_conn() as conn:
            row = conn.execute(
                "SELECT * FROM sessions WHERE session_id = ?",
                (session_id,),
            ).fetchone()

        if row is None:
            return None

        return dict(row)

    def list_sessions(self, limit: int = 50, offset: int = 0) -> list[dict]:
        """세션 목록 조회 (최근 업데이트순).

        Returns:
            세션 정보 리스트
        """
        with self._get_conn() as conn:
            rows = conn.execute(
                "SELECT * FROM sessions ORDER BY updated_at DESC LIMIT ? OFFSET ?",
                (limit, offset),
            ).fetchall()

        return [dict(r) for r in rows]

    def delete_session(self, session_id: str) -> bool:
        """세션 및 메시지 삭제.

        Returns:
            삭제 성공 여부
        """
        with self._get_conn() as conn:
            cursor = conn.execute(
                "DELETE FROM sessions WHERE session_id = ?",
                (session_id,),
            )
            return cursor.rowcount > 0

    # --------------------------------------------------------------- #
    # 메시지 CRUD
    # --------------------------------------------------------------- #

    def add_message(
        self,
        session_id: str,
        role: str,
        content: str,
        mode: Optional[str] = None,
        sources: Optional[list[dict]] = None,
    ) -> dict:
        """메시지 추가.

        Args:
            session_id: 세션 ID
            role: "user" | "assistant" | "system"
            content: 메시지 내용
            mode: 채팅 모드 (fact/summary/column)
            sources: 검색 출처 (assistant 메시지에만)

        Returns:
            추가된 메시지 정보
        """
        now = datetime.now(timezone.utc).isoformat()
        sources_json = json.dumps(sources, ensure_ascii=False) if sources else None

        with self._get_conn() as conn:
            conn.execute(
                """INSERT INTO messages (session_id, role, content, mode, sources, created_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (session_id, role, content, mode, sources_json, now),
            )
            # 세션 updated_at 갱신
            conn.execute(
                "UPDATE sessions SET updated_at = ? WHERE session_id = ?",
                (now, session_id),
            )

        return {
            "role": role,
            "content": content,
            "mode": mode,
            "sources": sources,
            "created_at": now,
        }

    def get_messages(
        self,
        session_id: str,
        limit: int = 100,
    ) -> list[dict]:
        """세션의 메시지 목록 조회 (시간순).

        Returns:
            메시지 딕셔너리 리스트
        """
        with self._get_conn() as conn:
            rows = conn.execute(
                """SELECT role, content, mode, sources, created_at
                   FROM messages
                   WHERE session_id = ?
                   ORDER BY created_at ASC
                   LIMIT ?""",
                (session_id, limit),
            ).fetchall()

        messages = []
        for r in rows:
            msg = {
                "role": r["role"],
                "content": r["content"],
                "mode": r["mode"],
                "created_at": r["created_at"],
            }
            # sources JSON 파싱
            if r["sources"]:
                try:
                    msg["sources"] = json.loads(r["sources"])
                except json.JSONDecodeError:
                    msg["sources"] = None
            messages.append(msg)

        return messages

    def get_chat_history(
        self,
        session_id: str,
        limit: int = 20,
    ) -> list[dict[str, str]]:
        """LLM 프롬프트용 대화 기록 반환.

        OpenAI Chat API 메시지 형식: [{"role": "...", "content": "..."}]

        최근 N개의 user/assistant 메시지만 반환.
        system 메시지는 LLM이 별도로 세팅하므로 제외.
        """
        with self._get_conn() as conn:
            rows = conn.execute(
                """SELECT role, content
                   FROM messages
                   WHERE session_id = ? AND role IN ('user', 'assistant')
                   ORDER BY created_at DESC
                   LIMIT ?""",
                (session_id, limit),
            ).fetchall()

        # 시간순으로 재배열 (DESC → ASC)
        rows = list(reversed(rows))

        return [{"role": r["role"], "content": r["content"]} for r in rows]

    def get_message_count(self, session_id: str) -> int:
        """세션의 메시지 수 반환."""
        with self._get_conn() as conn:
            row = conn.execute(
                "SELECT COUNT(*) as cnt FROM messages WHERE session_id = ?",
                (session_id,),
            ).fetchone()
        return row["cnt"] if row else 0


# --------------------------------------------------------------------------- #
# 싱글톤
# --------------------------------------------------------------------------- #

_session_store: Optional[SessionStore] = None


def get_session_store() -> SessionStore:
    """SessionStore 싱글톤 인스턴스 반환."""
    global _session_store
    if _session_store is None:
        _session_store = SessionStore()
    return _session_store