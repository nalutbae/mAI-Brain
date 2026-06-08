"""mAI-Brain — 워크스페이스 API

엔드포인트:
- GET    /api/workspaces                    — 워크스페이스 목록
- POST   /api/workspaces                    — 워크스페이스 생성
- GET    /api/workspaces/{id}               — 워크스페이스 조회
- PUT    /api/workspaces/{id}               — 워크스페이스 수정
- DELETE  /api/workspaces/{id}              — 워크스페이스 삭제
- POST   /api/workspaces/{id}/documents     — 문서 할당
- DELETE  /api/workspaces/{id}/documents    — 문서 해제
- GET    /api/workspaces/{id}/documents     — 워크스페이스 내 문서 목록
- POST   /api/workspaces/{id}/search        — 워크스페이스 내 검색
"""

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from app.models.workspace import (
    Workspace,
    WorkspaceCreate,
    WorkspaceUpdate,
    WorkspaceDocumentAssign,
    WorkspaceListResponse,
)
from app.core.workspace import get_workspace_store

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("", response_model=WorkspaceListResponse)
def list_workspaces():
    """워크스페이스 목록 조회"""
    store = get_workspace_store()
    workspaces = store.list_workspaces()
    return WorkspaceListResponse(workspaces=workspaces, total=len(workspaces))


@router.post("", response_model=Workspace, status_code=201)
def create_workspace(data: WorkspaceCreate):
    """워크스페이스 생성
    
    워크스페이스를 생성하면 Qdrant에 전용 컬렉션이 자동으로 생성됩니다.
    """
    store = get_workspace_store()
    return store.create_workspace(data)


@router.get("/{workspace_id}", response_model=Workspace)
def get_workspace(workspace_id: str):
    """워크스페이스 상세 조회"""
    store = get_workspace_store()
    workspace = store.get_workspace(workspace_id)
    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found")
    return workspace


@router.put("/{workspace_id}", response_model=Workspace)
def update_workspace(workspace_id: str, data: WorkspaceUpdate):
    """워크스페이스 수정 (이름, 설명, 시스템 프롬프트)"""
    store = get_workspace_store()
    workspace = store.update_workspace(workspace_id, data)
    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found")
    return workspace


@router.delete("/{workspace_id}")
def delete_workspace(workspace_id: str):
    """워크스페이스 삭제. 기본 워크스페이스는 삭제 불가."""
    if workspace_id == "default":
        raise HTTPException(status_code=400, detail="Cannot delete default workspace")
    store = get_workspace_store()
    if not store.delete_workspace(workspace_id):
        raise HTTPException(status_code=404, detail="Workspace not found")
    return {"message": "Workspace deleted", "workspace_id": workspace_id}


@router.post("/{workspace_id}/documents", response_model=Workspace)
def assign_documents(workspace_id: str, data: WorkspaceDocumentAssign):
    """워크스페이스에 문서 할당.
    
    문서를 워크스페이스에 할당하면, 해당 워크스페이스의 컬렉션에서 
    검색 시 이 문서의 벡터가 포함됩니다.
    """
    store = get_workspace_store()
    workspace = store.assign_documents(workspace_id, data.document_ids)
    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found")
    return workspace


@router.delete("/{workspace_id}/documents", response_model=Workspace)
def unassign_documents(workspace_id: str, data: WorkspaceDocumentAssign):
    """워크스페이스에서 문서 해제"""
    store = get_workspace_store()
    workspace = store.unassign_documents(workspace_id, data.document_ids)
    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found")
    return workspace


@router.get("/{workspace_id}/documents")
def get_workspace_documents(workspace_id: str):
    """워크스페이스 내 문서 목록.
    
    워크스페이스에 할당된 문서의 인덱싱 상태를 반환합니다.
    """
    store = get_workspace_store()
    workspace = store.get_workspace(workspace_id)
    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found")

    from app.core.qdrant import get_qdrant
    from app.ingestion.indexer import get_tracker
    from app.models.document import DocumentInfo, IndexingStatus

    documents = []

    if workspace.document_ids:
        tracker = get_tracker()
        tracker_states = {s["document_id"]: s for s in tracker.list_all()}

        for doc_id in workspace.document_ids:
            tracker_entry = tracker_states.get(doc_id)
            if tracker_entry:
                status = IndexingStatus(tracker_entry.get("status", "completed"))
                documents.append(DocumentInfo(
                    document_id=doc_id,
                    filename=tracker_entry.get("filename", doc_id),
                    status=status,
                    total_chunks=tracker_entry.get("total_chunks"),
                    created_at=tracker_entry.get("created_at"),
                ))
            else:
                documents.append(DocumentInfo(
                    document_id=doc_id,
                    filename=doc_id,
                    status=IndexingStatus.COMPLETED,
                ))

    return {"documents": documents, "total": len(documents)}


@router.post("/{workspace_id}/search")
def search_workspace(
    workspace_id: str,
    query: str = Query(..., min_length=1),
    mode: str = Query(default="fact"),
    limit: int = Query(default=5, ge=1, le=50),
):
    """워크스페이스 내 하이브리드 검색.
    
    워크스페이스의 전용 컬렉션에서 검색을 수행합니다.
    기본 워크스페이스는 전역 컬렉션(mai_brain_documents)에서 검색합니다.
    """
    store = get_workspace_store()
    workspace = store.get_workspace(workspace_id)
    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found")

    from app.config import ChatMode
    from app.core.search import hybrid_search
    from app.core.qdrant import get_qdrant

    try:
        chat_mode = ChatMode(mode)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid mode: {mode}. Use: fact, summary, column, reasoning",
        )

    qdrant = get_qdrant()
    collection_name = workspace.vector_collection

    if not qdrant.client.collection_exists(collection_name):
        return {
            "hits": [],
            "query": query,
            "mode": mode,
            "workspace_id": workspace_id,
            "workspace_name": workspace.name,
        }

    result = hybrid_search(
        query=query,
        mode=chat_mode,
        collection_name=collection_name,
        limit=limit,
    )

    return {
        "hits": [
            {
                "text": h.text,
                "source": h.source,
                "score": h.score,
                "chunk_index": h.chunk_index,
                "page": h.page,
            }
            for h in result.hits
        ],
        "query": result.query,
        "mode": result.mode.value,
        "workspace_id": workspace_id,
        "workspace_name": workspace.name,
    }