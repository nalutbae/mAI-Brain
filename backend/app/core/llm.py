"""mAI-Brain AI 챗봇 — LLM 클라이언트 모듈

ProviderSettingsStore 기반 다중 프로바이더 지원:
- Ollama, OpenAI, Anthropic, Groq, DeepSeek, Custom
- 활성 프로바이더 → 폴백 프로바이더 순서로 시도
- 시스템 프롬프트: 워크스페이스/모드별 커스터마이제이션 지원
"""

from __future__ import annotations

import logging
from typing import Optional

import httpx

from app.config import ChatMode, ReasoningStrength, get_settings
from app.models.chat import SearchHit
from app.models.provider import (
    LLMProviderConfig,
    LLMProviderType,
    ProviderSettingsStore,
)

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# 시스템 프롬프트 (기본값 — 데이터스토어에 커스텀 프롬프트가 없을 때 사용)
# --------------------------------------------------------------------------- #

DEFAULT_SYSTEM_PROMPT = """\
당신은 업로드된 문서를 분석하고 답변하는 도메인 특화 문서 AI입니다.

규칙:
1. 항상 한국어로 답변하라.
2. 원문을 그대로 인용하라. 원본 문서의 용어를 임의로 변환하지 마라.
3. 출처를 요청받은 경우에만 표기하라: [파일명] [문단번호]
4. 제공된 문서에 없는 내용은 추론하지 마라. 모르면 "해당 문서에서 찾을 수 없습니다"라고 답하라.
5. 필요시 원문 용어와 일반 용어의 대조를 주석으로 제공하라.\
"""

# 모드별 추가 지시사항 (기본값)
DEFAULT_MODE_INSTRUCTIONS: dict[ChatMode, str] = {
    ChatMode.FACT: """\
[팩트 조회 모드]
- 정확한 사실만 답변하라.
- 출처(파일명, 페이지/청크 위치)를 반드시 표기하라.
- 짧고 명확하게 답변하라.
- 문서에 없는 정보는 추측하지 마라.""",

    ChatMode.SUMMARY: """\
[요약 모드]
- 여러 문서의 관련 내용을 종합하여 요약하라.
- 주요 포인트를 번호로 나열하라.
- 각 포인트에 출처를 표기하라.
- 원문의 용어를 유지하라.""",

    ChatMode.COLUMN: """\
[컬럼 작성 모드]
- 다수 문서를 참고하여 종합적인 글을 작성하라.
- 논리적 흐름으로 서술하라.
- 인용구는 원문 그대로 사용하라 (용어 변환 금지).
- 출처를 괄호로 표기하라: (파일명, 페이지).
- 서론-본론-결론 구조를 사용하라.""",

    ChatMode.REASONING: """\
[추론 모드]
당신은 검색된 문서들을 교차 분석하여 인과관계, 패턴, 함의를 도출하는 추론 전문가입니다. 문서에 최대한 근거하되, 문서가 없는 경우에도 가장 가까운 답변을 제출합니다.

규칙:
1. 검색된 문서들을 먼저 요약하라. 각 문서의 핵심 주장을 1-2문장으로 제시하라.
2. 문서 간 연결점을 식별하라:
   - 서로 다른 문서가 같은 주제를 어떻게 다루는가?
   - 시간적 선후관계가 있는가? (원인 → 결과)
   - 한 문서의 주장이 다른 문서의 사례/증거로 뒷받침되는가?
   - 문서 간 모순이나 긴장이 있는가?
3. 추론 단계를 명시적으로 표시하라:
   - '문서 A에 따르면... 문서 B에 의하면...'
   - '이로부터 다음과 같은 추론이 가능하다: ...'
   - '(추론)' 마커를 사용하여 직접 인용과 추론을 구분하라.
4. 추론의 강도를 3단계로 표시하라:
   - [강한 추론]: 문서들이 명시적으로 뒷받침
   - [중간 추론]: 문서들이 간접적으로 시사
   - [약한 추론]: 제한된 근거에 기반, 추가 검증 필요
5. 반드시 각 추론에 사용된 문서를 출처로 명시하라: [파일명, p.페이지]
6. 추론할 수 없는 질문에는 '추론에 필요한 충분한 근거가 검색되지 않았습니다'라고 답하라.
7. 답변 구조: 문서 분석 → 연결점 → 추론 → 결론 순으로 작성하라.
8. 최종 답변은 한국어로, 원문 용어는 그대로 사용하라.""",
}

# 추론 강도별 추가 프롬프트
REASONING_STRENGTH_INSTRUCTIONS: dict[ReasoningStrength, str] = {
    ReasoningStrength.ALL: "",  # 기본 추론 프롬프트 그대로 사용
    ReasoningStrength.STRONG: """\
[추가 지시: 강한 추론만]
- [강한 추론] 항목만 출력하라. [중간 추론], [약한 추론]은 생략하라.
- 문서들이 명시적으로 뒷받침하는 추론에 집중하라.
- 근거가 불충분한 추론은 과감히 건너뛰어라.
- 각 추론에 최소 2개 이상의 문서 출처를 제시하라.""",
    ReasoningStrength.MID: """\
[추가 지시: 중간 추론만]
- [중간 추론] 항목만 출력하라. [강한 추론], [약한 추론]은 생략하라.
- 문서들이 간접적으로 시사하는 패턴과 함의에 집중하라.
- '이는 ~을 시사한다', '~으로 볼 여지가 있다'와 같은 표현을 사용하라.
- 추론의 한계(추가 검증이 필요한 지점)를 반드시 명시하라.""",
    ReasoningStrength.WEAK: """\
[추가 지시: 약한 추론만]
- [약한 추론] 항목만 출력하라. [강한 추론], [중간 추론]은 생략하라.
- 제한된 근거로 가능한 추론을 탐색하라. 가설 제시를 두려워하지 마라.
- '추측컨대...', '추가 연구가 필요하지만...'과 같은 표현을 사용하라.
- 각 추론에 [추가 검증 필요] 태그를 붙여라.
- 근거의 한계를 솔직히 인정하라.
- 근거가 되는 문서가 없더라도 최대한 유사한 답변을 제출하라.""",
}

# 컬럼 모드 근거 강도별 추가 프롬프트
COLUMN_STRENGTH_INSTRUCTIONS: dict[ReasoningStrength, str] = {
    ReasoningStrength.ALL: "",
    ReasoningStrength.STRONG: """\
[추가 지시: 강한 근거만 사용]
- 3개 이상의 서로 다른 문서에서 교차 검증된 정보만 인용하라.
- 단일 출처의 주장은 배제하라.
- 모든 인용구에 정확한 출처를 표기하라: (파일명, 페이지).
- 검증되지 않은 정보는 '확인 불가'로 명시하라.""",
    ReasoningStrength.MID: """\
[추가 지시: 중간 근거만 사용]
- 2개 이상의 문서에서 언급된 정보를 우선 인용하라.
- 단일 문서 인용 시 '~에 따르면'으로 출처를 명확히 하라.
- 교차 검증 가능한 주장과 단일 출처 주장을 구분하여 표시하라.""",
    ReasoningStrength.WEAK: """\
[추가 지시: 약한 근거 포함]
- 1개의 문서만으로도 충분히 인용 가능하다.
- 출처가 단일 문서인 경우 '~에 의하면'으로 명시하라.
- 추측성 내용도 '[추정]' 태그를 붙여 포함하라.
- 근거 부족을 솔직히 인정하고 다양한 관점을 제시하라.
- 근거 문서가 없는 경우에도 최대한 논리적으로 컬럼을 작성하라.""",
}


def _get_reasoning_instruction(strength: Optional[ReasoningStrength]) -> str:
    """추론 강도에 따른 프롬프트 조정."""
    if strength is None or strength == ReasoningStrength.ALL:
        return ""
    return REASONING_STRENGTH_INSTRUCTIONS.get(strength, "")


def _get_column_strength_instruction(strength: Optional[ReasoningStrength]) -> str:
    """컬럼 모드 근거 강도에 따른 프롬프트 조정."""
    if strength is None or strength == ReasoningStrength.ALL:
        return ""
    return COLUMN_STRENGTH_INSTRUCTIONS.get(strength, "")


# --------------------------------------------------------------------------- #
# 프롬프트 해석 — 커스텀 프롬프트 > 기본 프롬프트
# --------------------------------------------------------------------------- #

def get_system_prompt_text(
    mode: ChatMode,
    workspace_id: Optional[str] = None,
) -> str:
    """모드+워크스페이스에 대한 시스템 프롬프트 텍스트 반환.

    우선순위:
    1. 커스텀 프롬프트 (워크스페이스+모드에 지정된 경우)
    2. 기본 프롬프트 (데이터스토어의 is_default)
    3. 하드코딩 DEFAULT_SYSTEM_PROMPT / DEFAULT_MODE_INSTRUCTIONS
    """
    try:
        from app.core.system_prompt import get_system_prompt_store, render_prompt
        store = get_system_prompt_store()
        effective = store.get_effective_prompt(mode=mode, workspace_id=workspace_id)

        if effective is not None:
            context = store.build_context(workspace_id=workspace_id)
            rendered, _, _ = render_prompt(effective.prompt_text, context)
            return rendered
    except Exception as exc:
        logger.warning("커스텀 프롬프트 로드 실패, 하드코딩 사용: %s", exc)

    # 폴백: 하드코딩 프롬프트
    return DEFAULT_MODE_INSTRUCTIONS.get(mode, DEFAULT_SYSTEM_PROMPT)


def get_base_system_prompt(workspace_id: Optional[str] = None) -> str:
    """베이스 시스템 프롬프트 (모드 지시사항 앞에 추가)."""
    return DEFAULT_SYSTEM_PROMPT


# --------------------------------------------------------------------------- #
# LLM 클라이언트 — ProviderSettingsStore 기반 다중 프로바이더
# --------------------------------------------------------------------------- #

class LLMClient:
    """LLM API 클라이언트.

    ProviderSettingsStore에서 활성 프로바이더 설정을 읽어 동적으로 호출.
    활성 프로바이더 실패 시 폴백 프로바이더로 자동 전환.

    지원 프로바이더:
    - Ollama (OpenAI 호환)
    - OpenAI
    - Anthropic (네이티브 API)
    - Groq (OpenAI 호환)
    - DeepSeek (OpenAI 호환)
    - Custom (OpenAI 호환)
    """

    def __init__(self) -> None:
        self._timeout = 120.0  # LLM 응답 대기 시간 (초)

    @property
    def _store(self) -> ProviderSettingsStore:
        return ProviderSettingsStore.get()

    def _get_provider_chain(self) -> list[LLMProviderConfig]:
        """호출할 프로바이더 체인 반환 (활성 → 폴백)."""
        active = self._store.get_active_llm_provider()
        chain = [active]

        fallback = self._store.get_fallback_llm_provider(active)
        if fallback and fallback.id != active.id:
            chain.append(fallback)

        return chain

    def generate_answer(
        self,
        query: str,
        contexts: list[SearchHit],
        mode: ChatMode = ChatMode.FACT,
        chat_history: Optional[list[dict[str, str]]] = None,
        reasoning_strength: Optional[ReasoningStrength] = None,
        workspace_id: Optional[str] = None,
    ) -> str:
        """검색 결과를 바탕으로 LLM 답변 생성.

        Args:
            query: 사용자 질문
            contexts: 검색 결과 (SearchHit 리스트)
            mode: 채팅 모드
            chat_history: 이전 대화 기록 [{"role": "user/assistant", "content": "..."}]
            reasoning_strength: 추론 강도 필터 (추론 모드에서만 사용)
            workspace_id: 워크스페이스 ID (커스텀 프롬프트 조회용)

        Returns:
            AI 답변 (한국어)
        """
        # 컨텍스트 텍스트 구성
        context_text = self._build_context(contexts)

        # 사용자 프롬프트 구성
        user_message = self._build_user_prompt(query, context_text, mode)

        # 메시지 시퀀스 구성
        messages = self._build_messages(
            mode, user_message, chat_history, reasoning_strength,
            workspace_id=workspace_id,
        )

        # 추론 모드는 더 긴 응답이 필요하므로 max_tokens 상향
        max_tokens = 3072 if mode == ChatMode.REASONING else 2048

        # 프로바이더 체인 순서대로 시도
        chain = self._get_provider_chain()
        last_error = None

        for provider_config in chain:
            try:
                answer = self._call_provider(provider_config, messages, max_tokens)
                if answer is not None:
                    logger.info(
                        "LLM 응답 성공: provider=%s, model=%s (%d자)",
                        provider_config.provider.value,
                        provider_config.get_effective_model(),
                        len(answer),
                    )
                    return answer
            except Exception as exc:
                last_error = exc
                logger.warning(
                    "LLM 호출 실패 (provider=%s): %s — 다음 프로바이더로 폴백",
                    provider_config.provider.value, exc,
                )

        # 모든 provider 실패
        err_msg = "모든 LLM 제공자 호출 실패"
        if last_error:
            err_msg += f": {last_error}"
        raise RuntimeError(err_msg)

    # ------------------------------------------------------------------- #
    # 프로바이더 호출 라우팅
    # ------------------------------------------------------------------- #

    def _call_provider(
        self,
        provider: LLMProviderConfig,
        messages: list[dict[str, str]],
        max_tokens: int = 2048,
    ) -> Optional[str]:
        """프로바이더 타입에 따라 적절한 API 호출."""
        ptype = provider.provider

        if ptype == LLMProviderType.ANTHROPIC:
            return self._call_anthropic(provider, messages, max_tokens)
        elif ptype == LLMProviderType.OLLAMA:
            base_url = provider.get_effective_base_url().rstrip("/")
            # base_url이 /api/chat으로 끝나면 Ollama 네이티브 API 사용
            if base_url.endswith("/api/chat"):
                return self._call_ollama_native(provider, messages, max_tokens)
            else:
                return self._call_openai_compatible(provider, messages, max_tokens)
        else:
            # OpenAI 호환: openai, groq, deepseek, custom
            return self._call_openai_compatible(provider, messages, max_tokens)

    # ------------------------------------------------------------------- #
    # Ollama 네이티브 API (/api/chat 엔드포인트)
    # ------------------------------------------------------------------- #

    def _call_ollama_native(
        self,
        provider: LLMProviderConfig,
        messages: list[dict[str, str]],
        max_tokens: int = 2048,
    ) -> Optional[str]:
        """Ollama 네이티브 /api/chat 엔드포인트 호출.

        ollama.com 클라우드 등 Ollama 네이티브 프로토콜을 사용하는 서비스용.
        인증: Authorization: Bearer {api_key}  (OLLAMA_API_KEY)
        요청: POST {base_url}  (base_url이 이미 /api/chat 전체 경로)
        응답: {"message": {"role": "assistant", "content": "..."}}
        """
        import os

        base_url = provider.get_effective_base_url().rstrip("/")
        model = provider.get_effective_model()

        # API 키: JSON 설정 → OLLAMA_API_KEY 환경변수 → 더미값
        api_key = provider.api_key
        if not api_key:
            api_key = os.environ.get("OLLAMA_API_KEY", "")
        if not api_key:
            api_key = "ollama"  # 로컬 Ollama는 더미값

        temperature = getattr(provider, 'temperature', 0.1)

        headers = {"Content-Type": "application/json"}
        if api_key and api_key != "ollama":
            headers["Authorization"] = f"Bearer {api_key}"

        try:
            response = httpx.post(
                base_url,  # 이미 /api/chat 전체 URL
                headers=headers,
                json={
                    "model": model,
                    "messages": messages,
                    "stream": False,
                    "options": {
                        "temperature": temperature,
                        "num_predict": max_tokens,
                    },
                },
                timeout=self._timeout,
            )
            response.raise_for_status()

            data = response.json()
            # Ollama 네이티브 응답: {"message": {"role": "assistant", "content": "..."}}
            answer = data.get("message", {}).get("content", "")
            if not answer:
                # /api/generate 형식 응답 폴백
                answer = data.get("response", "")
            return answer if answer else None

        except httpx.HTTPStatusError as exc:
            logger.warning(
                "Ollama 네이티브 API 오류: %d %s (url=%s)",
                exc.response.status_code, exc.response.text[:200], base_url,
            )
            return None
        except Exception as exc:
            logger.warning("Ollama 네이티브 연결 오류: %s", exc)
            return None

    # ------------------------------------------------------------------- #
    # OpenAI 호환 API (ollama, openai, groq, deepseek, custom)
    # ------------------------------------------------------------------- #

    def _call_openai_compatible(
        self,
        provider: LLMProviderConfig,
        messages: list[dict[str, str]],
        max_tokens: int = 2048,
    ) -> Optional[str]:
        """OpenAI Chat Completions 호환 API 공통 호출."""
        import os

        base_url = provider.get_effective_base_url()
        model = provider.get_effective_model()

        # API 키: JSON 설정 → 환경변수 → 프로바이더별 기본값 순서로 해석
        api_key = provider.api_key
        if not api_key:
            # 프로바이더별 환경변수에서 폴백
            env_var_map = {
                LLMProviderType.OPENAI: "OPENAI_API_KEY",
                LLMProviderType.ANTHROPIC: "ANTHROPIC_API_KEY",
                LLMProviderType.GROQ: "GROQ_API_KEY",
                LLMProviderType.DEEPSEEK: "DEEPSEEK_API_KEY",
            }
            env_var = env_var_map.get(provider.provider, "")
            if env_var:
                api_key = os.environ.get(env_var, "")
        if not api_key and provider.provider == LLMProviderType.OLLAMA:
            api_key = "ollama"  # Ollama는 더미값

        # 호출 URL 구성 — base_url에 이미 /v1이 포함된 경우 중복 방지
        burl = base_url.rstrip("/")
        if burl.endswith("/v1"):
            url = f"{burl}/chat/completions"
        else:
            url = f"{burl}/v1/chat/completions"

        temperature = getattr(provider, 'temperature', 0.1)

        if not api_key:
            logger.warning(
                "API 키 없음 — 프로바이더 %s 호출 스킵", provider.provider.value,
            )
            return None

        try:
            response = httpx.post(
                url,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": model,
                    "messages": messages,
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                },
                timeout=self._timeout,
            )
            response.raise_for_status()

            data = response.json()
            answer = data["choices"][0]["message"]["content"]
            return answer

        except httpx.HTTPStatusError as exc:
            logger.error(
                "%s API 오류: %d %s",
                provider.provider.value,
                exc.response.status_code,
                exc.response.text[:200],
            )
            return None
        except httpx.RequestError as exc:
            logger.error("%s 연결 오류: %s", provider.provider.value, exc)
            return None
        except (KeyError, IndexError) as exc:
            logger.error("%s 응답 파싱 오류: %s", provider.provider.value, exc)
            return None

    # ------------------------------------------------------------------- #
    # Anthropic 네이티브 API
    # ------------------------------------------------------------------- #

    def _call_anthropic(
        self,
        provider: LLMProviderConfig,
        messages: list[dict[str, str]],
        max_tokens: int = 2048,
    ) -> Optional[str]:
        """Anthropic Messages API 호출."""
        base_url = provider.get_effective_base_url()
        model = provider.get_effective_model()
        api_key = provider.api_key

        if not api_key:
            logger.warning("Anthropic API 키 없음 — 호출 스킵")
            return None

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
        }
        if system_prompts:
            body["system"] = "\n\n".join(system_prompts)

        try:
            response = httpx.post(
                url,
                headers={
                    "x-api-key": api_key,
                    "anthropic-version": "2023-06-01",
                    "Content-Type": "application/json",
                },
                json=body,
                timeout=self._timeout,
            )
            response.raise_for_status()

            data = response.json()
            # Anthropic 응답: content[0].text
            for block in data.get("content", []):
                if block.get("type") == "text":
                    return block["text"]
            return None

        except httpx.HTTPStatusError as exc:
            logger.error(
                "Anthropic API 오류: %d %s",
                exc.response.status_code,
                exc.response.text[:200],
            )
            return None
        except httpx.RequestError as exc:
            logger.error("Anthropic 연결 오류: %s", exc)
            return None
        except (KeyError, IndexError) as exc:
            logger.error("Anthropic 응답 파싱 오류: %s", exc)
            return None

    # ------------------------------------------------------------------- #
    # 프롬프트 구성
    # ------------------------------------------------------------------- #

    def _build_context(self, contexts: list[SearchHit]) -> str:
        """검색 결과를 컨텍스트 텍스트로 변환."""
        if not contexts:
            return "관련 문서를 찾을 수 없습니다."

        parts = []
        for i, hit in enumerate(contexts, 1):
            source_info = f"[{hit.source}"
            if hit.page is not None:
                source_info += f", p.{hit.page}"
            source_info += "]"
            parts.append(f"--- 인용 {i} {source_info} ---\n{hit.text}\n")

        return "\n".join(parts)

    def _build_user_prompt(
        self, query: str, context_text: str, mode: ChatMode,
    ) -> str:
        """사용자 메시지 구성."""
        return f"""다음 문서를 참고하여 질문에 답변하라.

[참고 문서]
{context_text}

[질문]
{query}"""

    def _build_messages(
        self,
        mode: ChatMode,
        user_message: str,
        chat_history: Optional[list[dict[str, str]]] = None,
        reasoning_strength: Optional[ReasoningStrength] = None,
        workspace_id: Optional[str] = None,
    ) -> list[dict[str, str]]:
        """OpenAI Chat API 메시지 시퀀스 구성."""
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


# --------------------------------------------------------------------------- #
# 싱글톤
# --------------------------------------------------------------------------- #

_llm_client: Optional[LLMClient] = None


def get_llm_client() -> LLMClient:
    """LLMClient 싱글톤 인스턴스 반환."""
    global _llm_client
    if _llm_client is None:
        _llm_client = LLMClient()
    return _llm_client
