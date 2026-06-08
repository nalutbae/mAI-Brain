"""mAI-Brain — RAG 검색 품질 메트릭 (규칙 기반)

LLM 호출 없이 계산 가능한 검색 품질 지표:
- Precision@k: 검색 결과 중 기대 출처의 비율
- Recall@k: 기대 출처 중 검색 결과에 포함된 비율
- MRR: Mean Reciprocal Rank
"""

from __future__ import annotations


def precision_at_k(retrieved_sources: list[str], expected_sources: list[str]) -> float:
    """Precision@k 계산.

    검색 결과 중 기대 출처가 얼마나 포함되어 있는지 비율.

    Args:
        retrieved_sources: 검색 결과 출처 파일명 리스트
        expected_sources: 기대 출처 파일명 리스트

    Returns:
        0.0~1.0, 높을수록 정밀
    """
    if not retrieved_sources:
        return 0.0
    expected_set = set(s.lower().strip() for s in expected_sources)
    if not expected_set:
        return 0.0
    hits = sum(1 for s in retrieved_sources if s.lower().strip() in expected_set)
    return hits / len(retrieved_sources)


def recall_at_k(retrieved_sources: list[str], expected_sources: list[str]) -> float:
    """Recall@k 계산.

    기대 출처 중 검색 결과에 포함된 비율.

    Args:
        retrieved_sources: 검색 결과 출처 파일명 리스트
        expected_sources: 기대 출처 파일명 리스트

    Returns:
        0.0~1.0, 높을수록 재현율 높음
    """
    if not expected_sources:
        return 0.0
    expected_set = set(s.lower().strip() for s in expected_sources)
    retrieved_set = set(s.lower().strip() for s in retrieved_sources)
    hits = expected_set & retrieved_set
    return len(hits) / len(expected_set)


def mean_reciprocal_rank(retrieved_sources: list[str], expected_sources: list[str]) -> float:
    """MRR (Mean Reciprocal Rank) 계산.

    첫 번째 관련 출처의 순위 역수. 검색 결과 정렬 품질 평가.

    Args:
        retrieved_sources: 검색 결과 출처 파일명 리스트 (순위 순)
        expected_sources: 기대 출처 파일명 리스트

    Returns:
        0.0~1.0, 1.0이면 첫 번째 결과가 정답
    """
    if not retrieved_sources or not expected_sources:
        return 0.0
    expected_set = set(s.lower().strip() for s in expected_sources)
    for i, source in enumerate(retrieved_sources, 1):
        if source.lower().strip() in expected_set:
            return 1.0 / i
    return 0.0


def extract_score(text: str) -> float:
    """LLM 응답에서 0~1 사이의 점수를 추출합니다."""
    import re

    text = text.strip()
    match = re.search(r'(?:0\.\d+|1\.0+|[01])(?:\b|$)', text)
    if match:
        try:
            score = float(match.group())
            return max(0.0, min(1.0, score))
        except ValueError:
            pass
    return 0.0