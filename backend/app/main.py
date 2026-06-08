"""mAI-Brain — FastAPI 애플리케이션 진입점"""

- CORS 미들웨어 설정
- API 라우터 등록
- 헬스체크 엔드포인트
"""

import asyncio
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from app.config import get_settings

settings = get_settings()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """애플리케이션 수명 주기 관리"""
    # Qdrant 연결 대기 (Docker compose 환경 대응)
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
            "Qdrant 연결 실패 (%d회 시도) — 서비스는 시작하지만 검색 기능이 동작하지 않을 수 있습니다",
            max_retries,
        )

    yield

    # 종료 시 정리
    logger.info("mAI-Brain 서비스 종료")


app = FastAPI(
    title=settings.app_name,
    description="mAI-Brain 도메인 특화 RAG 챗봇 API",
    version="0.1.0",
    debug=settings.debug,
    lifespan=lifespan,
)

# CORS 미들웨어 — Next.js 프론트엔드에서의 요청 허용
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
    """서비스 헬스체크"""
    return {"status": "ok", "app": settings.app_name}


@app.get("/")
async def root():
    """루트 엔드포인트 — API 개요"""
    return {
        "app": settings.app_name,
        "version": "0.1.0",
        "docs": "/docs",
        "health": "/health",
    }


# ── 라우터 등록 ───────────────────────────────────────────────────────────
from app.api import documents
app.include_router(documents.router, prefix="/api/documents", tags=["documents"])

from app.api import chat, sessions
app.include_router(chat.router, prefix="/api/chat", tags=["chat"])
app.include_router(sessions.router, prefix="/api/sessions", tags=["sessions"])