"""mAI-Brain — 임베디드 채팅 위젯 데이터 모델

위젯 설정과 익명 토큰 발급에 사용되는 Pydantic 모델.

핵심 개념:
- WidgetConfig: 위젯 설정 (CORS, 테마, 인사말, 워크스페이스 등)
- WidgetToken: 익명 접근용 JWT 토큰
- 테마: 색상, 로고, 위치 등 커스터마이징 가능
"""

import secrets
from datetime import datetime, timezone
from typing import Optional
from pydantic import BaseModel, Field


# ── 위젯 테마 ────────────────────────────────────────────────────────────

class WidgetTheme(BaseModel):
    """위젯 테마 설정"""
    primary_color: str = Field(
        default="#3B82F6",
        description="주요 색상 (헤더, 버튼 등)",
    )
    background_color: str = Field(
        default="#FFFFFF",
        description="채팅 배경 색상",
    )
    text_color: str = Field(
        default="#1F2937",
        description="기본 텍스트 색상",
    )
    user_bubble_color: str = Field(
        default="#3B82F6",
        description="사용자 메시지 버블 색상",
    )
    user_bubble_text_color: str = Field(
        default="#FFFFFF",
        description="사용자 메시지 텍스트 색상",
    )
    assistant_bubble_color: str = Field(
        default="#F3F4F6",
        description="AI 메시지 버블 색상",
    )
    assistant_bubble_text_color: str = Field(
        default="#1F2937",
        description="AI 메시지 텍스트 색상",
    )
    border_radius: str = Field(
        default="12px",
        description="버블 테두리 둥글기",
    )
    font_family: str = Field(
        default="system-ui, -apple-system, sans-serif",
        description="폰트 패밀리",
    )


class WidgetPosition(str):
    """위젯 위치 설정"""
    BOTTOM_RIGHT = "bottom-right"
    BOTTOM_LEFT = "bottom-left"


# ── 위젯 설정 ────────────────────────────────────────────────────────────

class WidgetConfig(BaseModel):
    """위젯 설정"""
    id: str = Field(default_factory=lambda: secrets.token_hex(8))
    name: str = Field(
        default="mAI-Brain 위젯",
        description="위젯 표시 이름",
    )
    workspace_id: Optional[str] = Field(
        default=None,
        description="연결된 워크스페이스 ID (null이면 기본 워크스페이스)",
    )
    allowed_origins: list[str] = Field(
        default_factory=lambda: ["http://localhost:3000"],
        description="위젯 삽입을 허용할 오리진 목록 (CORS)",
    )
    greeting: str = Field(
        default="안녕하세요! 무엇을 도와드릴까요?",
        description="위젯 오픈 시 표시할 인사말",
    )
    theme: WidgetTheme = Field(
        default_factory=WidgetTheme,
        description="위젯 테마 설정",
    )
    position: str = Field(
        default="bottom-right",
        description="위젯 위치: bottom-right | bottom-left",
    )
    logo_url: Optional[str] = Field(
        default=None,
        description="위젯 헤더 로고 이미지 URL",
    )
    placeholder: str = Field(
        default="질문을 입력하세요...",
        description="입력 필드 플레이스홀더",
    )
    is_active: bool = Field(
        default=True,
        description="위젯 활성화 여부",
    )
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
    )
    updated_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
    )


class WidgetConfigCreate(BaseModel):
    """위젯 설정 생성 요청"""
    name: str = "mAI-Brain 위젯"
    workspace_id: Optional[str] = None
    allowed_origins: list[str] = ["http://localhost:3000"]
    greeting: str = "안녕하세요! 무엇을 도와드릴까요?"
    theme: WidgetTheme = Field(default_factory=WidgetTheme)
    position: str = "bottom-right"
    logo_url: Optional[str] = None
    placeholder: str = "질문을 입력하세요..."


class WidgetConfigUpdate(BaseModel):
    """위젯 설정 수정 요청"""
    name: Optional[str] = None
    workspace_id: Optional[str] = None
    allowed_origins: Optional[list[str]] = None
    greeting: Optional[str] = None
    theme: Optional[WidgetTheme] = None
    position: Optional[str] = None
    logo_url: Optional[str] = None
    placeholder: Optional[str] = None
    is_active: Optional[bool] = None


class WidgetConfigListResponse(BaseModel):
    """위젯 설정 목록 응답"""
    widgets: list[WidgetConfig]
    total: int


# ── 익명 토큰 ────────────────────────────────────────────────────────────

class WidgetTokenRequest(BaseModel):
    """위젯 익명 토큰 발급 요청"""
    widget_id: str = Field(
        ...,
        description="위젯 설정 ID",
    )
    origin: str = Field(
        ...,
        description="요청 오리진 (CORS 검증용)",
    )


class WidgetTokenResponse(BaseModel):
    """위젯 익명 토큰 발급 응답"""
    token: str = Field(
        ...,
        description="익명 접근 토큰 (API 인증용)",
    )
    widget_id: str = Field(
        ...,
        description="위젯 설정 ID",
    )
    expires_at: str = Field(
        ...,
        description="토큰 만료 시각 (ISO 8601)",
    )
    config: WidgetConfig = Field(
        ...,
        description="위젯 설정 (프론트엔드 초기 렌더링용)",
    )


# ── JS 스니펫 ─────────────────────────────────────────────────────────────

class WidgetSnippetResponse(BaseModel):
    """위젯 삽입 스니펫 응답"""
    widget_id: str
    snippet: str = Field(
        ...,
        description="HTML에 삽입할 <script> 태그 스니펫",
    )
    iframe_url: str = Field(
        ...,
        description="iframe 임베드 URL",
    )