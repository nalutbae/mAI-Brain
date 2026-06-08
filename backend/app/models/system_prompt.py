"""mAI-Brain — 시스템 프롬프트 커스터마이제이션 모델

워크스페이스별/모드별 커스텀 시스템 프롬프트 관리.

핵심 개념:
- SystemPrompt: 워크스페이스+모드 조합에 대한 커스텀 프롬프트
- variables: 템플릿 변수({{workspace_name}}, {{document_count}}, {{mode}}, {{date}})
- is_default: 해당 모드의 기본 프롬프트 (워크스페이스 미지정 시 사용)
- 프리뷰: 변수 치환 결과를 미리 확인
"""

from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel, Field

from app.config import ChatMode


# ── 지원 변수 목록 ────────────────────────────────────────────────────────

SUPPORTED_VARIABLES = {
    "workspace_name": "워크스페이스 이름",
    "document_count": "워크스페이스 내 문서 수",
    "mode": "현재 채팅 모드 (fact/summary/column/reasoning)",
    "date": "현재 날짜 (YYYY-MM-DD)",
    "workspace_id": "워크스페이스 ID",
    "collection_name": "Qdrant 컬렉션명",
}


# ── Pydantic 모델 ──────────────────────────────────────────────────────────

class SystemPrompt(BaseModel):
    """시스템 프롬프트"""
    id: str
    workspace_id: Optional[str] = Field(
        default=None,
        description="워크스페이스 ID (None=기본 프롬프트)",
    )
    mode: ChatMode = Field(
        ...,
        description="채팅 모드 (fact/summary/column/reasoning)",
    )
    prompt_text: str = Field(
        ...,
        description="프롬프트 본문 ({{variable}} 템플릿 지원)",
    )
    variables: list[str] = Field(
        default_factory=list,
        description="사용 중인 변수 목록",
    )
    is_default: bool = Field(
        default=False,
        description="해당 모드의 기본 프롬프트 여부",
    )
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
    )
    updated_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
    )


class SystemPromptCreate(BaseModel):
    """시스템 프롬프트 생성 요청"""
    workspace_id: Optional[str] = Field(
        default=None,
        description="워크스페이스 ID (None=기본 프롬프트)",
    )
    mode: ChatMode = Field(
        ...,
        description="채팅 모드",
    )
    prompt_text: str = Field(
        ...,
        min_length=1,
        description="프롬프트 본문",
    )
    is_default: bool = Field(
        default=False,
        description="기본 프롬프트로 설정 여부",
    )


class SystemPromptUpdate(BaseModel):
    """시스템 프롬프트 수정 요청"""
    prompt_text: Optional[str] = Field(
        default=None,
        min_length=1,
        description="프롬프트 본문",
    )
    is_default: Optional[bool] = Field(
        default=None,
        description="기본 프롬프트로 설정 여부",
    )


class SystemPromptPreview(BaseModel):
    """프롬프트 미리보기 결과 (변수 치환 후)"""
    id: str
    mode: ChatMode
    workspace_id: Optional[str] = None
    original_text: str = Field(..., description="원본 프롬프트 (변수 미치환)")
    rendered_text: str = Field(..., description="치환된 프롬프트")
    variables_used: list[str] = Field(..., description="치환된 변수 목록")
    variables_missing: list[str] = Field(..., description="치환 불가능한 변수")


class SystemPromptListResponse(BaseModel):
    """프롬프트 목록 응답"""
    prompts: list[SystemPrompt]
    total: int