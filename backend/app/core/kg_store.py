"""지식 그래프 Qdrant 스토리지

엔티티와 관계를 Qdrant의 별도 컬렉션에 저장합니다.
엔티티는 벡터 임베딩과 함께 저장하여 시맨틱 검색을 지원합니다.
관계는 페이로드 필드로 저장합니다.
"""

from __future__ import annotations

import logging
from typing import Optional

from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    MatchValue,
    PointStruct,
    PayloadSchemaType,
    VectorParams,
)

from app.config import get_settings
from app.core.vectordb import get_vector_db
from app.models.knowledge_graph import (
    Entity,
    EntityType,
    ExtractionResult,
    GraphData,
    GraphEdge,
    GraphNode,
    Relation,
    RelationType,
)

logger = logging.getLogger(__name__)

KG_ENTITIES_COLLECTION = "mai_brain_kg_entities"
KG_RELATIONS_COLLECTION = "mai_brain_kg_relations"


# ── 컬렉션 초기화 ──────────────────────────────────────────────────────────────


def ensure_kg_collections(qdrant_client: QdrantClient, embedding_dim: int = 768) -> None:
    """KG 컬렉션이 없으면 생성합니다."""
    settings = get_settings()

    # 엔티티 컬렉션
    if not qdrant_client.collection_exists(KG_ENTITIES_COLLECTION):
        qdrant_client.create_collection(
            collection_name=KG_ENTITIES_COLLECTION,
            vectors_config=VectorParams(
                size=embedding_dim,
                distance=Distance.COSINE,
            ),
        )
        # 인덱스 생성
        qdrant_client.create_payload_index(
            collection_name=KG_ENTITIES_COLLECTION,
            field_name="type",
            field_schema=PayloadSchemaType.KEYWORD,
        )
        qdrant_client.create_payload_index(
            collection_name=KG_ENTITIES_COLLECTION,
            field_name="name",
            field_schema=PayloadSchemaType.KEYWORD,
        )
        qdrant_client.create_payload_index(
            collection_name=KG_ENTITIES_COLLECTION,
            field_name="source_document_ids",
            field_schema=PayloadSchemaType.KEYWORD,
        )
        logger.info("KG 엔티티 컬렉션 생성: %s", KG_ENTITIES_COLLECTION)

    # 관계 컬렉션 (벡터 없음 — 페이로드만)
    if not qdrant_client.collection_exists(KG_RELATIONS_COLLECTION):
        qdrant_client.create_collection(
            collection_name=KG_RELATIONS_COLLECTION,
            vectors_config=VectorParams(
                size=embedding_dim,
                distance=Distance.COSINE,
            ),
        )
        qdrant_client.create_payload_index(
            collection_name=KG_RELATIONS_COLLECTION,
            field_name="relation_type",
            field_schema=PayloadSchemaType.KEYWORD,
        )
        qdrant_client.create_payload_index(
            collection_name=KG_RELATIONS_COLLECTION,
            field_name="source_entity_id",
            field_schema=PayloadSchemaType.KEYWORD,
        )
        qdrant_client.create_payload_index(
            collection_name=KG_RELATIONS_COLLECTION,
            field_name="target_entity_id",
            field_schema=PayloadSchemaType.KEYWORD,
        )
        logger.info("KG 관계 컬렉션 생성: %s", KG_RELATIONS_COLLECTION)


# ── 엔티티/관계 저장 ────────────────────────────────────────────────────────────


async def store_extraction_result(result: ExtractionResult) -> None:
    """추출 결과를 Qdrant KG 컬렉션에 저장합니다.

    엔티티는 임베딩과 함께 저장하여 시맨틱 검색을 지원합니다.
    관계는 소스/타겟 엔티티 ID와 함께 저장합니다.
    """
    from app.core.vectordb import get_vector_db

    vdb = get_vector_db()
    settings = get_settings()

    # Qdrant 클라이언트 가져오기
    qdrant_client = vdb.client if hasattr(vdb, "client") else None
    if qdrant_client is None:
        logger.error("Qdrant 클라이언트를 가져올 수 없습니다.")
        return

    # 컬렉션 초기화
    ensure_kg_collections(qdrant_client, embedding_dim=settings.ollama_embedding_dim)

    # 임베딩 프로바이더로 엔티티 이름 임베딩
    from app.core.vectordb import get_embedding_provider
    embedding_provider = get_embedding_provider()

    if result.entities:
        # 엔티티 이름 목록 임베딩
        entity_names = [e.name + (f": {e.description}" if e.description else "") for e in result.entities]
        embed_result = embedding_provider.encode(entity_names)
        dense_vectors = embed_result.dense if hasattr(embed_result, "dense") else embed_result

        # 엔티티 포인트 구성
        entity_points = []
        for i, entity in enumerate(result.entities):
            vector = dense_vectors[i] if i < len(dense_vectors) else [0.0] * settings.ollama_embedding_dim
            entity_points.append(PointStruct(
                id=entity.id,
                vector=vector.tolist() if hasattr(vector, "tolist") else list(vector),
                payload={
                    "name": entity.name,
                    "type": entity.type.value,
                    "description": entity.description or "",
                    "properties": entity.properties,
                    "source_document_ids": entity.source_document_ids,
                    "source_chunks": entity.source_chunks,
                    "mention_count": entity.mention_count,
                    "created_at": entity.created_at,
                    "updated_at": entity.updated_at,
                },
            ))

        # 기존 동일 엔티티와 병합 후 업서트
        qdrant_client.upsert(
            collection_name=KG_ENTITIES_COLLECTION,
            points=entity_points,
        )
        logger.info("KG 엔티티 %d개 저장 완료", len(entity_points))

    if result.relations:
        # 관계 포인트 구성 (벡터는 엔티티 임베딩의 평균 사용)
        relation_points = []
        entity_map = {e.id: e for e in result.entities}

        for rel in result.relations:
            # 관계 설명을 임베딩
            rel_text = f"{rel.relation_type.value}: {rel.description or ''}"
            rel_points_batch = []
            relation_points.append(PointStruct(
                id=rel.id,
                vector=[0.0] * settings.ollama_embedding_dim,  # 더미 벡터 — 관계는 벡터 검색 대상이 아님
                payload={
                    "source_entity_id": rel.source_entity_id,
                    "target_entity_id": rel.target_entity_id,
                    "relation_type": rel.relation_type.value,
                    "description": rel.description or "",
                    "weight": rel.weight,
                    "source_document_ids": rel.source_document_ids,
                    "evidence_text": rel.evidence_text or "",
                    "created_at": rel.created_at,
                },
            ))

        qdrant_client.upsert(
            collection_name=KG_RELATIONS_COLLECTION,
            points=relation_points,
        )
        logger.info("KG 관계 %d개 저장 완료", len(relation_points))


# ── 그래프 조회 ──────────────────────────────────────────────────────────────────


def get_graph_data(
    qdrant_client: QdrantClient,
    document_id: Optional[str] = None,
    entity_types: Optional[list[EntityType]] = None,
    limit: int = 200,
) -> GraphData:
    """그래프 시각화 데이터를 조회합니다.

    Args:
        document_id: 특정 문서의 엔티티만 필터링
        entity_types: 특정 엔티티 타입만 필터링
        limit: 최대 노드 수

    Returns:
        GraphData (nodes + edges + stats)
    """
    # 엔티티 조회
    entity_filter_conditions = []
    if document_id:
        entity_filter_conditions.append(
            FieldCondition(key="source_document_ids", match=MatchValue(value=document_id))
        )
    if entity_types:
        entity_filter_conditions.append(
            FieldCondition(key="type", match=MatchValue(value=[t.value for t in entity_types]))
        )

    entity_filter = Filter(must=entity_filter_conditions) if entity_filter_conditions else None

    # 스크롤로 모든 엔티티 가져오기
    entities_payload = []
    offset = None
    while len(entities_payload) < limit:
        points, offset = qdrant_client.scroll(
            collection_name=KG_ENTITIES_COLLECTION,
            scroll_filter=entity_filter,
            limit=min(100, limit - len(entities_payload)),
            offset=offset,
            with_payload=True,
            with_vectors=False,
        )
        entities_payload.extend(points)
        if offset is None:
            break

    # 엔티티 ID 수집
    entity_ids = set()
    nodes: list[GraphNode] = []
    type_counts: dict[str, int] = {}

    for point in entities_payload[:limit]:
        p = point.payload
        entity_ids.add(point.id)
        type_val = p.get("type", "concept")
        type_counts[type_val] = type_counts.get(type_val, 0) + 1
        nodes.append(GraphNode(
            id=point.id,
            label=p.get("name", ""),
            type=EntityType(type_val),
            description=p.get("description"),
            mention_count=p.get("mention_count", 0),
            group=type_val,
        ))

    # 관계 조회 (엔티티 ID에 해당하는 관계만)
    if not entity_ids:
        return GraphData(nodes=[], edges=[], stats=type_counts)

    edges: list[GraphEdge] = []
    for eid in list(entity_ids)[:100]:  # 배치 제한
        # 소스 엔티티로 필터
        source_rels, _ = qdrant_client.scroll(
            collection_name=KG_RELATIONS_COLLECTION,
            scroll_filter=Filter(must=[
                FieldCondition(key="source_entity_id", match=MatchValue(value=eid)),
            ]),
            limit=50,
            with_payload=True,
            with_vectors=False,
        )
        for rel_point in source_rels:
            p = rel_point.payload
            target_id = p.get("target_entity_id", "")
            if target_id in entity_ids:
                edges.append(GraphEdge(
                    id=rel_point.id,
                    source=p.get("source_entity_id", ""),
                    target=target_id,
                    label=p.get("relation_type", "").replace("_", " "),
                    relation_type=RelationType(p.get("relation_type", "related_to")),
                    weight=p.get("weight", 1.0),
                ))

    return GraphData(
        nodes=nodes,
        edges=edges,
        stats=type_counts,
    )


def get_entity_detail(
    qdrant_client: QdrantClient,
    entity_id: str,
) -> Optional[dict]:
    """특정 엔티티의 상세 정보를 조회합니다."""
    try:
        points = qdrant_client.retrieve(
            collection_name=KG_ENTITIES_COLLECTION,
            ids=[entity_id],
            with_payload=True,
            with_vectors=False,
        )
        if not points:
            return None

        entity_point = points[0]
        p = entity_point.payload

        # 관련 관계 조회
        source_rels, _ = qdrant_client.scroll(
            collection_name=KG_RELATIONS_COLLECTION,
            scroll_filter=Filter(should=[
                FieldCondition(key="source_entity_id", match=MatchValue(value=entity_id)),
                FieldCondition(key="target_entity_id", match=MatchValue(value=entity_id)),
            ]),
            limit=50,
            with_payload=True,
            with_vectors=False,
        )

        related_entities = []
        for rel_point in source_rels:
            rp = rel_point.payload
            other_id = (
                rp.get("target_entity_id") if rp.get("source_entity_id") == entity_id
                else rp.get("source_entity_id")
            )
            # 관련 엔티티 정보 조회
            other_points = qdrant_client.retrieve(
                collection_name=KG_ENTITIES_COLLECTION,
                ids=[other_id],
                with_payload=True,
                with_vectors=False,
            )
            if other_points:
                op = other_points[0].payload
                related_entities.append({
                    "id": other_id,
                    "name": op.get("name", ""),
                    "type": op.get("type", ""),
                    "relation_type": rp.get("relation_type", ""),
                    "relation_description": rp.get("description", ""),
                    "weight": rp.get("weight", 1.0),
                })

        return {
            "id": entity_id,
            "name": p.get("name", ""),
            "type": p.get("type", ""),
            "description": p.get("description", ""),
            "properties": p.get("properties", {}),
            "mention_count": p.get("mention_count", 0),
            "source_document_ids": p.get("source_document_ids", []),
            "related_entities": related_entities,
        }

    except Exception as e:
        logger.error("엔티티 상세 조회 실패: %s", e)
        return None


def search_entities(
    qdrant_client: QdrantClient,
    query: str,
    entity_types: Optional[list[EntityType]] = None,
    limit: int = 20,
) -> list[dict]:
    """시맨틱 검색으로 엔티티를 조회합니다."""
    from app.core.vectordb import get_embedding_provider

    embedding_provider = get_embedding_provider()
    settings = get_settings()
    ensure_kg_collections(qdrant_client, embedding_dim=settings.ollama_embedding_dim)

    # 쿼리 임베딩
    query_embed = embedding_provider.encode([query])
    query_vector = query_embed.dense[0] if hasattr(query_embed, "dense") else query_embed[0]
    query_vector = query_vector.tolist() if hasattr(query_vector, "tolist") else list(query_vector)

    # 필터 조건
    filter_conditions = []
    if entity_types:
        filter_conditions.append(
            FieldCondition(key="type", match=MatchValue(value=[t.value for t in entity_types]))
        )

    # 시맨틱 검색
    results = qdrant_client.search(
        collection_name=KG_ENTITIES_COLLECTION,
        query_vector=query_vector,
        limit=limit,
        query_filter=Filter(must=filter_conditions) if filter_conditions else None,
        with_payload=True,
    )

    return [
        {
            "id": str(r.id),
            "name": r.payload.get("name", ""),
            "type": r.payload.get("type", ""),
            "description": r.payload.get("description", ""),
            "mention_count": r.payload.get("mention_count", 0),
            "score": r.score,
        }
        for r in results
    ]


def delete_kg_by_document(qdrant_client: QdrantClient, document_id: str) -> int:
    """특정 문서의 KG 데이터를 삭제합니다."""
    deleted = 0

    # 해당 문서의 엔티티 찾기
    entity_points, _ = qdrant_client.scroll(
        collection_name=KG_ENTITIES_COLLECTION,
        scroll_filter=Filter(must=[
            FieldCondition(key="source_document_ids", match=MatchValue(value=document_id)),
        ]),
        limit=1000,
        with_payload=True,
        with_vectors=False,
    )

    entity_ids = [p.id for p in entity_points]

    # 엔티티 삭제
    if entity_ids:
        qdrant_client.delete(
            collection_name=KG_ENTITIES_COLLECTION,
            points_selector=entity_ids,
        )
        deleted += len(entity_ids)

    # 관련 관계 삭제
    for eid in entity_ids[:100]:
        rel_points, _ = qdrant_client.scroll(
            collection_name=KG_RELATIONS_COLLECTION,
            scroll_filter=Filter(should=[
                FieldCondition(key="source_entity_id", match=MatchValue(value=eid)),
                FieldCondition(key="target_entity_id", match=MatchValue(value=eid)),
            ]),
            limit=100,
            with_payload=True,
            with_vectors=False,
        )
        rel_ids = [p.id for p in rel_points]
        if rel_ids:
            qdrant_client.delete(
                collection_name=KG_RELATIONS_COLLECTION,
                points_selector=rel_ids,
            )
            deleted += len(rel_ids)

    logger.info("문서 %s의 KG 데이터 %d개 삭제 완료", document_id, deleted)
    return deleted