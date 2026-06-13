"""mAI-Brain AI 챗봇 — LLM 스트리밍 클라이언트

LLMClient.generate_answer()의 스트리밍 버전.
각 프로바이더(Ollama, OpenAI호환, Anthropic)에 대해
SSE(Server-Sent Events) 형식으로 토큰을 점진적으로 전송한다.

설계:
- 기존 LLMClient의 프로바이더 체인 로직을 재사용
- httpx 대신 asyncio + httpx.AsyncClient 사용
- stream=True로 API 호출 → 라인 단위 읽기 → yield
- 폴백: 스트리밍 실패 시 동기 호출로 자동 전환
"""

from __future__ import annotations

import json
import logging
from typing import AsyncGenerator, Optional

import httpx

from app.config import ChatMode, ReasoningStrength
from app.models.chat import SearchHit
from app.models.provider import (
    LLMProviderConfig,
    LLMProviderType,
    ProviderSettingsStore,
)
from app.core.llm import (
    get_base_system_prompt,
    get_system_prompt_text,
    _get_reasoning_instruction,
    _get_column_strength_instruction,
)

logger = logging.getLogger(__name__)


class LLMStreamClient:
    """LLM 스트리밍 클라이언트.

    generate_answer_stream()은 AsyncGenerator[str, None]을 반환하며,
    각 yield는 완성된 텍스트 조각(delta)이다.
    """

    def __init__(self, timeout: float = 120.0) -> None:
        self._timeout = timeout

    @property
    def _store(self) -> ProviderSettingsStore:
        return ProviderSettingsStore.get()

    def _get_provider_chain(self) -> list[LLMProviderConfig]:
        """호출할 프로바이더 체인 (활성 → 폴백)."""
        active = self._store.get_active_llm_provider()
        chain = [active]
        fallback = self._store.get_fallback_llm_provider(active)
        if fallback and fallback.id != active.id:
            chain.append(fallback)
        return chain

    def _build_messages(
        self,
        mode: ChatMode,
        user_message: str,
        chat_history: Optional[list[dict[str, str]]] = None,
        reasoning_strength: Optional[ReasoningStrength] = None,
        workspace_id: Optional[str] = None,
    ) -> list[dict[str, str]]:
        """기존 LLMClient와 동일한 메시지 구성 로직."""
        messages = [
            {"role": "system", "content": get_base_system_prompt(workspace_id)},
        ]

        mode_instruction = get_system_prompt_text(mode=mode, workspace_id=workspace_id)
        if mode_instruction:
            if reasoning_strength:
                if mode == ChatMode.REASONING:
                    si = _get_reasoning_instruction(reasoning_strength)
                elif mode == ChatMode.COLUMN:
                    si = _get_column_strength_instruction(reasoning_strength)
                else:
                    si = ""
                if si:
                    mode_instruction = mode_instruction + "\n\n" + si
            messages.append({"role": "system", "content": mode_instruction})

        if chat_history:
            messages.extend(chat_history)

        messages.append({"role": "user", "content": user_message})
        return messages

    # ------------------------------------------------------------------- #
    # 공개 스트리밍 메서드
    # ------------------------------------------------------------------- #

    async def generate_answer_stream(
        self,
        query: str,
        contexts: list[SearchHit],
        mode: ChatMode = ChatMode.FACT,
        chat_history: Optional[list[dict[str, str]]] = None,
        reasoning_strength: Optional[ReasoningStrength] = None,
        workspace_id: Optional[str] = None,
    ) -> AsyncGenerator[str, None]:
        """검색 결과를 바탕으로 LLM 답변을 스트리밍으로 생성.

        각 yield는 완성된 텍스트 델타이다.
        폴백 프로바이더까지 모두 실패하면 RuntimeError를 발생시킨다.
        """
        from app.core.llm import LLMClient

        # 컨텍스트 텍스트 구성 (기존 LLMClient 재사용)
        llm = LLMClient()
        context_text = llm._build_context(contexts)
        user_message = llm._build_user_prompt(query, context_text, mode)

        messages = self._build_messages(
            mode, user_message, chat_history, reasoning_strength,
            workspace_id=workspace_id,
        )

        max_tokens = 3072 if mode == ChatMode.REASONING else 2048

        chain = self._get_provider_chain()
        last_error: Optional[Exception] = None

        for provider_config in chain:
            try:
                async for chunk in self._stream_provider(provider_config, messages, max_tokens):
                    yield chunk
                return  # 성공 → 종료
            except Exception as exc:
                last_error = exc
                logger.warning(
                    "LLM 스트리밍 실패 (provider=%s): %s — 다음 프로바이더로 폴백",
                    provider_config.provider.value, exc,
                )
                continue

        # 모든 provider 실패
        err_msg = "모든 LLM 제공자 스트리밍 호출 실패"
        if last_error:
            err_msg += f": {last_error}"
        raise RuntimeError(err_msg)

    # ------------------------------------------------------------------- #
    # 프로바이더별 스트리밍 라우팅
    # ------------------------------------------------------------------- #

    async def _stream_provider(
        self,
        provider: LLMProviderConfig,
        messages: list[dict[str, str]],
        max_tokens: int = 2048,
    ) -> AsyncGenerator[str, None]:
        """프로바이더 타입에 따라 적절한 스트리밍 API 호출."""
        ptype = provider.provider

        if ptype == LLMProviderType.ANTHROPIC:
            async for chunk in self._stream_anthropic(provider, messages, max_tokens):
                yield chunk
        elif ptype == LLMProviderType.OLLAMA:
            base_url = provider.get_effective_base_url().rstrip("/")
            if base_url.endswith("/api/chat"):
                async for chunk in self._stream_ollama_native(provider, messages, max_tokens):
                    yield chunk
            else:
                async for chunk in self._stream_openai_compatible(provider, messages, max_tokens):
                    yield chunk
        else:
            # OpenAI 호환: openai, groq, deepseek, custom
            async for chunk in self._stream_openai_compatible(provider, messages, max_tokens):
                yield chunk

    # ------------------------------------------------------------------- #
    # OpenAI 호환 스트리밍 (ollama, openai, groq, deepseek, custom)
    # ------------------------------------------------------------------- #

    async def _stream_openai_compatible(
        self,
        provider: LLMProviderConfig,
        messages: list[dict[str, str]],
        max_tokens: int = 2048,
    ) -> AsyncGenerator[str, None]:
        """OpenAI Chat Completions 호환 스트리밍 API."""
        base_url = provider.get_effective_base_url()
        model = provider.get_effective_model()
        api_key = provider.get_effective_api_key()

        if not api_key and provider.provider != LLMProviderType.OLLAMA:
            logger.warning("API 키 없음 — 프로바이더 %s 스트리밍 스킵", provider.provider.value)
            return

        burl = base_url.rstrip("/")
        if burl.endswith("/v1"):
            url = f"{burl}/chat/completions"
        else:
            url = f"{burl}/v1/chat/completions"

        temperature = getattr(provider, 'temperature', 0.1)

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        # Ollama는 Bearer 토큰이 필요 없을 수 있음
        if not api_key or api_key == "ollama":
            headers.pop("Authorization", None)

        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": True,
        }

        async with httpx.AsyncClient(timeout=httpx.Timeout(self._timeout, read=180.0)) as client:
            async with client.stream("POST", url, headers=headers, json=payload) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    data_str = line[6:]  # "data: " 제거
                    if data_str.strip() == "[DONE]":
                        return
                    try:
                        chunk_data = json.loads(data_str)
                        delta = chunk_data.get("choices", [{}])[0].get("delta", {})
                        content = delta.get("content", "")
                        if content:
                            yield content
                    except json.JSONDecodeError:
                        continue

    # ------------------------------------------------------------------- #
    # Ollama 네이티브 스트리밍 (/api/chat)
    # ------------------------------------------------------------------- #

    async def _stream_ollama_native(
        self,
        provider: LLMProviderConfig,
        messages: list[dict[str, str]],
        max_tokens: int = 2048,
    ) -> AsyncGenerator[str, None]:
        """Ollama 네이티브 /api/chat 스트리밍.

        Ollama는 stream=True 시 각 응답이 별도 JSON 라인으로 옴:
        {"message":{"role":"assistant","content":"..."},"done":false}
        ...
        {"message":{"role":"assistant","content":""},"done":true}
        """
        base_url = provider.get_effective_base_url().rstrip("/")
        model = provider.get_effective_model()
        api_key = provider.get_effective_api_key()
        if not api_key:
            api_key = "ollama"

        temperature = getattr(provider, 'temperature', 0.1)

        headers = {"Content-Type": "application/json"}
        if api_key and api_key != "ollama":
            headers["Authorization"] = f"Bearer {api_key}"

        payload = {
            "model": model,
            "messages": messages,
            "stream": True,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
            },
        }

        async with httpx.AsyncClient(timeout=httpx.Timeout(self._timeout, read=180.0)) as client:
            async with client.stream("POST", base_url, headers=headers, json=payload) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        chunk_data = json.loads(line)
                        # Ollama 네이티브: {"message": {"content": "..."}}
                        content = chunk_data.get("message", {}).get("content", "")
                        if content:
                            yield content
                    except json.JSONDecodeError:
                        continue

    # ------------------------------------------------------------------- #
    # Anthropic 스트리밍
    # ------------------------------------------------------------------- #

    async def _stream_anthropic(
        self,
        provider: LLMProviderConfig,
        messages: list[dict[str, str]],
        max_tokens: int = 2048,
    ) -> AsyncGenerator[str, None]:
        """Anthropic Messages API 스트리밍.

        Anthropic은 SSE 형식으로 이벤트를 전송:
        event: content_block_delta
        data: {"type":"content_block_delta","delta":{"type":"text_delta","text":"..."}}
        """
        base_url = provider.get_effective_base_url()
        model = provider.get_effective_model()
        api_key = provider.get_effective_api_key()

        if not api_key:
            logger.warning("Anthropic API 키 없음 — 스트리밍 스킵")
            return

        # Anthropic은 system 프롬프트를 별도 필드로 분리
        system_prompts = []
        chat_messages = []
        for msg in messages:
            if msg["role"] == "system":
                system_prompts.append(msg["content"])
            else:
                chat_messages.append(msg)

        url = f"{base_url.rstrip('/')}/v1/messages"
        body = {
            "model": model,
            "max_tokens": max_tokens,
            "messages": chat_messages,
            "stream": True,
        }
        if system_prompts:
            body["system"] = "\n\n".join(system_prompts)

        headers = {
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        }

        async with httpx.AsyncClient(timeout=httpx.Timeout(self._timeout, read=180.0)) as client:
            async with client.stream("POST", url, headers=headers, json=body) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    data_str = line[6:]
                    try:
                        event_data = json.loads(data_str)
                        event_type = event_data.get("type", "")
                        if event_type == "content_block_delta":
                            delta = event_data.get("delta", {})
                            text = delta.get("text", "")
                            if text:
                                yield text
                        elif event_type == "message_stop":
                            return
                    except json.JSONDecodeError:
                        continue


# --------------------------------------------------------------------------- #
# 싱글톤
# --------------------------------------------------------------------------- #

_llm_stream_client: Optional[LLMStreamClient] = None


def get_llm_stream_client() -> LLMStreamClient:
    """LLMStreamClient 싱글톤 인스턴스 반환."""
    global _llm_stream_client
    if _llm_stream_client is None:
        _llm_stream_client = LLMStreamClient()
    return _llm_stream_client