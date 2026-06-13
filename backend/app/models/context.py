"""mAI-Brain AI 챗봇 — 컨텍스트 관련 Pydantic 모델

문서 고정(Pin), 대화 요약(Context Summary) 요청/응답 모델을 정의합니다.
"""

from typing import Optional

from pydantic import BaseModel, Field


# --------------------------------------------------------------------------- #
# 문서 고정 (Pin Document)
# --------------------------------------------------------------------------- #

class PinDocumentRequest(BaseModel):
    """문서 고정 요청"""
    session_id: str = Field(..., description="세션 ID")
    document_id: str = Field(..., description="고정할 문서 ID")


class PinnedDocument(BaseModel):
    """고정된 문서 정보"""
    session_id: str = Field(..., description="세션 ID")
    document_id: str = Field(..., description="문서 ID")
    pinned_at: str = Field(..., description="고정 시각 (ISO 8601)")
    title: Optional[str] = Field(default=None, description="문서 제목 (filename)")


class UnpinDocumentRequest(BaseModel):
    """문서 고정 해제 요청"""
    session_id: str = Field(..., description="세션 ID")
    document_id: str = Field(..., description="고정 해제할 문서 ID")


# --------------------------------------------------------------------------- #
# 대화 요약 (Context Summary)
# --------------------------------------------------------------------------- #

class ContextSummary(BaseModel):
    """대화 요약 정보"""
    session_id: str = Field(..., description="세션 ID")
    summary_text: str = Field(..., description="요약 텍스트")
    message_count: int = Field(..., description="요약에 포함된 메시지 수")
    created_at: str = Field(..., description="요약 생성 시각 (ISO 8601)")


class SummarizeResponse(BaseModel):
    """요약 생성 응답"""
    session_id: str = Field(..., description="세션 ID")
    summary: str = Field(..., description="생성된 요약 텍스트")
    message_count: int = Field(..., description="요약에 포함된 메시지 수")