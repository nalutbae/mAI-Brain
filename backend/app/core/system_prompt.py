"""mAI-Brain — 시스템 프롬프트 관리 엔진

워크스페이스별/모드별 커스텀 프롬프트 CRUD 및 변수 치환.

핵심 기능:
1. 프롬프트 CRUD (JSON 파일 영속화)
2. 템플릿 변수 치환 ({{workspace_name}}, {{document_count}}, {{mode}}, {{date}})
3. 미리보기 (치환 결과 확인)
4. 기본 프롬프트 관리 (is_default)
5. 워크스페이스별 프롬프트 해석 (workspace > default > 하드코딩 프롬프트)
"""

import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from app.config import ChatMode
from app.models.system_prompt import (
    SystemPrompt,
    SystemPromptCreate,
    SystemPromptPreview,
    SystemPromptUpdate,
    SUPPORTED_VARIABLES,
)
from app.models.workspace import DATA_DIR

# ── 데이터 저장 경로 ──────────────────────────────────────────────────────

PROMPT_DATA_DIR = DATA_DIR.parent / "prompts"
PROMPT_DATA_DIR.mkdir(parents=True, exist_ok=True)


# ── 변수 치환 ─────────────────────────────────────────────────────────────

_VARIABLE_PATTERN = re.compile(r"\{\{(\w+)\}\}")


def _extract_variables(text: str) -> list[str]:
    """프롬프트 텍스트에서 {{변수}} 패턴을 추출."""
    return list(set(_VARIABLE_PATTERN.findall(text)))


def render_prompt(
    prompt_text: str,
    context: Optional[dict[str, str]] = None,
) -> tuple[str, list[str], list[str]]:
    """프롬프트 템플릿 변수를 치환하여 렌더링.

    Args:
        prompt_text: 원본 프롬프트 텍스트 ({{variable}} 포함)
        context: 변수→값 매핑 (None이면 치환 없이 원본 반환)

    Returns:
        (rendered_text, variables_used, variables_missing) 튜플
    """
    if context is None:
        context = {}

    variables_in_text = _extract_variables(prompt_text)
    variables_used: list[str] = []
    variables_missing: list[str] = []

    def replacer(match: re.Match) -> str:
        var_name = match.group(1)
        if var_name in context and context[var_name] is not None:
            variables_used.append(var_name)
            return str(context[var_name])
        variables_missing.append(var_name)
        return match.group(0)  # 치환 불가 → 원본 유지

    rendered = _VARIABLE_PATTERN.sub(replacer, prompt_text)
    return rendered, variables_used, variables_missing


# ── 프롬프트 스토어 ───────────────────────────────────────────────────────

class SystemPromptStore:
    """JSON 파일 기반 시스템 프롬프트 영속 저장소"""

    def __init__(self, data_dir: Path = PROMPT_DATA_DIR):
        self.data_dir = data_dir
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self._prompts: dict[str, SystemPrompt] = {}
        self._load()

    def _load(self):
        """디스크에서 프롬프트 데이터 로드"""
        data_file = self.data_dir / "system_prompts.json"
        if data_file.exists():
            raw = json.loads(data_file.read_text(encoding="utf-8"))
            self._prompts = {k: SystemPrompt(**v) for k, v in raw.items()}
        # 기본 프롬프트 생성 (하드코딩 프롬프트에서 초기화)
        if not self._prompts:
            self._create_defaults()
            self._save()

    def _create_defaults(self):
        """기본 모드별 프롬프트 생성 (llm.py의 하드코딩과 동일)"""
        from app.core.llm import DEFAULT_SYSTEM_PROMPT, DEFAULT_MODE_INSTRUCTIONS

        # 글로벌 기본 시스템 프롬프트
        default_system = SystemPrompt(
            id="default-system",
            workspace_id=None,
            mode=ChatMode.FACT,  # 기본값 (글로벌은 모드 무관하나 스키마 호환)
            prompt_text=DEFAULT_SYSTEM_PROMPT,
            is_default=True,
        )
        self._prompts[default_system.id] = default_system

        # 모드별 기본 프롬프트
        for mode, instruction in DEFAULT_MODE_INSTRUCTIONS.items():
            prompt_id = f"default-{mode.value}"
            prompt = SystemPrompt(
                id=prompt_id,
                workspace_id=None,
                mode=mode,
                prompt_text=instruction,
                is_default=True,
            )
            self._prompts[prompt.id] = prompt

    def _save(self):
        """프롬프트 데이터를 디스크에 저장"""
        data_file = self.data_dir / "system_prompts.json"
        raw = {k: v.model_dump() for k, v in self._prompts.items()}
        data_file.write_text(
            json.dumps(raw, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def list_prompts(
        self,
        workspace_id: Optional[str] = None,
        mode: Optional[ChatMode] = None,
    ) -> list[SystemPrompt]:
        """프롬프트 목록 조회.

        Args:
            workspace_id: 워크스페이스 필터 (None=기본 프롬프트만)
            mode: 모드 필터
        """
        results = list(self._prompts.values())
        if workspace_id is not None:
            results = [p for p in results if p.workspace_id == workspace_id]
        if mode is not None:
            results = [p for p in results if p.mode == mode]
        return results

    def get_prompt(self, prompt_id: str) -> Optional[SystemPrompt]:
        """프롬프트 ID로 조회."""
        return self._prompts.get(prompt_id)

    def get_effective_prompt(
        self,
        mode: ChatMode,
        workspace_id: Optional[str] = None,
    ) -> Optional[SystemPrompt]:
        """모드+워크스페이스에 대한 유효 프롬프트 조회.

        우선순위:
        1. 워크스페이스+모드에 지정된 커스텀 프롬프트
        2. 모드의 기본 프롬프트 (is_default=True)
        3. None (하드코딩 프롬프트 사용)
        """
        # 1. 워크스페이스+모드에 지정된 커스텀 프롬프트
        if workspace_id is not None:
            for p in self._prompts.values():
                if p.workspace_id == workspace_id and p.mode == mode and not p.is_default:
                    return p

        # 2. 모드의 기본 프롬프트
        prompt_id = f"default-{mode.value}"
        if prompt_id in self._prompts:
            return self._prompts[prompt_id]

        # 3. 없으면 None (호출자가 하드코딩 프롬프트 사용)
        return None

    def create_prompt(self, data: SystemPromptCreate) -> SystemPrompt:
        """새 프롬프트 생성."""
        prompt_id = str(uuid.uuid4())[:8]

        # 동일 워크스페이스+모드 조합이 이미 있는지 확인
        for p in self._prompts.values():
            if p.workspace_id == data.workspace_id and p.mode == data.mode and not p.is_default:
                raise ValueError(
                    f"워크스페이스 '{data.workspace_id}'의 {data.mode.value} 모드에 "
                    f"이미 커스텀 프롬프트가 존재합니다 (id={p.id})"
                )

        # 프롬프트 내 변수 추출
        variables = _extract_variables(data.prompt_text)

        prompt = SystemPrompt(
            id=prompt_id,
            workspace_id=data.workspace_id,
            mode=data.mode,
            prompt_text=data.prompt_text,
            variables=variables,
            is_default=data.is_default,
        )
        self._prompts[prompt_id] = prompt
        self._save()
        return prompt

    def update_prompt(
        self,
        prompt_id: str,
        data: SystemPromptUpdate,
    ) -> Optional[SystemPrompt]:
        """프롬프트 수정."""
        prompt = self._prompts.get(prompt_id)
        if not prompt:
            return None

        update_data = data.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            setattr(prompt, key, value)

        # prompt_text 변경 시 변수 재추출
        if data.prompt_text is not None:
            prompt.variables = _extract_variables(data.prompt_text)

        prompt.updated_at = datetime.now(timezone.utc).isoformat()
        self._save()
        return prompt

    def delete_prompt(self, prompt_id: str) -> bool:
        """프롬프트 삭제. 기본 프롬프트는 삭제 불가."""
        prompt = self._prompts.get(prompt_id)
        if not prompt:
            return False
        if prompt.is_default:
            raise ValueError("기본 프롬프트는 삭제할 수 없습니다.")
        del self._prompts[prompt_id]
        self._save()
        return True

    def preview_prompt(
        self,
        prompt_id: str,
        context: Optional[dict[str, str]] = None,
    ) -> Optional[SystemPromptPreview]:
        """프롬프트 미리보기 (변수 치환 결과)."""
        prompt = self._prompts.get(prompt_id)
        if not prompt:
            return None

        rendered, used, missing = render_prompt(prompt.prompt_text, context)
        return SystemPromptPreview(
            id=prompt.id,
            mode=prompt.mode,
            workspace_id=prompt.workspace_id,
            original_text=prompt.prompt_text,
            rendered_text=rendered,
            variables_used=used,
            variables_missing=missing,
        )

    def build_context(
        self,
        workspace_id: Optional[str] = None,
        mode: Optional[str] = None,
    ) -> dict[str, str]:
        """변수 치환에 필요한 컨텍스트 구성.

        워크스페이스 정보를 기반으로 {{workspace_name}},
        {{document_count}}, {{collection_name}} 등을 제공.
        """
        context: dict[str, str] = {}
        now = datetime.now(timezone.utc)

        context["date"] = now.strftime("%Y-%m-%d")

        if mode is not None:
            context["mode"] = mode

        if workspace_id:
            from app.core.workspace import get_workspace_store
            store = get_workspace_store()
            ws = store.get_workspace(workspace_id)
            if ws:
                context["workspace_id"] = ws.id
                context["workspace_name"] = ws.name
                context["document_count"] = str(len(ws.document_ids))
                context["collection_name"] = ws.vector_collection

        return context


# ── 싱글턴 ─────────────────────────────────────────────────────────────────

_store: Optional[SystemPromptStore] = None


def get_system_prompt_store() -> SystemPromptStore:
    global _store
    if _store is None:
        _store = SystemPromptStore()
    return _store