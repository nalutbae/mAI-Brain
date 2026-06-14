"""mAI-Brain — 워크스페이스 관리 엔진

Qdrant 컬렉션 분리 기반 워크스페이스 격리 시스템.

핵심 기능:
1. 워크스페이스 CRUD (JSON 파일 영속화)
2. 워크스페이스별 Qdrant 컬렉션 관리
3. 문서 할당/해제 시 벡터 동기화
4. 워크스페이스 접근 시 검색 스코프 제한
"""

import json
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from app.models.workspace import Workspace, WorkspaceCreate, WorkspaceUpdate, DATA_DIR

logger = logging.getLogger(__name__)


class WorkspaceStore:
    """JSON 파일 기반 워크스페이스 영속 저장소"""

    def __init__(self, data_dir: Path = DATA_DIR):
        self.data_dir = data_dir
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self._workspaces: dict[str, Workspace] = {}
        self._load()

    def _load(self):
        """디스크에서 워크스페이스 데이터 로드"""
        data_file = self.data_dir / "workspaces.json"
        if data_file.exists():
            try:
                raw = json.loads(data_file.read_text(encoding="utf-8"))
                self._workspaces = {k: Workspace(**v) for k, v in raw.items()}
            except (json.JSONDecodeError, Exception) as e:
                logger.warning("워크스페이스 데이터 로드 실패, 초기화: %s", e)
                self._workspaces = {}
        # 기본 워크스페이스가 없으면 생성
        if not self._workspaces:
            default = Workspace(
                id="default",
                name="기본 워크스페이스",
                description="모든 문서가 포함된 기본 워크스페이스",
                system_prompt="",
                vector_collection="mai_brain_documents",
                document_ids=[],
            )
            self._workspaces[default.id] = default
            self._save()

    def _save(self):
        """워크스페이스 데이터를 디스크에 저장"""
        data_file = self.data_dir / "workspaces.json"
        raw = {k: v.model_dump() for k, v in self._workspaces.items()}
        data_file.write_text(json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8")

    def list_workspaces(self) -> list[Workspace]:
        return list(self._workspaces.values())

    def get_workspace(self, workspace_id: str) -> Optional[Workspace]:
        return self._workspaces.get(workspace_id)

    def get_default_workspace(self) -> Workspace:
        """기본 워크스페이스 반환 (항상 존재 보장)"""
        default = self._workspaces.get("default")
        if default is None:
            # 정책상 항상 존재해야 함
            default = Workspace(
                id="default",
                name="기본 워크스페이스",
                description="모든 문서가 포함된 기본 워크스페이스",
                system_prompt="",
                vector_collection="mai_brain_documents",
                document_ids=[],
            )
            self._workspaces["default"] = default
            self._save()
        return default

    def create_workspace(self, data: WorkspaceCreate) -> Workspace:
        workspace_id = str(uuid.uuid4())[:8]
        collection_name = f"ws_{workspace_id}"
        workspace = Workspace(
            id=workspace_id,
            name=data.name,
            description=data.description,
            system_prompt=data.system_prompt,
            vector_collection=collection_name,
            document_ids=[],
        )
        self._workspaces[workspace_id] = workspace
        self._save()
        # Qdrant에 워크스페이스 전용 컬렉션 생성
        self._ensure_collection(collection_name)
        logger.info("워크스페이스 생성: id=%s, name=%s, collection=%s",
                     workspace_id, data.name, collection_name)
        return workspace

    def update_workspace(self, workspace_id: str, data: WorkspaceUpdate) -> Optional[Workspace]:
        workspace = self._workspaces.get(workspace_id)
        if not workspace:
            return None
        update_data = data.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            setattr(workspace, key, value)
        workspace.updated_at = datetime.now(timezone.utc).isoformat()
        self._save()
        return workspace

    def delete_workspace(self, workspace_id: str) -> bool:
        """워크스페이스 삭제. 기본 워크스페이스는 삭제 불가."""
        if workspace_id == "default":
            return False
        workspace = self._workspaces.get(workspace_id)
        if not workspace:
            return False
        # Qdrant 컬렉션 삭제 시도 (실패해도 메타데이터는 삭제)
        self._delete_collection(workspace.vector_collection)
        del self._workspaces[workspace_id]
        self._save()
        logger.info("워크스페이스 삭제: id=%s", workspace_id)
        return True

    def assign_documents(self, workspace_id: str, document_ids: list[str]) -> Optional[Workspace]:
        """워크스페이스에 문서 할당"""
        workspace = self._workspaces.get(workspace_id)
        if not workspace:
            return None
        for doc_id in document_ids:
            if doc_id not in workspace.document_ids:
                workspace.document_ids.append(doc_id)
        workspace.updated_at = datetime.now(timezone.utc).isoformat()
        self._save()
        return workspace

    def unassign_documents(self, workspace_id: str, document_ids: list[str]) -> Optional[Workspace]:
        """워크스페이스에서 문서 해제"""
        workspace = self._workspaces.get(workspace_id)
        if not workspace:
            return None
        workspace.document_ids = [d for d in workspace.document_ids if d not in document_ids]
        workspace.updated_at = datetime.now(timezone.utc).isoformat()
        self._save()
        return workspace

    # ── Qdrant 컬렉션 관리 ────────────────────────────────────────────────

    def _ensure_collection(self, collection_name: str) -> bool:
        """Qdrant 컬렉션이 없으면 생성"""
        try:
            from app.core.qdrant import get_qdrant
            from qdrant_client import models

            qdrant = get_qdrant()

            if qdrant.client.collection_exists(collection_name):
                logger.info("컬렉션 이미 존재: %s", collection_name)
                return True

            # 실제 임베딩 프로바이더에서 차원 감지 (Settings 기본값 대신)
            from app.core.embedding import get_embedding_provider
            try:
                emb = get_embedding_provider()
                vector_size = emb.encode(["dim probe"]).dim
            except Exception:
                vector_size = qdrant.vector_size  # 폴백: 설정 기반 차원

            qdrant.client.create_collection(
                collection_name=collection_name,
                vectors_config={
                    "dense": models.VectorParams(
                        size=vector_size,
                        distance=models.Distance.COSINE,
                    )
                },
                sparse_vectors_config={
                    "sparse": models.SparseVectorParams(
                        index=models.SparseIndexParams(on_disk=True),
                    )
                },
                optimizers_config=models.OptimizersConfigDiff(
                    indexing_threshold=20000,
                ),
                replication_factor=1,
            )
            logger.info("Qdrant 컬렉션 생성: %s (vector_size=%d)", collection_name, vector_size)
            return True
        except Exception as e:
            logger.error("Qdrant 컬렉션 생성 실패: %s — %s", collection_name, e)
            return False

    def _delete_collection(self, collection_name: str) -> bool:
        """Qdrant 컬렉션 삭제"""
        # 기본 컬렉션은 삭제 금지
        if collection_name == "mai_brain_documents":
            logger.warning("기본 컬렉션은 삭제할 수 없음: %s", collection_name)
            return False
        try:
            from app.core.qdrant import get_qdrant
            qdrant = get_qdrant()
            if qdrant.client.collection_exists(collection_name):
                qdrant.client.delete_collection(collection_name)
                logger.info("Qdrant 컬렉션 삭제: %s", collection_name)
                return True
            return True  # 존재하지 않으면 성공
        except Exception as e:
            logger.error("Qdrant 컬렉션 삭제 실패: %s — %s", collection_name, e)
            return False

    def get_collection_name(self, workspace_id: str) -> str:
        """워크스페이스의 Qdrant 컬렉션 이름 반환.
        
        워크스페이스가 없으면 기본 컬렉션 이름 반환.
        컬렉션이 존재하지 않으면 자동 생성 (임베딩 차원 불일치 방지).
        """
        workspace = self._workspaces.get(workspace_id)
        if workspace and workspace.vector_collection:
            # 컬렉션이 존재하는지 확인, 없으면 생성
            self._ensure_collection(workspace.vector_collection)
            return workspace.vector_collection
        # 기본 워크스페이스의 컬렉션
        default = self.get_default_workspace()
        return default.vector_collection


# ── 싱글턴 인스턴스 ───────────────────────────────────────────────────────

_store: Optional[WorkspaceStore] = None


def get_workspace_store() -> WorkspaceStore:
    global _store
    if _store is None:
        _store = WorkspaceStore()
    return _store