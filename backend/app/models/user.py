"""mAI-Brain — 사용자 인증 모델 및 저장소

SQLite 기반 사용자 관리. 역할은 admin / user 두 가지.
비밀번호는 bcrypt로 해시하여 저장.
JWT 액세스 토큰 발급.
"""

import hashlib
import json
import logging
import os
import secrets
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import bcrypt
from pydantic import BaseModel, EmailStr

logger = logging.getLogger(__name__)

# ── 상수 ────────────────────────────────────────────────────────────────────

DEFAULT_DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"

ROLE_ADMIN = "admin"
ROLE_USER = "user"
VALID_ROLES = {ROLE_ADMIN, ROLE_USER}


# ── Pydantic 모델 ────────────────────────────────────────────────────────────

class UserCreate(BaseModel):
    username: str
    password: str
    display_name: Optional[str] = None


class UserLogin(BaseModel):
    username: str
    password: str


class UserResponse(BaseModel):
    id: str
    username: str
    display_name: Optional[str] = None
    role: str
    is_active: bool
    created_at: str
    last_login_at: Optional[str] = None


class RoleUpdate(BaseModel):
    role: str  # admin | user


class ActiveUpdate(BaseModel):
    is_active: bool


# ── SQLite 기반 사용자 저장소 ─────────────────────────────────────────────────

class UserStore:
    """SQLite 기반 사용자 저장소.

    data/users.db 에 저장. 환경변수 USERS_DB_PATH 로 오버라이드 가능.
    """

    def __init__(self, data_dir: Optional[Path] = None):
        self._db_path = self._resolve_db_path(data_dir)
        self._init_db()
        self._ensure_admin()

    @staticmethod
    def _resolve_db_path(data_dir: Optional[Path] = None) -> Path:
        env = os.environ.get("USERS_DB_PATH")
        if env:
            return Path(env)
        d = data_dir or DEFAULT_DATA_DIR
        d.mkdir(parents=True, exist_ok=True)
        return d / "users.db"

    def _init_db(self):
        import sqlite3
        # 빈/손상된 DB 파일은 삭제 후 재생성
        if self._db_path.exists() and self._db_path.stat().st_size == 0:
            logger.warning("빈 users.db 파일 감지 — 삭제 후 재생성: %s", self._db_path)
            self._db_path.unlink(missing_ok=True)
        conn = sqlite3.connect(str(self._db_path))
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id          TEXT PRIMARY KEY,
                username    TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                display_name TEXT,
                role        TEXT NOT NULL DEFAULT 'user',
                is_active   INTEGER NOT NULL DEFAULT 1,
                created_at  TEXT NOT NULL,
                last_login_at TEXT
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_users_username ON users(username)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_users_role ON users(role)")
        conn.commit()
        conn.close()

    def _ensure_admin(self):
        """초기 관리자 계정이 없으면 생성.

        환경변수 ADMIN_USERNAME / ADMIN_PASSWORD 로 설정.
        기본값: admin / admin (첫 로그인 후 변경 권장).
        """
        import sqlite3
        conn = sqlite3.connect(str(self._db_path))
        row = conn.execute("SELECT id FROM users WHERE role = ?", (ROLE_ADMIN,)).fetchone()
        if row:
            conn.close()
            return

        admin_user = os.environ.get("ADMIN_USERNAME", "admin")
        admin_pass = os.environ.get("ADMIN_PASSWORD", "admin")

        user_id = secrets.token_hex(16)
        pw_hash = bcrypt.hashpw(admin_pass.encode(), bcrypt.gensalt()).decode()
        now = datetime.now(timezone.utc).isoformat()

        conn.execute(
            "INSERT INTO users (id, username, password_hash, display_name, role, is_active, created_at) "
            "VALUES (?, ?, ?, ?, ?, 1, ?)",
            (user_id, admin_user, pw_hash, "관리자", ROLE_ADMIN, now),
        )
        conn.commit()
        conn.close()
        logger.info("초기 관리자 계정 생성: %s (첫 로그인 후 비밀번호 변경 권장)", admin_user)

    # ── CRUD ──────────────────────────────────────────────────────────────

    def create_user(self, username: str, password: str,
                    display_name: Optional[str] = None,
                    role: str = ROLE_USER) -> dict:
        import sqlite3

        if role not in VALID_ROLES:
            raise ValueError(f"잘못된 역할: {role}. 허용: {VALID_ROLES}")
        if len(username) < 2:
            raise ValueError("사용자 이름은 2자 이상이어야 합니다.")
        if len(password) < 4:
            raise ValueError("비밀번호는 4자 이상이어야 합니다.")

        pw_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
        user_id = secrets.token_hex(16)
        now = datetime.now(timezone.utc).isoformat()

        conn = sqlite3.connect(str(self._db_path))
        try:
            conn.execute(
                "INSERT INTO users (id, username, password_hash, display_name, role, is_active, created_at) "
                "VALUES (?, ?, ?, ?, ?, 1, ?)",
                (user_id, username, pw_hash, display_name, role, now),
            )
            conn.commit()
        except sqlite3.IntegrityError:
            conn.close()
            raise ValueError(f"사용자 이름이 이미 존재합니다: {username}")

        conn.close()
        return self.get_user(user_id)

    def authenticate(self, username: str, password: str) -> Optional[dict]:
        """사용자 인증. 성공 시 사용자 딕셔너리, 실패 시 None."""
        import sqlite3

        conn = sqlite3.connect(str(self._db_path))
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT * FROM users WHERE username = ? AND is_active = 1",
            (username,),
        ).fetchone()
        conn.close()

        if not row:
            return None

        stored_hash = row["password_hash"].encode()
        if not bcrypt.checkpw(password.encode(), stored_hash):
            return None

        # last_login_at 업데이트
        now = datetime.now(timezone.utc).isoformat()
        conn = sqlite3.connect(str(self._db_path))
        conn.execute("UPDATE users SET last_login_at = ? WHERE id = ?", (now, row["id"]))
        conn.commit()
        conn.close()

        return dict(row)

    def get_user(self, user_id: str) -> Optional[dict]:
        import sqlite3

        conn = sqlite3.connect(str(self._db_path))
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        conn.close()
        return dict(row) if row else None

    def get_user_by_username(self, username: str) -> Optional[dict]:
        import sqlite3

        conn = sqlite3.connect(str(self._db_path))
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
        conn.close()
        return dict(row) if row else None

    def list_users(self, limit: int = 50, offset: int = 0) -> list[dict]:
        import sqlite3

        conn = sqlite3.connect(str(self._db_path))
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM users ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (limit, offset),
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def update_role(self, user_id: str, role: str) -> Optional[dict]:
        if role not in VALID_ROLES:
            raise ValueError(f"잘못된 역할: {role}")

        import sqlite3
        conn = sqlite3.connect(str(self._db_path))
        conn.execute("UPDATE users SET role = ? WHERE id = ?", (role, user_id))
        conn.commit()
        affected = conn.total_changes
        conn.close()

        if not affected:
            return None
        return self.get_user(user_id)

    def update_active(self, user_id: str, is_active: bool) -> Optional[dict]:
        import sqlite3
        conn = sqlite3.connect(str(self._db_path))
        conn.execute("UPDATE users SET is_active = ? WHERE id = ?", (int(is_active), user_id))
        conn.commit()
        conn.close()
        return self.get_user(user_id)

    def update_password(self, user_id: str, new_password: str) -> bool:
        if len(new_password) < 4:
            raise ValueError("비밀번호는 4자 이상이어야 합니다.")

        pw_hash = bcrypt.hashpw(new_password.encode(), bcrypt.gensalt()).decode()
        import sqlite3
        conn = sqlite3.connect(str(self._db_path))
        conn.execute("UPDATE users SET password_hash = ? WHERE id = ?", (pw_hash, user_id))
        conn.commit()
        affected = conn.total_changes
        conn.close()
        return affected > 0

    def update_display_name(self, user_id: str, display_name: str) -> Optional[dict]:
        import sqlite3
        conn = sqlite3.connect(str(self._db_path))
        conn.execute("UPDATE users SET display_name = ? WHERE id = ?", (display_name, user_id))
        conn.commit()
        conn.close()
        return self.get_user(user_id)

    def delete_user(self, user_id: str) -> bool:
        import sqlite3
        conn = sqlite3.connect(str(self._db_path))
        conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
        conn.commit()
        affected = conn.total_changes
        conn.close()
        return affected > 0

    def user_count(self) -> int:
        import sqlite3
        conn = sqlite3.connect(str(self._db_path))
        count = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        conn.close()
        return count


# ── 싱글톤 ───────────────────────────────────────────────────────────────────

_user_store: Optional[UserStore] = None


def get_user_store() -> UserStore:
    global _user_store
    if _user_store is None:
        _user_store = UserStore()
    return _user_store