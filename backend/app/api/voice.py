"""mAI-Brain — 음성 인터페이스 API

브라우저 Web Speech API가 기본이지만, 더 높은 품질이 필요할 때
사용할 수 있는 서버 측 STT/TTS 엔드포인트를 제공합니다.

엔드포인트:
- POST /api/voice/stt:  오디오 파일 → 텍스트 (OpenAI Whisper)
- POST /api/voice/tts:  텍스트 → 오디오 파일 (ElevenLabs)
- GET  /api/voice:      음성 API 상태 확인
"""

from __future__ import annotations

import logging
from io import BytesIO

from fastapi import APIRouter, File, HTTPException, UploadFile, Query
from fastapi.responses import StreamingResponse

from app.config import get_settings
from app.models.voice import STTResponse, TTSRequest

logger = logging.getLogger(__name__)

router = APIRouter()

# ── 상태 확인 ────────────────────────────────────────────────────────────


@router.get("")
async def voice_status():
    """음성 API 상태 확인 — 설정된 제공자 반환"""
    settings = get_settings()
    return {
        "stt_provider": "whisper" if settings.voice_whisper_api_key else None,
        "tts_provider": "elevenlabs" if settings.voice_elevenlabs_api_key else None,
        "message": (
            "백엔드 음성 API가 설정되지 않았습니다. "
            "VOICE_WHISPER_API_KEY / VOICE_ELEVENLABS_API_KEY 환경변수를 설정하세요."
        ),
    }


# ── STT: Whisper API ─────────────────────────────────────────────────────


@router.post("/stt", response_model=STTResponse)
async def speech_to_text(
    file: UploadFile = File(..., description="오디오 파일 (mp3, wav, webm, m4a)"),
    language: str = Query(default="ko", description="언어 코드"),
):
    """오디오 파일을 텍스트로 변환 (OpenAI Whisper API).

    브라우저 Web Speech API를 사용할 수 없는 환경이나
    더 높은 정확도가 필요할 때 사용합니다.
    """
    settings = get_settings()
    api_key = settings.voice_whisper_api_key

    if not api_key:
        raise HTTPException(
            status_code=501,
            detail="Whisper API가 설정되지 않았습니다. VOICE_WHISPER_API_KEY를 설정하세요.",
        )

    # 파일 확장자 검증
    filename = file.filename or "audio.mp3"
    allowed_extensions = {".mp3", ".wav", ".webm", ".m4a", ".ogg", ".flac", ".mp4", ".mpeg"}
    ext = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext not in allowed_extensions:
        raise HTTPException(
            status_code=400,
            detail=f"지원하지 않는 파일 형식입니다: {ext}. 지원: {', '.join(sorted(allowed_extensions))}",
        )

    # OpenAI Whisper API 호출
    import httpx

    try:
        audio_content = await file.read()
        audio_file = BytesIO(audio_content)
        audio_file.name = filename

        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.post(
                "https://api.openai.com/v1/audio/transcriptions",
                headers={"Authorization": f"Bearer {api_key}"},
                files={"file": (filename, audio_file, file.content_type or "audio/mpeg")},
                data={
                    "model": "whisper-1",
                    "language": language,
                    "response_format": "json",
                },
            )

        if response.status_code != 200:
            logger.error("Whisper API 오류: %s %s", response.status_code, response.text)
            raise HTTPException(
                status_code=502,
                detail=f"Whisper API 오류: {response.status_code}",
            )

        result = response.json()
        return STTResponse(
            text=result.get("text", ""),
            language=language,
            duration_seconds=result.get("duration"),
            provider="whisper",
        )

    except httpx.RequestError as exc:
        logger.error("Whisper API 네트워크 오류: %s", exc)
        raise HTTPException(status_code=502, detail="Whisper API 연결 실패") from exc


# ── TTS: ElevenLabs API ──────────────────────────────────────────────────


@router.post("/tts")
async def text_to_speech(request: TTSRequest):
    """텍스트를 음성 오디오로 변환 (ElevenLabs API).

    MP3 오디오 스트림을 반환합니다.
    브라우저 SpeechSynthesis를 사용할 수 없는 환경이나
    더 자연스러운 음성이 필요할 때 사용합니다.
    """
    settings = get_settings()
    api_key = settings.voice_elevenlabs_api_key

    if not api_key:
        raise HTTPException(
            status_code=501,
            detail="ElevenLabs API가 설정되지 않았습니다. VOICE_ELEVENLABS_API_KEY를 설정하세요.",
        )

    # 기본 음성 ID (한국어 지원 ElevenLabs 음성)
    voice_id = request.voice_id or settings.voice_elevenlabs_voice_id or "pNInz6obpgDQGcFmaJgB"  # Adam

    import httpx

    try:
        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.post(
                f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}",
                headers={
                    "xi-api-key": api_key,
                    "Content-Type": "application/json",
                    "Accept": "audio/mpeg",
                },
                json={
                    "text": request.text,
                    "model_id": "eleven_multilingual_v2",
                    "voice_settings": {
                        "stability": 0.5,
                        "similarity_boost": 0.75,
                        "speed": request.speed,
                    },
                },
            )

        if response.status_code != 200:
            logger.error("ElevenLabs API 오류: %s %s", response.status_code, response.text)
            raise HTTPException(
                status_code=502,
                detail=f"ElevenLabs API 오류: {response.status_code}",
            )

        return StreamingResponse(
            BytesIO(response.content),
            media_type="audio/mpeg",
            headers={"Content-Disposition": "inline; filename=speech.mp3"},
        )

    except httpx.RequestError as exc:
        logger.error("ElevenLabs API 네트워크 오류: %s", exc)
        raise HTTPException(status_code=502, detail="ElevenLabs API 연결 실패") from exc
