"""지식 그래프 엔티티/관계 추출 모듈

LLM을 사용하여 문서 청크에서 엔티티와 관계를 추출합니다.
한국어 문서(법률, 논문, 뉴스)에 최적화된 프롬프트를 사용합니다.

사용 흐름:
  1. 문서 인덱싱 후 extract_from_document() 호출
  2. 각 청크에서 엔티티/관계 추출 (LLM)
  3. 동일 엔티티 병합 (이름+타입 기준)
  4. Qdrant KG 컬렉션에 저장
"""

from __future__ import annotations

import json
import logging
import re
from typing import Optional

from app.core.llm import LLMClient, get_llm_client
from app.models.knowledge_graph import (
    Entity,
    EntityType,
    ExtractionResult,
    ExtractionStatus,
    Relation,
    RelationType,
)

logger = logging.getLogger(__name__)

# ── 한국어 최적화 엔티티 추출 프롬프트 ────────────────────────────────────────

SYSTEM_PROMPT = """당신은 한국어 문서에서 엔티티와 관계를 추출하는 전문가입니다.

다음 텍스트에서 모든 중요한 엔티티(명명 개체)와 그들 간의 관계를 추출하세요.

## 엔티티 타입
- person: 인물 (이름, 직위 포함)
- organization: 조직, 기관, 기업, 부서
- law_article: 법률 조문 (예: "헌법 제21조", "민법 제750조")
- concept: 개념, 용어, 원칙, 이론
- event: 사건, 사고, 회의, 선거
- location: 장소, 지역
- document: 문서, 보고서, 논문, 기사
- technology: 기술, 제품, 시스템
- role: 직위, 역할, 직책

## 관계 타입
- cites: 인용 (법률 조문 간, 논문 간)
- belongs_to: 소속 (인물→조직)
- influences: 영향, 영향력
- mentions: 언급
- defines: 정의
- contradicts: 모순, 충돌
- supports: 지지, 근거
- related_to: 일반적 관계
- synonym_of: 동의어
- part_of: 부분-전체
- precedes: 선후관계
- occurred_at: 사건-장소

## 출력 형식
반드시 아래 JSON 형식으로만 응답하세요. 다른 텍스트는 절대 포함하지 마세요.

```json
{
  "entities": [
    {
      "name": "엔티티 이름",
      "type": "person|organization|law_article|concept|event|location|document|technology|role",
      "description": "한 줄 설명",
      "properties": {}
    }
  ],
  "relations": [
    {
      "source": "출발 엔티티 이름",
      "target": "도착 엔티티 이름",
      "type": "cites|belongs_to|influences|mentions|defines|contradicts|supports|related_to|synonym_of|part_of|precedes|occurred_at",
      "description": "관계 설명",
      "weight": 0.0~1.0
    }
  ]
}
```

## 규칙
1. 엔티티 이름은 원문 그대로 사용 (번역하지 않음)
2. 법률 조문은 "법률명 제X조" 형식으로 (예: "개인정보보호법 제15조")
3. 관계는 반드시 위에 나열된 엔티티 간에만 성립
4. weight는 관계의 강도/확실성을 나타냄 (명시적 언급=1.0, 추론=0.5~0.8)
5. 중복 엔티티는 제거
6. 추출할 엔티티가 없으면 빈 배열 반환"""

USER_PROMPT_TEMPLATE = """다음 텍스트에서 엔티티와 관계를 추출하세요:

---
{text}
---

JSON 형식으로만 응답하세요."""

# ── 엔티티 이름 정규화 ──────────────────────────────────────────────────────────

# 법률 조문 정규화 패턴
_LAW_PATTERNS = [
    (re.compile(r"(\w+법)\s*제(\d+)조(?:의\s*(\d+))?\s*제(\d+)항"),  # OO법 제X조의Y제Z항
     lambda m: f"{m.group(1)} 제{m.group(2)}조의{m.group(3)} 제{m.group(4)}항"),
    (re.compile(r"(\w+법)\s*제(\d+)조(?:의\s*(\d+))?"),  # OO법 제X조의Y
     lambda m: f"{m.group(1)} 제{m.group(2)}조" + (f"의{m.group(3)}" if m.group(3) else "")),
]


def normalize_entity_name(name: str, entity_type: EntityType) -> str:
    """엔티티 이름 정규화 (동의어 병합을 위해)."""
    name = name.strip()
    if entity_type == EntityType.LAW_ARTICLE:
        for pattern, replacer in _LAW_PATTERNS:
            if pattern.search(name):
                return replacer(pattern.search(name))
    return name


# ── LLM 응답 파싱 ─────────────────────────────────────────────────────────────

def _parse_llm_response(response_text: str) -> dict:
    """LLM 응답에서 JSON 추출.

    응답에 마크다운 코드 펜스가 포함될 수 있으므로 처리.
    """
    # ```json ... ``` 블록 추출
    json_match = re.search(r"```(?:json)?\s*\n?(.*?)```", response_text, re.DOTALL)
    if json_match:
        text = json_match.group(1).strip()
    else:
        text = response_text.strip()

    # 중괄호로 감싸진 JSON 찾기
    brace_match = re.search(r"\{.*\}", text, re.DOTALL)
    if brace_match:
        text = brace_match.group(0)

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        logger.warning("KG 추출: JSON 파싱 실패 — 응답: %s...", response_text[:200])
        return {"entities": [], "relations": []}


# ── 엔티티 타입 매핑 ────────────────────────────────────────────────────────────

_ENTITY_TYPE_MAP = {t.value: t for t in EntityType}
_RELATION_TYPE_MAP = {t.value: t for t in RelationType}


def _map_entity_type(raw_type: str) -> EntityType:
    """LLM 응답의 엔티티 타입을 EntityType으로 매핑."""
    return _ENTITY_TYPE_MAP.get(raw_type.lower().strip(), EntityType.CONCEPT)


def _map_relation_type(raw_type: str) -> RelationType:
    """LLM 응답의 관계 타입을 RelationType으로 매핑."""
    return _RELATION_TYPE_MAP.get(raw_type.lower().strip(), RelationType.RELATED_TO)


# ── 핵심 추출 로직 ─────────────────────────────────────────────────────────────


class KGExtractor:
    """지식 그래프 엔티티/관계 추출기."""

    def __init__(self, llm_client: Optional[LLMClient] = None):
        self.llm = llm_client or get_llm_client()

    def extract_from_chunk(
        self,
        text: str,
        document_id: str,
        chunk_id: str,
        max_entities: int = 10,
    ) -> tuple[list[Entity], list[Relation]]:
        """단일 청크에서 엔티티와 관계를 추출합니다.

        Returns:
            (entities, relations) 튜플
        """
        # 텍스트가 너무 짧으면 스킵
        if len(text.strip()) < 50:
            return [], []

        # LLM 호출
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": USER_PROMPT_TEMPLATE.format(text=text[:3000])},
        ]

        try:
            response = self._call_llm(messages)
        except Exception as e:
            logger.error("KG 추출 LLM 호출 실패: %s", e)
            return [], []

        # 응답 파싱
        parsed = _parse_llm_response(response)

        # Entity 객체 생성
        entities: list[Entity] = []
        for raw_ent in parsed.get("entities", [])[:max_entities]:
            try:
                name = raw_ent.get("name", "").strip()
                if not name:
                    continue
                raw_type = raw_ent.get("type", "concept")
                entity_type = _map_entity_type(raw_type)
                normalized = normalize_entity_name(name, entity_type)

                entity = Entity(
                    name=normalized,
                    type=entity_type,
                    description=raw_ent.get("description"),
                    properties=raw_ent.get("properties", {}),
                    source_document_ids=[document_id],
                    source_chunks=[chunk_id],
                    mention_count=1,
                )
                entities.append(entity)
            except Exception as e:
                logger.warning("엔티티 생성 실패: %s — %s", raw_ent, e)
                continue

        # Relation 객체 생성 (엔티티 이름으로 매핑)
        entity_names = {e.name for e in entities}
        relations: list[Relation] = []
        for raw_rel in parsed.get("relations", []):
            try:
                source_name = raw_rel.get("source", "").strip()
                target_name = raw_rel.get("target", "").strip()
                if not source_name or not target_name:
                    continue
                # 소스/타겟이 추출된 엔티티에 없으면 유연하게 처리
                # (LLM이 엔티티를 놓친 경우 자동 추가하지는 않음)
                source_id = ""
                target_id = ""
                for e in entities:
                    if e.name == source_name:
                        source_id = e.id
                    if e.name == target_name:
                        target_id = e.id

                if not source_id or not target_id:
                    continue

                relation = Relation(
                    source_entity_id=source_id,
                    target_entity_id=target_id,
                    relation_type=_map_relation_type(raw_rel.get("type", "related_to")),
                    description=raw_rel.get("description"),
                    weight=float(raw_rel.get("weight", 1.0)),
                    source_document_ids=[document_id],
                    evidence_text=text[:200],
                )
                relations.append(relation)
            except Exception as e:
                logger.warning("관계 생성 실패: %s — %s", raw_rel, e)
                continue

        return entities, relations

    def extract_from_document(
        self,
        chunks: list[dict],
        document_id: str,
        document_name: str,
    ) -> ExtractionResult:
        """문서의 모든 청크에서 엔티티/관계를 추출하고 병합합니다.

        Args:
            chunks: [{id, text, metadata}] 형식의 청크 리스트
            document_id: 문서 ID
            document_name: 문서 파일명

        Returns:
            ExtractionResult (병합된 엔티티/관계 포함)
        """
        all_entities: list[Entity] = []
        all_relations: list[Relation] = []

        for chunk in chunks:
            chunk_id = chunk.get("id", chunk.get("chunk_index", ""))
            text = chunk.get("text", "")

            entities, relations = self.extract_from_chunk(
                text=text,
                document_id=document_id,
                chunk_id=str(chunk_id),
            )

            all_entities.extend(entities)
            all_relations.extend(relations)

        # 동일 엔티티 병합 (이름+타입 기준)
        merged_entities = self._merge_entities(all_entities)

        # 관계의 엔티티 ID 재매핑 (병합 후 ID 변경 대응)
        id_map = self._build_id_map(all_entities, merged_entities)
        merged_relations = self._remap_relations(all_relations, id_map)

        # 중복 관계 제거
        unique_relations = self._deduplicate_relations(merged_relations)

        return ExtractionResult(
            document_id=document_id,
            document_name=document_name,
            entities=merged_entities,
            relations=unique_relations,
            status=ExtractionStatus.COMPLETED,
        )

    def _call_llm(self, messages: list[dict]) -> str:
        """LLM 프로바이더 체인을 통해 응답을 가져옵니다."""
        from app.models.provider import ProviderSettingsStore

        store = ProviderSettingsStore.get()
        active_provider = store.get_active_llm_provider()
        if not active_provider:
            raise RuntimeError("활성 LLM 프로바이더가 없습니다.")

        result = self.llm._call_provider(active_provider, messages, max_tokens=2048)
        if result is None:
            raise RuntimeError("LLM 응답이 없습니다.")
        return result

    @staticmethod
    def _merge_entities(entities: list[Entity]) -> list[Entity]:
        """동일 이름+타입의 엔티티를 병합합니다."""
        entity_map: dict[str, Entity] = {}
        for entity in entities:
            key = f"{entity.type.value}::{entity.name}"
            if key in entity_map:
                entity_map[key] = entity_map[key].merge(entity)
            else:
                entity_map[key] = entity
        return list(entity_map.values())

    @staticmethod
    def _build_id_map(
        old_entities: list[Entity],
        merged_entities: list[Entity],
    ) -> dict[str, str]:
        """병합 전→후 ID 매핑을 생성합니다."""
        # 병합된 엔티티에서 이름→새ID 맵 구성
        name_to_new_id: dict[str, str] = {}
        for e in merged_entities:
            key = f"{e.type.value}::{e.name}"
            name_to_new_id[key] = e.id

        # 이전 ID → 새 ID 매핑
        id_map: dict[str, str] = {}
        for old_e in old_entities:
            key = f"{old_e.type.value}::{old_e.name}"
            if key in name_to_new_id:
                id_map[old_e.id] = name_to_new_id[key]

        return id_map

    @staticmethod
    def _remap_relations(
        relations: list[Relation],
        id_map: dict[str, str],
    ) -> list[Relation]:
        """관계의 엔티티 ID를 병합 후 ID로 재매핑합니다."""
        remapped = []
        for rel in relations:
            new_source = id_map.get(rel.source_entity_id, rel.source_entity_id)
            new_target = id_map.get(rel.target_entity_id, rel.target_entity_id)
            # 자기 참조 관계 제외
            if new_source == new_target:
                continue
            remapped.append(Relation(
                id=rel.id,
                source_entity_id=new_source,
                target_entity_id=new_target,
                relation_type=rel.relation_type,
                description=rel.description,
                weight=rel.weight,
                source_document_ids=rel.source_document_ids,
                evidence_text=rel.evidence_text,
                created_at=rel.created_at,
            ))
        return remapped

    @staticmethod
    def _deduplicate_relations(relations: list[Relation]) -> list[Relation]:
        """동일 소스-타겟-타입의 중복 관계를 제거하고 가중치를 누적합니다."""
        key_map: dict[str, Relation] = {}
        for rel in relations:
            key = f"{rel.source_entity_id}::{rel.relation_type.value}::{rel.target_entity_id}"
            if key in key_map:
                existing = key_map[key]
                # 가중치 평균
                existing.weight = (existing.weight + rel.weight) / 2
                # 문서 ID 병합
                existing.source_document_ids = list(
                    set(existing.source_document_ids + rel.source_document_ids)
                )
                # 설명 보강
                if rel.description and not existing.description:
                    existing.description = rel.description
            else:
                key_map[key] = rel
        return list(key_map.values())