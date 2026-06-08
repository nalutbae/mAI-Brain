"""mAI-Brain AI 챗봇 — LLM 클라이언트 모듈

ollama-cloud(1순위) + DeepSeek API(2순위) LLM 호출.
시스템 프롬프트: 조선어 원문 인용, 한국어 답변, 환각 방지.

핵심 설계:
- OpenAI 호환 엔드포인트로 ollama-cloud 호출
- DeepSeek API 폴백 (ollama-cloud 실패 시)
- 이전 대화 컨텍스트를 프롬프트에 포함하여 이어서 대화 가능
"""

from __future__ import annotations

import logging
from typing import Optional

import httpx

from app.config import ChatMode, LLMProviderType, ReasoningStrength, get_settings
from app.models.chat import SearchHit

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# 시스템 프롬프트 (아이디어.md 섹션 5.3 기반)
# --------------------------------------------------------------------------- #

SYSTEM_PROMPT = """\
당신은 업로드된 문서를 분석하고 답변하는 도메인 특화 문서 AI입니다.

규칙:
1. 항상 한국어로 답변하라.
2. 원문을 그대로 인용하라. 원본 문서의 용어를 임의로 변환하지 마라.
3. 출처를 요청받은 경우에만 표기하라: [파일명] [문단번호]
4. 제공된 문서에 없는 내용은 추론하지 마라. 모르면 "해당 문서에서 찾을 수 없습니다"라고 답하라.
5. 필요시 원문 용어와 일반 용어의 대조를 주석으로 제공하라.\
"""

# 모드별 추가 지시사항
MODE_INSTRUCTIONS: dict[ChatMode, str] = {
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


# --------------------------------------------------------------------------- #
# 추론 강도별 추가 프롬프트
# --------------------------------------------------------------------------- #

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


def _get_reasoning_instruction(strength: Optional[ReasoningStrength]) -> str:
    """추론 강도에 따른 프롬프트 조정.

    Args:
        strength: 추론 강도 (None → 전체 모드)

    Returns:
        추가 프롬프트 문자열 (없으면 빈 문자열)
    """
    if strength is None or strength == ReasoningStrength.ALL:
        return ""
    return REASONING_STRENGTH_INSTRUCTIONS.get(strength, "")


# --------------------------------------------------------------------------- #
# 컬럼 모드 근거 강도별 추가 프롬프트
# --------------------------------------------------------------------------- #

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


def _get_column_strength_instruction(strength: Optional[ReasoningStrength]) -> str:
    """컬럼 모드 근거 강도에 따른 프롬프트 조정."""
    if strength is None or strength == ReasoningStrength.ALL:
        return ""
    return COLUMN_STRENGTH_INSTRUCTIONS.get(strength, "")


# --------------------------------------------------------------------------- #
# LLM 클라이언트
# --------------------------------------------------------------------------- #

class LLMClient:
    """LLM API 클라이언트.

    ollama-cloud → DeepSeek API 순서로 폴백.
    둘 다 실패하면 예외 발생.

    OpenAI 호환 엔드포인트를 사용 (ollama-cloud, DeepSeek 모두 지원).
    """

    def __init__(self) -> None:
        settings = get_settings()
        self._provider = settings.llm_provider
        self._deepseek_api_key = settings.deepseek_api_key
        self._deepseek_base_url = settings.deepseek_base_url
        self._deepseek_model = settings.deepseek_model
        # ollama-cloud 설정 (환경변수 또는 기본값)
        self._ollama_base_url = settings.ollama_base_url
        self._timeout = 120.0  # LLM 응답 대기 시간 (초)

    def generate_answer(
        self,
        query: str,
        contexts: list[SearchHit],
        mode: ChatMode = ChatMode.FACT,
        chat_history: Optional[list[dict[str, str]]] = None,
        reasoning_strength: Optional[ReasoningStrength] = None,
    ) -> str:
        """검색 결과를 바탕으로 LLM 답변 생성.

        Args:
            query: 사용자 질문
            contexts: 검색 결과 (SearchHit 리스트)
            mode: 채팅 모드
            chat_history: 이전 대화 기록 [{"role": "user/assistant", "content": "..."}]
            reasoning_strength: 추론 강도 필터 (추론 모드에서만 사용)

        Returns:
            AI 답변 (한국어)
        """
        # 컨텍스트 텍스트 구성
        context_text = self._build_context(contexts)

        # 사용자 프롬프트 구성
        user_message = self._build_user_prompt(query, context_text, mode)

        # 메시지 시퀀스 구성
        messages = self._build_messages(mode, user_message, chat_history, reasoning_strength)

        # LLM 호출 — provider 순서대로 시도
        # 추론 모드는 더 긴 응답이 필요하므로 max_tokens 상향
        max_tokens = 3072 if mode == ChatMode.REASONING else 2048

        if self._provider == LLMProviderType.OLLAMA_CLOUD:
            answer = self._call_ollama_cloud(messages, max_tokens)
            if answer is not None:
                return answer
            # 폴백
            logger.info("ollama-cloud 실패, DeepSeek API로 폴백")
            answer = self._call_deepseek(messages, max_tokens)
            if answer is not None:
                return answer
        else:
            answer = self._call_deepseek(messages, max_tokens)
            if answer is not None:
                return answer
            # 폴백
            logger.info("DeepSeek API 실패, ollama-cloud로 폴백")
            answer = self._call_ollama_cloud(messages, max_tokens)
            if answer is not None:
                return answer

        # 모든 provider 실패
        raise RuntimeError("모든 LLM 제공자 호출 실패 — ollama-cloud와 DeepSeek API 모두 응답하지 않습니다.")

    # ------------------------------------------------------------------- #
    # 프롬프트 구성
    # ------------------------------------------------------------------- #

    def _build_context(self, contexts: list[SearchHit]) -> str:
        """검색 결과를 컨텍스트 텍스트로 변환.

        각 검색 결과를 번호가 매겨진 인용구로 포맷팅.
        """
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
    ) -> list[dict[str, str]]:
        """OpenAI Chat API 메시지 시퀀스 구성.

        시스템 프롬프트 → 이전 대화 기록 → 현재 사용자 메시지.
        """
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
        ]

        # 모드별 추가 지시사항
        mode_instruction = MODE_INSTRUCTIONS.get(mode)
        if mode_instruction:
            # 추론/컬럼 모드 + 강도 지정 시: 강도별 추가 지시사항 덧붙임
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

        # 이전 대화 기록 (이어서 대화)
        if chat_history:
            messages.extend(chat_history)

        # 현재 질문
        messages.append({"role": "user", "content": user_message})

        return messages

    # ------------------------------------------------------------------- #
    # LLM API 호출
    # ------------------------------------------------------------------- #

    def _call_ollama_cloud(
        self, messages: list[dict[str, str]], max_tokens: int = 2048,
    ) -> Optional[str]:
        """ollama-cloud API 호출 (OpenAI 호환 엔드포인트).

        Returns:
            답변 텍스트, 실패 시 None
        """
        settings = get_settings()
        # ollama-cloud의 OpenAI 호환 엔드포인트
        url = f"{self._ollama_base_url}/v1/chat/completions"

        return self._call_openai_compatible(
            url=url,
            api_key="ollama",  # ollama는 API 키 불필요, 더미값
            model=settings.ollama_model,  # 설정에서 모델명 로드
            messages=messages,
            provider_name="ollama-cloud",
            max_tokens=max_tokens,
        )

    def _call_deepseek(
        self, messages: list[dict[str, str]], max_tokens: int = 2048,
    ) -> Optional[str]:
        """DeepSeek API 호출.

        Returns:
            답변 텍스트, 실패 시 None
        """
        if not self._deepseek_api_key:
            logger.warning("DEEPSEEK_API_KEY 미설정 — DeepSeek 호출 스킵")
            return None

        url = f"{self._deepseek_base_url}/chat/completions"

        return self._call_openai_compatible(
            url=url,
            api_key=self._deepseek_api_key,
            model=self._deepseek_model,
            messages=messages,
            provider_name="DeepSeek",
            max_tokens=max_tokens,
        )

    def _call_openai_compatible(
        self,
        url: str,
        api_key: str,
        model: str,
        messages: list[dict[str, str]],
        provider_name: str,
        max_tokens: int = 2048,
    ) -> Optional[str]:
        """OpenAI Chat Completions 호환 API 공통 호출.

        ollama-cloud, DeepSeek 모두 동일한 스펙 사용.
        """
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
                    "temperature": 0.1,  # 낮은 온도로 환각 최소화
                    "max_tokens": max_tokens,
                },
                timeout=self._timeout,
            )
            response.raise_for_status()

            data = response.json()
            answer = data["choices"][0]["message"]["content"]
            logger.info("%s 응답 성공 (%d자)", provider_name, len(answer))
            return answer

        except httpx.HTTPStatusError as exc:
            logger.error(
                "%s API 오류: %d %s",
                provider_name, exc.response.status_code, exc.response.text[:200],
            )
            return None
        except httpx.RequestError as exc:
            logger.error("%s 연결 오류: %s", provider_name, exc)
            return None
        except (KeyError, IndexError) as exc:
            logger.error("%s 응답 파싱 오류: %s", provider_name, exc)
            return None


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