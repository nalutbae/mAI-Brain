"""mAI-Brain — 음성 인터페이스 모델

STT(TTS → 텍스트) 및 TTS(텍스트 → 음성) 요청/응답 모델.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


# ── STT ────────────────────────────────────────────────────────────────────

class STTResponse(BaseModel):
    """음성 → 텍스트 변환 결과"""

    text: str = Field(..., description="변환된 텍스트")
    language: str = Field(default="ko", description="인식된 언어 코드")
    duration_seconds: float | None = Field(default=None, description="오디오 길이 (초)")
    provider: str = Field(default="whisper", description="사용된 STT 제공자")


# ── TTS ────────────────────────────────────────────────────────────────────

class TTSRequest(BaseModel):
    """텍스트 → 음성 변환 요청"""

    text: str = Field(..., min_length=1, max_length=4096, description="읽어줄 텍스트")
    voice_id: str | None = Field(default=None, description="ElevenLabs 음성 ID (기본값 설정됨)")
    language: str = Field(default="ko", description="언어 코드")
    speed: float = Field(default=1.0, ge=0.5, le=2.0, description="재생 속도")
