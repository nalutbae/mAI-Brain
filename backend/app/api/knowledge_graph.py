"""지식 그래프 API — 엔티티 추출, 그래프 조회, 검색

엔드포인트:
  POST /api/kg/extract         — 문서에서 엔티티/관계 추출
  GET  /api/kg/graph            — 그래프 시각화 데이터 조회
  GET  /api/kg/entity/{id}      — 엔티티 상세 조회
  GET  /api/kg/search           — 시맨틱 엔티티 검색
  GET  /api/kg/stats            — 그래프 통계
  DELETE /api/kg/document/{id}  — 문서 KG 데이터 삭제
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from qdrant_client.models import Filter, FieldCondition, MatchValue

from app.core.kg_extractor import KGExtractor
from app.core.kg_store import (
    delete_kg_by_document,
    ensure_kg_collections,
    get_entity_detail,
    get_graph_data,
    search_entities,
    store_extraction_result,
)
from app.core.vectordb import QdrantVectorDB, get_vector_db
from app.models.knowledge_graph import (
    EntityType,
    ExtractionRequest,
    ExtractionResult,
    ExtractionStatus,
    GraphData,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/kg", tags=["knowledge-graph"])


def _get_qdrant_client():
    """Qdrant 클라이언트를 가져옵니다 (QdrantVectorDB인 경우만)."""
    vdb = get_vector_db()
    if not isinstance(vdb, QdrantVectorDB):
        raise HTTPException(status_code=500, detail="지식 그래프는 Qdrant에서만 지원됩니다.")
    return vdb.client, vdb.collection_name


@router.post("/extract", response_model=ExtractionResult)
async def extract_knowledge_graph(request: ExtractionRequest):
    """문서에서 엔티티와 관계를 추출합니다."""
    qdrant_client, collection_name = _get_qdrant_client()

    # KG 컬렉션 초기화
    ensure_kg_collections(qdrant_client)

    # 대상 문서 결정
    if request.document_id:
        filter_must = [FieldCondition(key="document_id", match=MatchValue(value=request.document_id))]
    elif request.source:
        filter_must = [FieldCondition(key="source", match=MatchValue(value=request.source))]
    else:
        raise HTTPException(
            status_code=400,
            detail="document_id 또는 source 중 하나를 지정하세요.",
        )

    points, _ = qdrant_client.scroll(
        collection_name=collection_name,
        scroll_filter=Filter(must=filter_must),
        limit=200,
        with_payload=True,
        with_vectors=False,
    )

    if not points:
        raise HTTPException(status_code=404, detail="해당 문서의 청크를 찾을 수 없습니다.")

    # 청크 목록 구성
    chunks = [
        {
            "id": str(p.id),
            "text": (p.payload or {}).get("text", ""),
            "metadata": p.payload or {},
        }
        for p in points
    ]

    document_name = chunks[0]["metadata"].get("source", "unknown") if chunks else "unknown"
    document_id = request.document_id or chunks[0]["metadata"].get("document_id", "unknown")

    # 엔티티 추출
    extractor = KGExtractor()
    result = extractor.extract_from_document(
        chunks=chunks,
        document_id=document_id,
        document_name=document_name,
    )

    # Qdrant에 저장
    try:
        await store_extraction_result(result)
    except Exception as e:
        logger.error("KG 저장 실패: %s", e)
        result.status = ExtractionStatus.FAILED
        result.error = f"저장 실패: {str(e)}"

    return result


@router.get("/graph", response_model=GraphData)
async def get_knowledge_graph(
    document_id: Optional[str] = Query(None, description="특정 문서 ID로 필터링"),
    entity_types: Optional[str] = Query(None, description="엔티티 타입 필터 (쉼표 구분)"),
    limit: int = Query(200, description="최대 노드 수"),
):
    """지식 그래프 시각화 데이터를 조회합니다."""
    qdrant_client, _ = _get_qdrant_client()
    ensure_kg_collections(qdrant_client)

    # 엔티티 타입 파싱
    types: Optional[list[EntityType]] = None
    if entity_types:
        types = [EntityType(t.strip()) for t in entity_types.split(",") if t.strip()]

    try:
        return get_graph_data(
            qdrant_client=qdrant_client,
            document_id=document_id,
            entity_types=types,
            limit=limit,
        )
    except Exception as e:
        logger.error("그래프 조회 실패: %s", e)
        raise HTTPException(status_code=500, detail=f"그래프 조회 실패: {str(e)}")


@router.get("/entity/{entity_id}")
async def get_entity(entity_id: str):
    """특정 엔티티의 상세 정보를 조회합니다."""
    qdrant_client, _ = _get_qdrant_client()

    result = get_entity_detail(qdrant_client, entity_id)
    if result is None:
        raise HTTPException(status_code=404, detail="엔티티를 찾을 수 없습니다.")
    return result


@router.get("/search")
async def search_knowledge_entities(
    query: str = Query(..., description="검색어"),
    entity_types: Optional[str] = Query(None, description="엔티티 타입 필터 (쉼표 구분)"),
    limit: int = Query(20, description="최대 결과 수"),
):
    """시맨틱 검색으로 엔티티를 조회합니다."""
    qdrant_client, _ = _get_qdrant_client()

    types: Optional[list[EntityType]] = None
    if entity_types:
        types = [EntityType(t.strip()) for t in entity_types.split(",") if t.strip()]

    try:
        results = search_entities(
            qdrant_client=qdrant_client,
            query=query,
            entity_types=types,
            limit=limit,
        )
        return {"query": query, "results": results}
    except Exception as e:
        logger.error("엔티티 검색 실패: %s", e)
        raise HTTPException(status_code=500, detail=f"검색 실패: {str(e)}")


@router.get("/stats")
async def get_kg_stats():
    """지식 그래프 통계를 조회합니다."""
    qdrant_client, _ = _get_qdrant_client()

    try:
        from app.core.kg_store import KG_ENTITIES_COLLECTION, KG_RELATIONS_COLLECTION

        entity_count = qdrant_client.count(KG_ENTITIES_COLLECTION).count
        relation_count = qdrant_client.count(KG_RELATIONS_COLLECTION).count

        # 타입별 엔티티 수
        type_counts: dict[str, int] = {}
        offset = None
        while True:
            points, offset = qdrant_client.scroll(
                collection_name=KG_ENTITIES_COLLECTION,
                limit=100,
                offset=offset,
                with_payload=True,
                with_vectors=False,
            )
            for p in points:
                t = (p.payload or {}).get("type", "unknown")
                type_counts[t] = type_counts.get(t, 0) + 1
            if offset is None:
                break

        return {
            "total_entities": entity_count,
            "total_relations": relation_count,
            "entities_by_type": type_counts,
        }
    except Exception as e:
        logger.warning("KG 통계 조회 실패 (컬렉션 없을 수 있음): %s", e)
        return {
            "total_entities": 0,
            "total_relations": 0,
            "entities_by_type": {},
        }


@router.delete("/document/{document_id}")
async def delete_document_kg(document_id: str):
    """특정 문서의 지식 그래프 데이터를 삭제합니다."""
    qdrant_client, _ = _get_qdrant_client()

    try:
        deleted = delete_kg_by_document(qdrant_client, document_id)
        return {"message": f"문서 {document_id}의 KG 데이터 {deleted}개 삭제 완료", "deleted_count": deleted}
    except Exception as e:
        logger.error("KG 삭제 실패: %s", e)
        raise HTTPException(status_code=500, detail=f"삭제 실패: {str(e)}")