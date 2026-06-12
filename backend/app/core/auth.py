"""mAI-Brain — API 키 인증 미들웨어

X-API-Key 헤더를 검증하는 FastAPI 의존성과 미들웨어.
- /api/v1/* 경로에만 인증 적용
- 관리용 API (/api/api-keys, /api/chat 등)는 인증 없이 유지
"""

import logging
from typing import Optional

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import APIKeyHeader

from app.models.api_key import get_api_key_store

logger = logging.getLogger(__name__)

# ── FastAPI Security 의존성 ────────────────────────────────────────────────

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


async def verify_api_key(api_key: Optional[str] = Depends(api_key_header)) -> dict:
    """X-API-Key 헤더 검증 의존성.

    /api/v1/* 엔드포인트에서 Depends()로 주입하여 사용.
    유효하지 않으면 401 Unauthorized 반환.
    """
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="X-API-Key 헤더가 필요합니다.",
            headers={"WWW-Authenticate": "ApiKey"},
        )

    store = get_api_key_store()
    record = store.validate_key(api_key)

    if not record:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="유효하지 않은 API 키입니다.",
            headers={"WWW-Authenticate": "ApiKey"},
        )

    return record


# ── Starlette 미들웨어 (선택적 — 의존성 방식 대신 전역 적용 시 사용) ──

class ApiKeyMiddleware:
    """Starlette 미들웨어: /api/v1/* 경로에만 API 키 인증 적용.

    FastAPI Depends() 방식으로도 충분하지만, 미들웨어로 전역 적용하면
    라우터마다 Depends()를 추가하지 않아도 됩니다.
    """

    # 인증이 필요 없는 경로 접두사
    PUBLIC_PREFIXES = (
        "/docs",
        "/redoc",
        "/openapi.json",
        "/health",
        "/api/api-keys",   # 관리용 — 별도 인증 필요시 추가
        "/api/chat",       # 내부용
        "/api/documents",
        "/api/chunking",
        "/api/cross-reasoning",
        "/api/evaluation",
        "/api/feedback",
        "/api/sessions",
        "/api/settings",
        "/api/voice",
        "/api/widget",
        "/api/workspaces",
    )

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")

        # /api/v1/ 경로가 아니면 통과
        if not path.startswith("/api/v1/"):
            await self.app(scope, receive, send)
            return

        # /api/v1/ 경로 → X-API-Key 검증
        import json
        from starlette.responses import JSONResponse

        # 헤더에서 X-API-Key 추출
        headers = dict(scope.get("headers", []))
        api_key = None
        for key, value in headers.items():
            if key == b"x-api-key":
                api_key = value.decode("utf-8", errors="replace")
                break

        if not api_key:
            response = JSONResponse(
                status_code=401,
                content={"detail": "X-API-Key 헤더가 필요합니다."},
            )
            await response(scope, receive, send)
            return

        store = get_api_key_store()
        record = store.validate_key(api_key)

        if not record:
            response = JSONResponse(
                status_code=401,
                content={"detail": "유효하지 않은 API 키입니다."},
            )
            await response(scope, receive, send)
            return

        # 인증 성공 — scope에 키 정보 저장
        scope.setdefault("state", {})
        if isinstance(scope.get("state"), dict):
            scope["state"]["api_key_record"] = record

        await self.app(scope, receive, send)