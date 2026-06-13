"""지식 그래프 모델 — 엔티티, 관계, 그래프 시각화 데이터 구조

엔티티: 인물, 조직, 법률 조문, 개념 등 문서에서 추출된 명명 개체
관계: 엔티티 간의 의미적 연결 (인용, 소속, 영향, 동의어 등)
"""


from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


# ── 열거형 ────────────────────────────────────────────────────────────────────


class EntityType(str, Enum):
    """엔티티 타입."""
    PERSON = "person"          # 인물
    ORGANIZATION = "organization"  # 조직/기관
    LAW_ARTICLE = "law_article"    # 법률 조문
    CONCEPT = "concept"          # 개념/용어
    EVENT = "event"            # 사건
    LOCATION = "location"        # 장소
    DOCUMENT = "document"        # 문서
    TECHNOLOGY = "technology"     # 기술/제품
    ROLE = "role"              # 직위/역할


class RelationType(str, Enum):
    """관계 타입."""
    CITES = "cites"              # 인용 (법률 조문 간)
    BELONGS_TO = "belongs_to"      # 소속 (인물→조직)
    INFLUENCES = "influences"      # 영향
    MENTIONS = "mentions"         # 언급
    DEFINES = "defines"          # 정의
    CONTRADICTS = "contradicts"    # 모순/충돌
    SUPPORTS = "supports"         # 지지/근거
    RELATED_TO = "related_to"      # 일반적 관계
    SYNONYM_OF = "synonym_of"      # 동의어
    PART_OF = "part_of"          # 부분-전체
    PRECEDES = "precedes"        # 선후관계
    OCCURRED_AT = "occurred_at"    # 사건-장소


class ExtractionStatus(str, Enum):
    """추출 상태."""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


# ── 엔티티 ─────────────────────────────────────────────────────────────────────


class Entity(BaseModel):
    """지식 그래프 엔티티."""
    id: str = Field(default_factory=lambda: f"ent-{uuid.uuid4().hex[:12]}")
    name: str                          # 엔티티 이름 (예: "대한민국 헌법 제21조")
    type: EntityType                   # 엔티티 타입
    description: Optional[str] = None  # 간단 설명
    properties: dict = Field(default_factory=dict)  # 추가 속성 (법률 번호, 소속 등)
    source_document_ids: list[str] = Field(default_factory=list)  # 등장 문서 ID
    source_chunks: list[str] = Field(default_factory=list)        # 등장 청크 ID
    mention_count: int = 0             # 총 언급 횟수
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def merge(self, other: Entity) -> Entity:
        """동일 엔티티 병합 (같은 이름+타입)."""
        return Entity(
            id=self.id,
            name=self.name,
            type=self.type,
            description=other.description or self.description,
            properties={**self.properties, **other.properties},
            source_document_ids=list(set(self.source_document_ids + other.source_document_ids)),
            source_chunks=list(set(self.source_chunks + other.source_chunks)),
            mention_count=self.mention_count + other.mention_count,
            created_at=min(self.created_at, other.created_at),
            updated_at=max(self.updated_at, other.updated_at),
        )


class Relation(BaseModel):
    """엔티티 간 관계."""
    id: str = Field(default_factory=lambda: f"rel-{uuid.uuid4().hex[:12]}")
    source_entity_id: str      # 출발 엔티티
    target_entity_id: str      # 도착 엔티티
    relation_type: RelationType
    description: Optional[str] = None  # 관계 설명
    weight: float = 1.0                 # 관계 강도 (0.0~1.0)
    source_document_ids: list[str] = Field(default_factory=list)
    evidence_text: Optional[str] = None  # 근거 텍스트
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


# ── 추출 결과 ──────────────────────────────────────────────────────────────────


class ExtractionResult(BaseModel):
    """문서에서 추출한 엔티티+관계 결과."""
    document_id: str
    document_name: str
    entities: list[Entity] = Field(default_factory=list)
    relations: list[Relation] = Field(default_factory=list)
    status: ExtractionStatus = ExtractionStatus.COMPLETED
    error: Optional[str] = None
    extracted_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


# ── 그래프 시각화 ──────────────────────────────────────────────────────────────


class GraphNode(BaseModel):
    """D3.js/vis.js 노드."""
    id: str
    label: str
    type: EntityType
    description: Optional[str] = None
    mention_count: int = 0
    group: str = ""  # 타입 기반 그룹 (색상 구분용)


class GraphEdge(BaseModel):
    """D3.js/vis.js 엣지."""
    id: str
    source: str   # 출발 노드 ID
    target: str   # 도착 노드 ID
    label: str = ""  # 관계 라벨
    relation_type: RelationType
    weight: float = 1.0


class GraphData(BaseModel):
    """프론트엔드 전송용 그래프 데이터."""
    nodes: list[GraphNode] = Field(default_factory=list)
    edges: list[GraphEdge] = Field(default_factory=list)
    stats: dict = Field(default_factory=dict)  # 엔티티/관계 통계


# ── API 요청/응답 ──────────────────────────────────────────────────────────────


class ExtractionRequest(BaseModel):
    """엔티티 추출 요청."""
    document_id: Optional[str] = None   # 특정 문서
    source: Optional[str] = None         # 특정 파일명
    workspace_id: Optional[str] = None  # 워크스페이스 범위
    entity_types: list[EntityType] = Field(default_factory=list)  # 필터
    max_entities_per_chunk: int = 10


class EntitySearchRequest(BaseModel):
    """엔티티 검색 요청."""
    query: str                           # 검색어
    entity_types: list[EntityType] = Field(default_factory=list)
    limit: int = 20


class EntityDetail(BaseModel):
    """엔티티 상세 (관련 엔티티 + 문서 포함)."""
    entity: Entity
    related_entities: list[tuple[Entity, Relation]] = Field(default_factory=list)
    related_documents: list[dict] = Field(default_factory=list)  # [{id, name, chunks}]