"""mAI-Brain — 외부용 OpenAPI v1 라우터

X-API-Key 인증이 적용된 공개 챗 API.
홈페이지 방문자용 챗봇이나 서드파티 연동에 사용합니다.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException

from app.config import ChatMode
from app.core.auth import verify_api_key
from app.models.chat import ChatRequest, ChatResponse

logger = logging.getLogger(__name__)
router = APIRouter(
    dependencies=[Depends(verify_api_key)],
)


class V1ChatRequest(ChatRequest):
    """외부 API v1 채팅 요청.

    기존 ChatRequest와 동일한 스키마.
    X-API-Key 헤더로 인증 (router-level Depends).
    """
    pass


class V1ChatResponse(ChatResponse):
    """외부 API v1 채팅 응답."""
    pass


# ── 엔드포인트 ──────────────────────────────────────────────────────────────

@router.post("/chat", response_model=V1ChatResponse)
async def v1_chat(
    request: V1ChatRequest,
    api_key_record: dict = Depends(verify_api_key),
):
    """외부용 채팅 API.

    X-API-Key 헤더로 인증된 요청만 처리합니다.
    내부 /api/chat과 동일한 로직이지만 API 키 인증이 필수입니다.
    """
    from app.api.chat import _handle_normal_mode
    from app.core.session_store import get_session_store

    logger.info(
        "v1 채팅 요청: api_key=%s, mode=%s, question=%s",
        api_key_record.get("key_prefix", "unknown"),
        request.mode.value,
        request.question[:50],
    )

    try:
        store = get_session_store()
        response = await _handle_normal_mode(request, store)
        return response
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("v1 채팅 오류: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"채팅 응답 생성 중 오류가 발생했습니다: {exc}",
        ) from exc


@router.get("/modes")
async def v1_modes():
    """사용 가능한 채팅 모드 목록."""
    return {
        "modes": [
            {"key": m.value, "label": _mode_label(m)}
            for m in ChatMode
        ],
    }


def _mode_label(mode: ChatMode) -> str:
    labels = {
        ChatMode.FACT: "팩트 조회",
        ChatMode.SUMMARY: "요약",
        ChatMode.COLUMN: "컬럼 작성",
        ChatMode.REASONING: "추론",
        ChatMode.CREATIVE: "창의적 대화",
    }
    return labels.get(mode, mode.value)