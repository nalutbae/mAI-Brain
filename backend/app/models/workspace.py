"""mAI-Brain — 워크스페이스 데이터 모델

프로젝트/도메인별 독립 컨텍스트를 제공하는 워크스페이스 시스템.

핵심 개념:
- Workspace: 문서, 세션, 프롬프트를 격리하는 독립 공간
- 각 워크스페이스는 고유한 Qdrant 컬렉션 이름을 가짐 (검색 스코프 제한)
- 문서는 워크스페이스에 할당되어 해당 컬렉션에 인덱싱됨
- 세션은 특정 워크스페이스에 속함
"""

from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field


# ── 데이터 저장 경로 ──────────────────────────────────────────────────────

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "workspaces"
DATA_DIR.mkdir(parents=True, exist_ok=True)


# ── Pydantic 모델 ──────────────────────────────────────────────────────────

class Workspace(BaseModel):
    """워크스페이스"""
    id: str
    name: str
    description: str = ""
    system_prompt: str = ""
    vector_collection: str = ""  # Qdrant 컬렉션명 (비어있으면 id 기반 자동 생성)
    document_ids: list[str] = Field(default_factory=list)
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class WorkspaceCreate(BaseModel):
    """워크스페이스 생성 요청"""
    name: str
    description: str = ""
    system_prompt: str = ""


class WorkspaceUpdate(BaseModel):
    """워크스페이스 수정 요청"""
    name: Optional[str] = None
    description: Optional[str] = None
    system_prompt: Optional[str] = None


class WorkspaceDocumentAssign(BaseModel):
    """워크스페이스에 문서 할당/해제"""
    document_ids: list[str]
    action: str = "assign"  # "assign" or "unassign"


class WorkspaceListResponse(BaseModel):
    """워크스페이스 목록 응답"""
    workspaces: list[Workspace]
    total: int


class WorkspaceSearchRequest(BaseModel):
    """워크스페이스 내 검색 요청"""
    query: str
    workspace_id: str
    mode: str = "fact"
    limit: int = 5