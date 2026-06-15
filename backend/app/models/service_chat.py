"""mAI-Brain — 서비스 챗봇 설정 모델

운영자가 JSON 파일 하나로 챗봇의 성격, 안내문구, FAQ, 객관식 선택지,
RAG 프롬프트를 완전 제어할 수 있는 구조.
"""

from datetime import datetime, timezone
from typing import Optional, Literal
from pydantic import BaseModel, Field


# ── 메타 ──────────────────────────────────────────────────────────────────

class ServiceChatMeta(BaseModel):
    version: int = 1
    updated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    description: str = "서비스 챗봇 설정 파일"


# ── 브랜딩 ─────────────────────────────────────────────────────────────────

class ServiceChatBranding(BaseModel):
    bot_name: str = "AI 서비스 어시스턴트"
    bot_emoji: str = "🤖"
    header_title: str = "서비스 챗봇"
    header_subtitle: str = "무엇이든 물어보세요 · AI 기반 실시간 상담"
    primary_color: str = "#2563eb"
    placeholder_text: str = "질문을 입력하세요..."


# ── 인사 메시지 ──────────────────────────────────────────────────────────

class ServiceChatGreeting(BaseModel):
    message: str = "안녕하세요! 👋 저는 **{{bot_name}}**입니다.\n\n궁금한 점이 있으시면 자유롭게 질문해 주세요."
    show_on_new_chat: bool = True


# ── 시스템 프롬프트 ──────────────────────────────────────────────────────

class ServiceChatModeInstructions(BaseModel):
    fact: str = ""
    summary: str = ""
    column: str = ""
    reasoning: str = ""
    creative: str = ""


class ServiceChatSystemPrompt(BaseModel):
    base: str = "당신은 {{bot_name}}입니다. 친근하고 도움이 되는 AI 상담사로서 방문자의 질문에 답변합니다."
    mode_instructions: ServiceChatModeInstructions = ServiceChatModeInstructions()
    user_prompt_template: str = (
        "다음 정보를 참고하여 질문에 답변해 주세요. "
        "답변은 자연스럽고 친근하게 작성하며, 출처나 인용 번호는 표시하지 마세요.\n\n"
        "[참고 정보]\n{context}\n\n[질문]\n{query}"
    )


# ── FAQ ───────────────────────────────────────────────────────────────────

class FaqItem(BaseModel):
    id: str
    icon: str = "📋"
    label: str
    question: str  # 클릭 시 LLM에 전송될 질문 텍스트


class ServiceChatFaq(BaseModel):
    section_title: str = "자주 묻는 질문"
    items: list[FaqItem] = []


# ── 객관식 선택지 (Quick Replies) ────────────────────────────────────────

class QuickReplyOption(BaseModel):
    id: str
    label: str
    type: Literal["question", "answer"] = "question"
    """question: LLM에 질문 전송, answer: 고정 답변 표시"""
    value: str = ""
    """question 타입: LLM에 전송할 질문. answer 타입: 빈 값 허용"""
    answer: Optional[str] = None
    """answer 타입일 때만 사용 — 고정 답변 텍스트 (마크다운 지원)"""


class QuickReplyGroup(BaseModel):
    id: str
    trigger: Literal["first_message", "after_answer", "always"] = "after_answer"
    """first_message: 첫 인사 후, after_answer: AI 답변 후, always: 항상"""
    title: str = "무엇을 도와드릴까요?"
    options: list[QuickReplyOption] = []


class ServiceChatQuickReplies(BaseModel):
    description: str = ""
    groups: list[QuickReplyGroup] = []


# ── 전체 설정 ────────────────────────────────────────────────────────────

class ServiceChatConfig(BaseModel):
    """서비스 챗봇 전체 설정 — service_chat_config.json 과 1:1 매핑"""
    meta: ServiceChatMeta = ServiceChatMeta()
    branding: ServiceChatBranding = ServiceChatBranding()
    greeting: ServiceChatGreeting = ServiceChatGreeting()
    workspace: str = "전체"
    """RAG 검색 워크스페이스. '전체'면 모든 워크스페이스에서 검색, 특정 ID면 해당 워크스페이스만 검색"""
    system_prompt: ServiceChatSystemPrompt = ServiceChatSystemPrompt()
    faq: ServiceChatFaq = ServiceChatFaq()
    quick_replies: ServiceChatQuickReplies = ServiceChatQuickReplies()
    disclaimer: str = "AI가 생성한 응답이므로 정확하지 않을 수 있습니다 · 중요한 정보는 원본을 확인해 주세요"