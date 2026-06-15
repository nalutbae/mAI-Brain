"""mAI-Brain — 서비스 챗봇 설정 API

GET  /api/service-chat/config     — 설정 조회 (프론트엔드 + 운영자)
PUT  /api/service-chat/config     — 설정 업데이트
POST /api/service-chat/config/reload — 파일 리로드 (직접 편집 후)
"""

from fastapi import APIRouter, HTTPException

from app.core.service_chat_config import get_service_chat_config_store
from app.models.service_chat import ServiceChatConfig

router = APIRouter()


@router.get("/config")
def get_service_chat_config():
    """서비스 챗봇 설정 조회."""
    store = get_service_chat_config_store()
    config = store.get_config()
    return config.model_dump(exclude_none=True)


@router.put("/config")
def update_service_chat_config(updates: dict):
    """서비스 챗봇 설정 업데이트.

    부분 업데이트 지원 — 변경할 필드만 전송.
    예: {"branding": {"bot_name": "새 이름"}, "faq": {"items": [...]}}
    """
    store = get_service_chat_config_store()
    try:
        updated = store.update_config(updates)
        return updated.model_dump(exclude_none=True)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"설정 업데이트 실패: {e}")


@router.post("/config/reload")
def reload_service_chat_config():
    """JSON 파일 리로드 — 운영자가 파일을 직접 편집한 후 호출."""
    store = get_service_chat_config_store()
    config = store.reload()
    return {
        "message": "설정이 리로드되었습니다.",
        "config": config.model_dump(exclude_none=True),
    }