"""mAI-Brain — FastAPI 애플리케이션 진입점

CORS 미들웨어 설정, API 라우터 등록, 헬스체크 엔드포인트
"""

import asyncio
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from scalar_fastapi import get_scalar_api_reference

from app.config import get_settings

settings = get_settings()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """애플리케이션 수명 주기 관리"""
    from app.core.qdrant import get_qdrant

    max_retries = 30
    for attempt in range(1, max_retries + 1):
        try:
            qdrant = get_qdrant()
            if qdrant.health_check():
                logger.info("Qdrant 연결 성공 (시도 %d/%d)", attempt, max_retries)
                break
        except Exception:
            pass
        if attempt < max_retries:
            logger.info("Qdrant 연결 대기 중... (시도 %d/%d)", attempt, max_retries)
            await asyncio.sleep(2)
    else:
        logger.warning(
            "Qdrant 연결 실패 (%d회 시도) - 서비스는 시작하지만 검색 기능이 동작하지 않을 수 있습니다",
            max_retries,
        )

    # 임베딩 모델 사전 로드 (백그라운드 스레드에서 실행하여 이벤트 루프 블로킹 방지)
    logger.info("임베딩 모델 사전 로드 시작...")
    loop = asyncio.get_running_loop()

    def _preload_embedding():
        try:
            from app.core.embedding import get_embedding_provider
            provider = get_embedding_provider()
            logger.info("임베딩 모델 사전 로드 완료: %s", type(provider).__name__)
        except Exception:
            logger.exception("임베딩 모델 사전 로드 실패 - 첫 인덱싱 시 로드됩니다")

    await loop.run_in_executor(None, _preload_embedding)

    # 에이전트 도구 등록
    from app.core.agent_tools import WebSearchTool, SummarizeDocumentTool, GenerateChartTool, SaveFileTool
    from app.core.agent_tools.registry import get_tool_registry
    _registry = get_tool_registry()
    _registry.register(WebSearchTool())
    _registry.register(SummarizeDocumentTool())
    _registry.register(GenerateChartTool())
    _registry.register(SaveFileTool())
    logger.info("에이전트 도구 %d개 등록 완료", len(_registry.get_tool_names()))

    yield

    logger.info("mAI-Brain 서비스 종료")


app = FastAPI(
    title=settings.app_name,
    description="mAI-Brain — 지식 기반 검색 증강 답변 플랫폼",
    version="0.2.0",
    debug=settings.debug,
    lifespan=lifespan,
    redirect_slashes=False,  # nginx 프록시 환경에서 307 리다이렉트 CORS 문제 방지
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── 헬스체크 ──────────────────────────────────────────────────────────────
@app.get("/health")
async def health_check():
    return {"status": "ok", "app": settings.app_name}


@app.get("/")
async def root():
    return {
        "app": settings.app_name,
        "version": "0.2.0",
        "docs": "/docs",
        "scalar": "/scalar",
        "health": "/health",
    }


# ── Scalar API 문서 ──────────────────────────────────────────────────────

@app.get("/scalar", include_in_schema=False)
async def scalar_html():
    """Scalar API 문서 UI (Swagger UI 대신 모던한 인터페이스)."""
    return get_scalar_api_reference(
        openapi_url=app.openapi_url,
        title=f"{settings.app_name} — API 문서",
    )


# ── 라우터 등록 ───────────────────────────────────────────────────────────
from app.api import documents
app.include_router(documents.router, prefix="/api/documents", tags=["documents"])

from app.api import (
    chat,
    chat_stream,
    chunking,
    cross_reasoning,
    evaluation,
    feedback,
    sessions,
    settings as settings_api,
    voice,
    widget,
    workspace,
)
app.include_router(chat.router, prefix="/api/chat", tags=["chat"])
app.include_router(chat_stream.router, prefix="/api/chat/stream", tags=["chat-stream"])
app.include_router(chunking.router, prefix="/api/chunking", tags=["chunking"])
app.include_router(cross_reasoning.router, prefix="/api/cross-reasoning", tags=["cross-reasoning"])
app.include_router(evaluation.router, prefix="/api/evaluation", tags=["evaluation"])
app.include_router(feedback.router, prefix="/api/feedback", tags=["feedback"])
app.include_router(sessions.router, prefix="/api/sessions", tags=["sessions"])
app.include_router(settings_api.router, prefix="/api/settings", tags=["settings"])
app.include_router(voice.router, prefix="/api/voice", tags=["voice"])
app.include_router(widget.router, prefix="/api/widget", tags=["widget"])
app.include_router(workspace.router, prefix="/api/workspaces", tags=["workspaces"])

# ── API 키 관리 (관리자용) ──────────────────────────────────────────────────
from app.api import api_keys, auth, admin_users
app.include_router(api_keys.router, prefix="/api/api-keys", tags=["api-keys"])

# ── 인증 ──────────────────────────────────────────────────────────────────────
app.include_router(auth.router, prefix="/api/auth", tags=["auth"])

# ── 관리자: 사용자 관리 ──────────────────────────────────────────────────────
app.include_router(admin_users.router, prefix="/api/admin/users", tags=["admin-users"])

# ── 외부용 OpenAPI v1 (X-API-Key 인증 필요) ────────────────────────────────
from app.api import v1
app.include_router(v1.router, prefix="/api/v1", tags=["v1"])