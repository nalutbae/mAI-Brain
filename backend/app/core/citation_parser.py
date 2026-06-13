"""mAI-Brain AI 챗봇 — 인용 파서 유틸리티

LLM 답변 텍스트에서 [[N]] 형식의 인용 마커를 추출하고,
SearchHit 리스트와 매핑하여 Citation 객체 리스트를 생성합니다.

사용법:
    from app.core.citation_parser import parse_citations

    citations = parse_citations(answer, search_hits)
    # → [Citation(index=1, source="doc.pdf", page=5, text="...", score=0.87), ...]
"""

from __future__ import annotations

import re
from typing import Optional

from app.models.chat import Citation, SearchHit

# [[1]], [[2]], [[12]] 등 인용 마커 패턴
CITATION_PATTERN = re.compile(r"\[\[(\d+)\]\]")


def parse_citations(
    answer: str,
    hits: list[SearchHit],
    max_text_length: int = 300,
) -> list[Citation]:
    """답변 텍스트에서 [[N]] 마커를 추출하여 SearchHit과 매핑.

    Args:
        answer: LLM 답변 텍스트
        hits: 검색 결과 리스트 (인덱스 1부터 매핑)
        max_text_length: 인용 텍스트 최대 길이 (자르기)

    Returns:
        Citation 리스트 — 중복 제거됨, 인덱스 순서 정렬
    """
    # 답변에서 [[N]] 마커 모두 추출
    matches = CITATION_PATTERN.findall(answer)
    if not matches:
        return []

    # 중복 제거 및 정수 변환
    seen: set[int] = set()
    indices: list[int] = []
    for m in matches:
        idx = int(m)
        if idx not in seen:
            seen.add(idx)
            indices.append(idx)

    # SearchHit과 매핑 (인덱스는 1부터, hits 리스트는 0부터)
    citations: list[Citation] = []
    for idx in indices:
        hit_index = idx - 1  # 1-based → 0-based
        if 0 <= hit_index < len(hits):
            hit = hits[hit_index]
            citations.append(Citation(
                index=idx,
                source=hit.source,
                page=hit.page,
                text=hit.text[:max_text_length],
                score=hit.score,
            ))

    return citations


def strip_citation_markers(text: str) -> str:
    """답변 텍스트에서 [[N]] 마커를 제거한 순수 텍스트 반환.

    프론트엔드에서는 마커를 제거하지 않고 그대로 렌더링하므로,
    이 함수는 주로 디버깅/로깅 용도로 사용됩니다.
    """
    return CITATION_PATTERN.sub("", text)


def get_cited_indices(answer: str) -> list[int]:
    """답변에서 인용된 인덱스 번호만 추출 (중복 제거, 정렬)."""
    matches = CITATION_PATTERN.findall(answer)
    if not matches:
        return []
    seen: set[int] = set()
    result: list[int] = []
    for m in sorted(set(matches), key=lambda x: int(x)):
        idx = int(m)
        if idx not in seen:
            seen.add(idx)
            result.append(idx)
    return result