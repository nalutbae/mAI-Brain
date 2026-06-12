"""mAI-Brain — 외부 API 키 모델 및 저장소

API 키를 발급/관리하여 홈페이지 방문자용 챗봇 OpenAPI를 제공합니다.
키는 data/api_keys.json에 저장되며, 실제 키 값은 해시되어 저장됩니다.
"""

import hashlib
import os
import json
import secrets
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field


# ── Pydantic 모델 ──────────────────────────────────────────────────────────

class ApiKeyCreate(BaseModel):
    """API 키 생성 요청"""
    name: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="키 이름 (예: '홈페이지 챗봇', '파트너 A')",
    )
    description: Optional[str] = Field(
        default=None,
        max_length=500,
        description="키 설명",
    )
    rate_limit: int = Field(
        default=60,
        ge=1,
        description="분당 요청 제한 (기본 60)",
    )


class ApiKeyResponse(BaseModel):
    """API 키 응답 (키 값 마스킹)"""
    id: str
    name: str
    description: Optional[str] = None
    key_prefix: str = Field(..., description="키 접두사 (mai_************)")
    rate_limit: int
    is_active: bool = True
    created_at: str
    last_used_at: Optional[str] = None
    usage_count: int = 0


class ApiKeyCreateResponse(ApiKeyResponse):
    """API 키 생성 응답 (평문 키 포함 — 생성 시 1회만 노출)"""
    api_key: str = Field(..., description="평문 API 키 (다시 볼 수 없음)")


# ── 저장소 ────────────────────────────────────────────────────────────────

class ApiKeyStore:
    """API 키 파일 기반 저장소.

    - 키 생성 시: 평문 키를 1회 반환, 저장은 SHA-256 해시만 보관
    - 키 검증 시: 요청 키를 해시하여 저장된 해시와 비교
    - 파일 위치: data/api_keys.json
    """

    _KEY_PREFIX = "mai_"
    _HASH_ALGO = "sha256"

    def __init__(self, data_dir: Optional[str] = None):
        if data_dir is None:
            data_dir = os.environ.get(
                "MAI_BRAIN_DATA_DIR",
                str(Path(__file__).resolve().parent.parent.parent / "data"),
            )
        self._data_dir = Path(data_dir)
        self._data_dir.mkdir(parents=True, exist_ok=True)
        self._path = self._data_dir / "api_keys.json"
        self._keys: dict = {}
        self._load()

    # ── 내부 유틸리티 ────────────────────────────────────────────────

    @staticmethod
    def _hash_key(key: str) -> str:
        """API 키를 SHA-256 해시로 변환."""
        return hashlib.sha256(key.encode()).hexdigest()

    @staticmethod
    def _now_iso() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _generate_key() -> str:
        """안전한 랜덤 API 키 생성 (mai_ 접두사 + 32바이트 hex)."""
        return f"mai_{secrets.token_hex(32)}"

    # ── 영속화 ────────────────────────────────────────────────────────

    def _load(self):
        """저장된 키 데이터 로드."""
        if self._path.exists():
            try:
                self._keys = json.loads(self._path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, ValueError):
                self._keys = {}
        else:
            self._keys = {}

    def _save(self):
        """키 데이터를 파일에 저장."""
        self._path.write_text(
            json.dumps(self._keys, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    # ── 공개 API ──────────────────────────────────────────────────────

    def create_key(self, req: ApiKeyCreate) -> ApiKeyCreateResponse:
        """새 API 키 생성. 평문 키는 이때 1회만 반환됩니다."""
        raw_key = self._generate_key()
        key_hash = self._hash_key(raw_key)
        key_id = secrets.token_hex(8)  # 짧은 공개 ID

        now = self._now_iso()
        record = {
            "id": key_id,
            "name": req.name,
            "description": req.description,
            "key_hash": key_hash,
            "key_prefix": f"{raw_key[:8]}...{raw_key[-4:]}",
            "rate_limit": req.rate_limit,
            "is_active": True,
            "created_at": now,
            "last_used_at": None,
            "usage_count": 0,
        }

        self._keys[key_id] = record
        self._save()

        return ApiKeyCreateResponse(
            id=key_id,
            name=req.name,
            description=req.description,
            key_prefix=record["key_prefix"],
            rate_limit=req.rate_limit,
            is_active=True,
            created_at=now,
            last_used_at=None,
            usage_count=0,
            api_key=raw_key,  # 평문 키 — 이때만 반환
        )

    def validate_key(self, raw_key: str) -> Optional[dict]:
        """요청 키 검증. 유효하면 키 레코드를 반환하고 usage를 갱신."""
        if not raw_key.startswith(self._KEY_PREFIX):
            return None

        key_hash = self._hash_key(raw_key)

        for key_id, record in self._keys.items():
            if record.get("key_hash") == key_hash and record.get("is_active", True):
                # 사용 기록 갱신
                record["last_used_at"] = self._now_iso()
                record["usage_count"] = record.get("usage_count", 0) + 1
                self._save()
                return record

        return None

    def list_keys(self) -> list[ApiKeyResponse]:
        """모든 API 키 목록 (키 값 제외)."""
        result = []
        for record in self._keys.values():
            result.append(ApiKeyResponse(
                id=record["id"],
                name=record["name"],
                description=record.get("description"),
                key_prefix=record["key_prefix"],
                rate_limit=record.get("rate_limit", 60),
                is_active=record.get("is_active", True),
                created_at=record["created_at"],
                last_used_at=record.get("last_used_at"),
                usage_count=record.get("usage_count", 0),
            ))
        return result

    def get_key(self, key_id: str) -> Optional[ApiKeyResponse]:
        """특정 API 키 정보 조회."""
        record = self._keys.get(key_id)
        if not record:
            return None
        return ApiKeyResponse(
            id=record["id"],
            name=record["name"],
            description=record.get("description"),
            key_prefix=record["key_prefix"],
            rate_limit=record.get("rate_limit", 60),
            is_active=record.get("is_active", True),
            created_at=record["created_at"],
            last_used_at=record.get("last_used_at"),
            usage_count=record.get("usage_count", 0),
        )

    def rotate_key(self, key_id: str) -> Optional[ApiKeyCreateResponse]:
        """기존 키를 비활성화하고 새 키 발급 (키 회전)."""
        record = self._keys.get(key_id)
        if not record:
            return None

        # 기존 키 비활성화
        record["is_active"] = False

        # 새 키 발급
        new_key = self._generate_key()
        new_hash = self._hash_key(new_key)
        new_id = secrets.token_hex(8)
        now = self._now_iso()

        new_record = {
            "id": new_id,
            "name": record["name"],
            "description": record.get("description"),
            "key_hash": new_hash,
            "key_prefix": f"{new_key[:8]}...{new_key[-4:]}",
            "rate_limit": record.get("rate_limit", 60),
            "is_active": True,
            "created_at": now,
            "last_used_at": None,
            "usage_count": 0,
            "rotated_from": key_id,  # 회전 추적
        }

        self._keys[new_id] = new_record
        self._save()

        return ApiKeyCreateResponse(
            id=new_id,
            name=record["name"],
            description=record.get("description"),
            key_prefix=new_record["key_prefix"],
            rate_limit=new_record["rate_limit"],
            is_active=True,
            created_at=now,
            last_used_at=None,
            usage_count=0,
            api_key=new_key,
        )

    def deactivate_key(self, key_id: str) -> bool:
        """API 키 비활성화 (삭제 대신)."""
        record = self._keys.get(key_id)
        if not record:
            return False
        record["is_active"] = False
        self._save()
        return True

    def delete_key(self, key_id: str) -> bool:
        """API 키 완전 삭제."""
        if key_id not in self._keys:
            return False
        del self._keys[key_id]
        self._save()
        return True


# ── 싱글톤 ───────────────────────────────────────────────────────────────

_api_key_store: Optional[ApiKeyStore] = None


def get_api_key_store() -> ApiKeyStore:
    """ApiKeyStore 싱글톤 인스턴스 반환."""
    global _api_key_store
    if _api_key_store is None:
        _api_key_store = ApiKeyStore()
    return _api_key_store