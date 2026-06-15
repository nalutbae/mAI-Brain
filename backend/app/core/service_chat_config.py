"""mAI-Brain — 서비스 챗봇 설정 스토어

JSON 파일 기반 영속 저장소. 기존 SystemPromptStore 패턴과 동일.
운영자가 JSON 파일을 직접 편집하거나 API를 통해 수정 가능.
"""

import json
import re
from pathlib import Path
from typing import Optional

from app.models.service_chat import ServiceChatConfig
from app.models.workspace import DATA_DIR

# ── 데이터 저장 경로 ──────────────────────────────────────────────────────

SERVICE_CHAT_CONFIG_DIR = DATA_DIR.parent
SERVICE_CHAT_CONFIG_PATH = SERVICE_CHAT_CONFIG_DIR / "service_chat_config.json"

# ── 변수 치환 ─────────────────────────────────────────────────────────────

_VARIABLE_PATTERN = re.compile(r"\{\{(\w+)\}\}")


def _render_template(text: str, context: dict[str, str]) -> str:
    """{{변수}} 패턴을 치환하여 렌더링."""
    def replacer(match: re.Match) -> str:
        var_name = match.group(1)
        return context.get(var_name, match.group(0))
    return _VARIABLE_PATTERN.sub(replacer, text)


# ── 스토어 ────────────────────────────────────────────────────────────────

class ServiceChatConfigStore:
    """JSON 파일 기반 서비스 챗봇 설정 영속 저장소"""

    def __init__(self, config_path: Path = SERVICE_CHAT_CONFIG_PATH):
        self.config_path = config_path
        self._config: ServiceChatConfig = ServiceChatConfig()
        self._load()

    def _load(self):
        """디스크에서 설정 로드. 파일이 없으면 기본값 생성."""
        if self.config_path.exists():
            try:
                raw = json.loads(self.config_path.read_text(encoding="utf-8"))
                self._config = ServiceChatConfig(**raw)
            except Exception as e:
                print(f"[ServiceChatConfig] 설정 로드 실패, 기본값 사용: {e}")
                self._config = ServiceChatConfig()
        else:
            self._config = ServiceChatConfig()
            self._save()

    def _save(self):
        """설정을 디스크에 저장."""
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        raw = self._config.model_dump(exclude_none=True)
        self.config_path.write_text(
            json.dumps(raw, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def get_config(self) -> ServiceChatConfig:
        """현재 설정 반환 (매번 디스크에서 리로드)."""
        self._load()
        return self._config

    def update_config(self, updates: dict) -> ServiceChatConfig:
        """설정 업데이트. updates는 ServiceChatConfig의 중첩 dict."""
        current = self._config.model_dump()
        _deep_merge(current, updates)
        self._config = ServiceChatConfig(**current)
        self._save()
        return self._config

    def reload(self) -> ServiceChatConfig:
        """강제 리로드 (운영자가 파일을 직접 편집한 후 호출)."""
        self._load()
        return self._config

    # ── 프롬프트 빌더 ──────────────────────────────────────────────────

    def build_system_prompt(self, bot_name: Optional[str] = None) -> str:
        """서비스 챗봇 시스템 프롬프트 빌드. {{bot_name}} 변수 치환."""
        config = self._config
        context = {"bot_name": bot_name or config.branding.bot_name}
        return _render_template(config.system_prompt.base, context)

    def build_mode_instruction(self, mode: str) -> str:
        """모드별 추가 지시문 빌드."""
        config = self._config
        instructions_map = {
            "fact": config.system_prompt.mode_instructions.fact,
            "summary": config.system_prompt.mode_instructions.summary,
            "column": config.system_prompt.mode_instructions.column,
            "reasoning": config.system_prompt.mode_instructions.reasoning,
            "creative": config.system_prompt.mode_instructions.creative,
        }
        return instructions_map.get(mode, "")

    def build_user_prompt(self, context_text: str, query: str) -> str:
        """사용자 프롬프트 빌드. {context}와 {query} 치환."""
        template = self._config.system_prompt.user_prompt_template
        return template.replace("{context}", context_text).replace("{query}", query)

    def build_greeting(self) -> str:
        """인사 메시지 빌드. {{bot_name}} 변수 치환."""
        config = self._config
        context = {"bot_name": config.branding.bot_name}
        return _render_template(config.greeting.message, context)


def _deep_merge(base: dict, override: dict) -> dict:
    """중첩 dict 병합 (override가 우선)."""
    for key, value in override.items():
        if key in base and isinstance(base[key], dict) and isinstance(value, dict):
            _deep_merge(base[key], value)
        else:
            base[key] = value
    return base


# ── 싱글턴 ────────────────────────────────────────────────────────────────

_store: Optional[ServiceChatConfigStore] = None


def get_service_chat_config_store() -> ServiceChatConfigStore:
    global _store
    if _store is None:
        _store = ServiceChatConfigStore()
    return _store