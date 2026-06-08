"""mAI-Brain — 임베디드 위젯 설정 저장소 및 토큰 발급

JSON 파일 기반 위젯 설정 저장소.
HMAC-SHA256 기반 익명 토큰 발급 (외부 서비스 의존성 없음).

저장 위치: backend/data/widget_settings.json
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import secrets
import time
from pathlib import Path
from typing import Optional

from app.models.widget import WidgetSettings

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# 설정 파일 경로
# --------------------------------------------------------------------------- #

def _get_settings_path() -> Path:
    """widget_settings.json 파일 경로 반환."""
    env_path = os.environ.get("WIDGET_SETTINGS_PATH")
    if env_path:
        return Path(env_path)
    project_root = Path(__file__).resolve().parent.parent.parent
    data_dir = project_root / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir / "widget_settings.json"


def _get_token_secret() -> str:
    """토큰 서명용 비밀키 반환 (환경변수 또는 랜덤 생성)."""
    secret = os.environ.get("WIDGET_TOKEN_SECRET")
    if secret:
        return secret
    # 폴백: 머신별 고정 시크릿 생성 (재시작 시 기존 토큰 무효화됨)
    secret_path = Path(__file__).resolve().parent.parent.parent / "data" / ".widget_secret"
    if secret_path.exists():
        return secret_path.read_text().strip()
    new_secret = secrets.token_hex(32)
    secret_path.parent.mkdir(parents=True, exist_ok=True)
    secret_path.write_text(new_secret)
    return new_secret


# --------------------------------------------------------------------------- #
# 기본 설정
# --------------------------------------------------------------------------- #

_DEFAULT_SETTINGS = WidgetSettings()


# --------------------------------------------------------------------------- #
# 위젯 설정 저장소
# --------------------------------------------------------------------------- #

class WidgetSettingsStore:
    """JSON 파일 기반 위젯 설정 저장소.

    설정 파일이 없으면 기본값을 생성합니다.
    """

    def __init__(self, path: Optional[Path] = None):
        self.path = path or _get_settings_path()
        self._ensure_file()

    def _ensure_file(self) -> None:
        """설정 파일이 없으면 기본값으로 생성."""
        if not self.path.exists():
            self._write(_DEFAULT_SETTINGS.model_dump(mode="json"))

    def _read(self) -> dict:
        """설정 파일 읽기."""
        with open(self.path, "r", encoding="utf-8") as f:
            return json.load(f)

    def _write(self, data: dict) -> None:
        """설정 파일 쓰기."""
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def get_settings(self) -> WidgetSettings:
        """현재 위젯 설정 반환."""
        data = self._read()
        # 병합: 저장된 값이 없는 필드는 기본값 사용
        merged = _DEFAULT_SETTINGS.model_dump(mode="json")
        merged.update(data)
        return WidgetSettings(**merged)

    def update_settings(self, updates: dict) -> WidgetSettings:
        """위젯 설정 부분 업데이트.

        None이 아닌 필드만 업데이트합니다.
        """
        current = self._read()
        for key, value in updates.items():
            if value is not None:
                current[key] = value
        self._write(current)
        return WidgetSettings(**current)


# --------------------------------------------------------------------------- #
# 싱글톤
# --------------------------------------------------------------------------- #

_store: Optional[WidgetSettingsStore] = None


def get_widget_store() -> WidgetSettingsStore:
    """WidgetSettingsStore 싱글톤 반환."""
    global _store
    if _store is None:
        _store = WidgetSettingsStore()
    return _store


# --------------------------------------------------------------------------- #
# 토큰 발급
# --------------------------------------------------------------------------- #

class WidgetTokenIssuer:
    """익명 위젯 토큰 발급기.

    HMAC-SHA256 기반 간단한 서명 토큰을 사용합니다.
    외부 JWT 라이브러리 없이 동작하며, 익명 세션 식별에 충분합니다.
    """

    TOKEN_VERSION = 1
    DEFAULT_TTL = 86400  # 24시간

    def __init__(self, secret: Optional[str] = None):
        self.secret = secret or _get_token_secret()

    def issue_token(
        self,
        origin: str,
        workspace_id: str = "default",
        ttl: int = DEFAULT_TTL,
    ) -> str:
        """익명 토큰 발급.

        토큰 형식: v{version}.{payload_base64}.{signature_hex}
        페이로드: {workspace_id}:{origin}:{issued_at}:{expires_at}:{nonce}
        """
        issued_at = int(time.time())
        expires_at = issued_at + ttl
        nonce = secrets.token_hex(8)

        payload = f"{workspace_id}:{origin}:{issued_at}:{expires_at}:{nonce}"
        payload_b64 = _b64_encode(payload)

        signature = hmac.new(
            self.secret.encode("utf-8"),
            f"v{self.TOKEN_VERSION}.{payload_b64}".encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

        return f"v{self.TOKEN_VERSION}.{payload_b64}.{signature}"

    def verify_token(self, token: str) -> Optional[dict]:
        """토큰 검증 및 파싱.

        Returns:
            검증 성공 시 {workspace_id, origin, issued_at, expires_at, nonce}
            실패 시 None
        """
        try:
            parts = token.split(".")
            if len(parts) != 3:
                return None

            version_str, payload_b64, signature = parts
            if not version_str.startswith("v"):
                return None

            # 서명 검증
            expected_sig = hmac.new(
                self.secret.encode("utf-8"),
                f"{version_str}.{payload_b64}".encode("utf-8"),
                hashlib.sha256,
            ).hexdigest()

            if not hmac.compare_digest(signature, expected_sig):
                return None

            # 페이로드 디코딩
            payload = _b64_decode(payload_b64)
            fields = payload.split(":")
            if len(fields) != 5:
                return None

            workspace_id, origin, issued_at_str, expires_at_str, nonce = fields
            issued_at = int(issued_at_str)
            expires_at = int(expires_at_str)

            # 만료 검증
            if time.time() > expires_at:
                return None

            return {
                "workspace_id": workspace_id,
                "origin": origin,
                "issued_at": issued_at,
                "expires_at": expires_at,
                "nonce": nonce,
            }
        except Exception:
            return None


def get_token_issuer() -> WidgetTokenIssuer:
    """WidgetTokenIssuer 싱글톤 반환."""
    return WidgetTokenIssuer()


# --------------------------------------------------------------------------- #
# 헬퍼
# --------------------------------------------------------------------------- #

def _b64_encode(s: str) -> str:
    """URL-safe base64 인코딩."""
    import base64
    return base64.urlsafe_b64encode(s.encode("utf-8")).decode("utf-8").rstrip("=")


def _b64_decode(s: str) -> str:
    """URL-safe base64 디코딩."""
    import base64
    padding = 4 - len(s) % 4
    if padding != 4:
        s += "=" * padding
    return base64.urlsafe_b64decode(s).decode("utf-8")
