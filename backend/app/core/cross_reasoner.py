"""mAI-Brain — 교차 문서 추론(Cross-Document Reasoning) 엔진

문서 간 교차 검증, 모순 탐지, 일치 분석을 수행합니다.

핵심 파이프라인:
1. 원본 질문 → 다중 하위 질문 자동 분해
2. 각 하위 질문 독립 검색 → 결과 간 모순/일치 분석
3. 문서 간 충돌 탐지 및 보고서 생성
4. 종합 분석 (synthesis) LLM 생성

설계 원칙:
- 기존 search.py의 hybrid_search, llm.py의 LLMClient 재사용
- 단일 책임: 분해 → 검색 → 분석 → 종합의 각 단계 분리
- LLM 프롬프트: 한국어 응답, 원문 용어 유지, 출처 명시
"""

from __future__ import annotations

import json
import logging
import re
from typing import Optional

from app.config import ChatMode, ReasoningStrength, get_settings
from app.core.llm import LLMClient, get_llm_client
from app.core.search import hybrid_search
from app.models.chat import SearchHit
from app.models.cross_reasoning import (
    ConflictType,
    CrossReasoningReport,
    CrossReasoningRequest,
    CrossReasoningStatus,
    DocumentAgreement,
    DocumentConflict,
    SubQuery,
    SubQueryResult,
)

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# 하위 질문 자동 분해 프롬프트
# --------------------------------------------------------------------------- #

SUBQUERY_GENERATION_PROMPT = """\
당신은 복잡한 질문을 분석하여 하위 질문으로 분해하는 전문가입니다.
원본 질문을 분석할 때 서로 다른 문서들이 다루는 측면을 식별하세요.

[원본 질문]
{query}

다음 규칙을 따르세요:
1. 원본 질문을 2~5개의 하위 질문으로 분해하세요.
2. 각 하위 질문은 서로 다른 문서에서 다룰 수 있는 측면을 포착해야 합니다.
3. 하위 질문들은 원본 질문의 모든 측면을 포괄해야 합니다.
4. 각 하위 질문에 aspect(측면)를 부여하세요: fact, cause, effect, comparison, timeline, definition 중 선택.

반드시 아래 JSON 형식으로만 출력하세요:
```json
{{
  "sub_queries": [
    {{"query": "하위 질문 1", "aspect": "fact"}},
    {{"query": "하위 질문 2", "aspect": "comparison"}},
    ...
  ]
}}
```"""


# --------------------------------------------------------------------------- #
# 모순 탐지 프롬프트
# --------------------------------------------------------------------------- #

CONFLICT_DETECTION_PROMPT = """\
당신은 여러 문서 간 모순과 일치를 탐지하는 전문가입니다.

[원본 질문]
{query}

[하위 질문별 검색 결과]
{sub_query_results}

다음을 분석하세요:
1. 서로 다른 문서가 같은 사실에 대해 상이한 주장을 하는 경우 (직접적 모순)
2. 시기적 차이로 인해 주장이 달라진 경우 (시간적 충돌)
3. 부분적으로 불일치하는 경우 (부분적 불일치)
4. 한 문서에만 근거가 있는 경우 (근거 차이)
5. 여러 문서가 같은 주장을 뒷받침하는 경우 (일치/상호 보완)

반드시 아래 JSON 형식으로만 출력하세요:
```json
{{
  "conflicts": [
    {{
      "conflict_type": "direct_contradiction|temporal_conflict|partial_disagreement|evidence_gap",
      "description": "모순 내용 설명",
      "document_a": "문서 A 파일명",
      "document_b": "문서 B 파일명",
      "claim_a": "문서 A의 주장",
      "claim_b": "문서 B의 주장",
      "severity": "low|medium|high",
      "resolution_hint": "모순 해소 힌트 (선택)"
    }}
  ],
  "agreements": [
    {{
      "description": "일치 내용 설명",
      "documents": ["문서1 파일명", "문서2 파일명"],
      "theme": "공통 주제",
      "strength": "weak|moderate|strong"
    }}
  ]
}}
```"""


# --------------------------------------------------------------------------- #
# 종합 분석 프롬프트
# --------------------------------------------------------------------------- #

SYNTHESIS_PROMPT = """\
당신은 여러 문서의 정보를 종합 분석하는 전문가입니다.

[원본 질문]
{query}

[하위 질문별 요약]
{summaries}

[발견된 모순]
{conflicts}

[발견된 일치]
{agreements}

다음 구조로 종합 분석 보고서를 작성하세요:

## 1. 문서 분석 요약
각 문서의 핵심 주장을 1-2문장으로 제시하세요.

## 2. 문서 간 연결점
- 서로 다른 문서가 같은 주제를 어떻게 다루는가?
- 시간적 선후관계가 있는가? (원인 → 결과)
- 한 문서의 주장이 다른 문서의 사례/증거로 뒷받침되는가?

## 3. 모순 및 불일치
발견된 모순을 상세히 설명하고 가능한 해석을 제시하세요.

## 4. 종합 결론
원본 질문에 대한 최종 답변을 제시하세요.

규칙:
- 반드시 한국어로 답변하라.
- 원문 용어를 그대로 인용하라.
- 각 주장에 출처를 명시하라: [파일명, p.페이지]
- 추론의 강도를 표시하라: [강한 추론], [중간 추론], [약한 추론]
- 추론할 수 없는 내용은 명시하라."""


# --------------------------------------------------------------------------- #
# 교차 문서 추론 엔진
# --------------------------------------------------------------------------- #

class CrossReasoner:
    """교차 문서 추론 엔진.

    파이프라인:
    1. decompose_query() — 원본 질문 → 다중 하위 질문
    2. search_sub_queries() — 각 하위 질문 독립 검색
    3. detect_conflicts() — 검색 결과 간 모순/일치 탐지
    4. synthesize() — 종합 분석 보고서 생성

    전체 analyze() 메서드가 위 단계를 순차 실행합니다.
    """

    def __init__(self) -> None:
        self._llm: Optional[LLMClient] = None

    @property
    def llm(self) -> LLMClient:
        """LLM 클라이언트 지연 초기화."""
        if self._llm is None:
            self._llm = get_llm_client()
        return self._llm

    def analyze(self, request: CrossReasoningRequest) -> CrossReasoningReport:
        """교차 문서 추론 전체 파이프라인 실행.

        Args:
            request: 교차 추론 요청

        Returns:
            CrossReasoningReport: 전체 분석 보고서
        """
        report = CrossReasoningReport(
            original_query=request.query,
            mode=request.mode,
            status=CrossReasoningStatus.ANALYZING,
        )

        try:
            # 1단계: 질문 분해
            sub_queries = self.decompose_query(
                query=request.query,
                manual_sub_queries=request.sub_queries,
            )
            report.sub_queries = sub_queries
            logger.info("질문 분해 완료: %d개 하위 질문", len(sub_queries))

            # 2단계: 각 하위 질문 검색
            sub_results = self.search_sub_queries(
                sub_queries=sub_queries,
                mode=request.mode,
            )
            report.sub_query_results = sub_results
            logger.info("하위 질문 검색 완료: %d개 결과", len(sub_results))

            # 3단계: 모순/일치 탐지
            conflicts, agreements = self.detect_conflicts(
                query=request.query,
                sub_results=sub_results,
            )
            report.conflicts = conflicts
            report.agreements = agreements
            logger.info(
                "모순 탐지 완료: %d개 모순, %d개 일치",
                len(conflicts), len(agreements),
            )

            # 4단계: 종합 분석
            strength = None
            if request.reasoning_strength:
                strength = ReasoningStrength(request.reasoning_strength)

            synthesis, confidence = self.synthesize(
                query=request.query,
                sub_results=sub_results,
                conflicts=conflicts,
                agreements=agreements,
                mode=request.mode,
                reasoning_strength=strength,
            )
            report.synthesis = synthesis
            report.confidence = confidence

            report.status = CrossReasoningStatus.COMPLETED
            logger.info("교차 추론 완료: 신뢰도 %.2f", confidence)

        except Exception as exc:
            logger.error("교차 추론 오류: %s", exc, exc_info=True)
            report.status = CrossReasoningStatus.FAILED
            report.synthesis = f"교차 추론 분석 중 오류가 발생했습니다: {exc}"

        return report

    # ------------------------------------------------------------------- #
    # 1단계: 질문 분해
    # ------------------------------------------------------------------- #

    def decompose_query(
        self,
        query: str,
        manual_sub_queries: Optional[list[str]] = None,
    ) -> list[SubQuery]:
        """원본 질문을 다중 하위 질문으로 분해.

        Args:
            query: 원본 질문
            manual_sub_queries: 수동 지정 하위 질문 (없으면 LLM 자동 생성)

        Returns:
            분해된 하위 질문 리스트
        """
        if manual_sub_queries:
            return [
                SubQuery(
                    query=sq,
                    aspect="manual",
                    order=i,
                )
                for i, sq in enumerate(manual_sub_queries)
            ]

        # LLM으로 하위 질문 자동 생성
        prompt = SUBQUERY_GENERATION_PROMPT.format(query=query)

        try:
            response = self.llm.generate_answer(
                query=prompt,
                contexts=[],
                mode=ChatMode.FACT,
            )
            return self._parse_sub_queries(response)
        except Exception as exc:
            logger.warning("질문 분해 LLM 호출 실패, 폴백: %s", exc)
            # 폴백: 원본 질문 그대로 사용
            return [SubQuery(query=query, aspect="general", order=0)]

    @staticmethod
    def _parse_sub_queries(response: str) -> list[SubQuery]:
        """LLM 응답에서 하위 질문 파싱."""
        # JSON 블록 추출
        json_match = re.search(r'```json\s*(.*?)\s*```', response, re.DOTALL)
        if json_match:
            json_str = json_match.group(1)
        else:
            # JSON 블록 없으면 전체에서 JSON 찾기
            json_match = re.search(r'\{[^{}]*"sub_queries"[^{}]*\}', response, re.DOTALL)
            json_str = json_match.group(0) if json_match else ""

        if not json_str:
            logger.warning("하위 질문 JSON 파싱 실패, 폴백 사용")
            return [SubQuery(query=response[:200], aspect="general", order=0)]

        try:
            data = json.loads(json_str)
            sub_queries_data = data.get("sub_queries", [])
            return [
                SubQuery(
                    query=sq.get("query", ""),
                    aspect=sq.get("aspect", "general"),
                    order=i,
                )
                for i, sq in enumerate(sub_queries_data)
                if sq.get("query", "").strip()
            ]
        except (json.JSONDecodeError, KeyError) as exc:
            logger.warning("하위 질문 JSON 파싱 오류: %s", exc)
            return [SubQuery(query=response[:200], aspect="general", order=0)]

    # ------------------------------------------------------------------- #
    # 2단계: 하위 질문 검색
    # ------------------------------------------------------------------- #

    def search_sub_queries(
        self,
        sub_queries: list[SubQuery],
        mode: ChatMode = ChatMode.REASONING,
    ) -> list[SubQueryResult]:
        """각 하위 질문에 대해 독립 검색 수행.

        Args:
            sub_queries: 분해된 하위 질문 리스트
            mode: 채팅 모드 (top-k 결정)

        Returns:
            각 하위 질문의 검색 결과
        """
        results: list[SubQueryResult] = []

        for sub_query in sub_queries:
            try:
                search_result = hybrid_search(
                    query=sub_query.query,
                    mode=mode,
                )
                # SearchHit → dict 변환 (JSON 직렬화 호환성)
                hits_dicts = [
                    {
                        "text": h.text,
                        "source": h.source,
                        "score": h.score,
                        "chunk_index": h.chunk_index,
                        "page": h.page,
                    }
                    for h in search_result.hits
                ]
                results.append(SubQueryResult(
                    sub_query=sub_query,
                    hits=hits_dicts,
                    summary="",
                ))
            except Exception as exc:
                logger.error("하위 질문 검색 실패 (%s): %s", sub_query.query[:50], exc)
                results.append(SubQueryResult(
                    sub_query=sub_query,
                    hits=[],
                    summary=f"검색 오류: {exc}",
                ))

        return results

    # ------------------------------------------------------------------- #
    # 3단계: 모순/일치 탐지
    # ------------------------------------------------------------------- #

    def detect_conflicts(
        self,
        query: str,
        sub_results: list[SubQueryResult],
    ) -> tuple[list[DocumentConflict], list[DocumentAgreement]]:
        """검색 결과 간 모순과 일치를 탐지.

        Args:
            query: 원본 질문
            sub_results: 하위 질문 검색 결과

        Returns:
            (모순 리스트, 일치 리스트)
        """
        # 검색 결과가 충분하지 않으면 빈 결과 반환
        total_hits = sum(len(r.hits) for r in sub_results)
        if total_hits < 2:
            logger.info("검색 결과 부족 (%d hits), 모순 탐지 스킵", total_hits)
            return [], []

        # 검색 결과 텍스트 구성
        sub_results_text = self._format_sub_results(sub_results)
        prompt = CONFLICT_DETECTION_PROMPT.format(
            query=query,
            sub_query_results=sub_results_text,
        )

        try:
            response = self.llm.generate_answer(
                query=prompt,
                contexts=[],
                mode=ChatMode.FACT,
            )
            return self._parse_conflicts(response)
        except Exception as exc:
            logger.error("모순 탐지 LLM 호출 실패: %s", exc)
            return [], []

    def _format_sub_results(self, sub_results: list[SubQueryResult]) -> str:
        """하위 질문 검색 결과를 텍스트로 포맷팅."""
        parts = []
        for i, result in enumerate(sub_results, 1):
            parts.append(f"### 하위 질문 {i}: {result.sub_query.query}")
            parts.append(f"(측면: {result.sub_query.aspect})")
            if result.hits:
                for j, hit in enumerate(result.hits[:5], 1):  # 상위 5개만
                    source_info = hit.get("source", "알 수 없음")
                    if hit.get("page") is not None:
                        source_info += f", p.{hit['page']}"
                    parts.append(f"  [{j}] {source_info}")
                    parts.append(f"      {hit.get('text', '')[:300]}")
            else:
                parts.append("  (검색 결과 없음)")
            parts.append("")
        return "\n".join(parts)

    @staticmethod
    def _parse_conflicts(
        response: str,
    ) -> tuple[list[DocumentConflict], list[DocumentAgreement]]:
        """LLM 응답에서 모순/일치 파싱."""
        # JSON 블록 추출
        json_match = re.search(r'```json\s*(.*?)\s*```', response, re.DOTALL)
        if json_match:
            json_str = json_match.group(1)
        else:
            # 전체에서 JSON 찾기 — 가장 바깥 중괄호
            start = response.find("{")
            end = response.rfind("}") + 1
            json_str = response[start:end] if start >= 0 and end > start else ""

        if not json_str:
            logger.warning("모순/일치 JSON 파싱 실패")
            return [], []

        try:
            data = json.loads(json_str)
        except json.JSONDecodeError:
            logger.warning("모순/일치 JSON 디코딩 실패")
            return [], []

        conflicts = []
        for cd in data.get("conflicts", []):
            try:
                conflict_type = ConflictType(
                    cd.get("conflict_type", "partial_disagreement")
                )
            except ValueError:
                conflict_type = ConflictType.PARTIAL_DISAGREEMENT

            conflicts.append(DocumentConflict(
                conflict_type=conflict_type,
                description=cd.get("description", ""),
                document_a=cd.get("document_a", "알 수 없음"),
                document_b=cd.get("document_b", "알 수 없음"),
                claim_a=cd.get("claim_a", ""),
                claim_b=cd.get("claim_b", ""),
                severity=cd.get("severity", "medium"),
                resolution_hint=cd.get("resolution_hint"),
            ))

        agreements = []
        for ad in data.get("agreements", []):
            agreements.append(DocumentAgreement(
                description=ad.get("description", ""),
                documents=ad.get("documents", []),
                theme=ad.get("theme", ""),
                strength=ad.get("strength", "moderate"),
            ))

        return conflicts, agreements

    # ------------------------------------------------------------------- #
    # 4단계: 종합 분석
    # ------------------------------------------------------------------- #

    def synthesize(
        self,
        query: str,
        sub_results: list[SubQueryResult],
        conflicts: list[DocumentConflict],
        agreements: list[DocumentAgreement],
        mode: ChatMode = ChatMode.REASONING,
        reasoning_strength: Optional[ReasoningStrength] = None,
    ) -> tuple[str, float]:
        """종합 분석 보고서 생성.

        Args:
            query: 원본 질문
            sub_results: 하위 질문 검색 결과
            conflicts: 발견된 모순
            agreements: 발견된 일치
            mode: 채팅 모드
            reasoning_strength: 추론 강도 필터

        Returns:
            (종합 분석 텍스트, 신뢰도 0~1)
        """
        # 하위 질문별 요약
        summaries = []
        for i, result in enumerate(sub_results, 1):
            summary_text = f"**하위 질문 {i}** ({result.sub_query.aspect}): {result.sub_query.query}\n"
            if result.summary:
                summary_text += f"요약: {result.summary}\n"
            elif result.hits:
                # 상위 3개 검색 결과 요약
                for j, hit in enumerate(result.hits[:3], 1):
                    src = hit.get("source", "알 수 없음")
                    page = hit.get("page")
                    src_ref = f"[{src}" + (f", p.{page}" if page else "") + "]"
                    summary_text += f"  - {src_ref}: {hit.get('text', '')[:200]}\n"
            summaries.append(summary_text)

        summaries_text = "\n".join(summaries) if summaries else "검색 결과 없음"

        conflicts_text = "발견된 모순 없음"
        if conflicts:
            conflict_items = []
            for c in conflicts:
                item = f"- [{c.conflict_type.value}] {c.description}\n"
                item += f"  문서 A({c.document_a}): {c.claim_a}\n"
                item += f"  문서 B({c.document_b}): {c.claim_b}\n"
                item += f"  심각도: {c.severity}"
                if c.resolution_hint:
                    item += f"\n  해소 힌트: {c.resolution_hint}"
                conflict_items.append(item)
            conflicts_text = "\n".join(conflict_items)

        agreements_text = "발견된 일치 없음"
        if agreements:
            agreement_items = []
            for a in agreements:
                item = f"- [{a.strength}] {a.description}\n"
                item += f"  문서: {', '.join(a.documents)}\n"
                item += f"  주제: {a.theme}"
                agreement_items.append(item)
            agreements_text = "\n".join(agreement_items)

        # 검색 결과를 SearchHit 리스트로 변환하여 LLM에 전달
        all_hits: list[SearchHit] = []
        for result in sub_results:
            for hit_dict in result.hits:
                all_hits.append(SearchHit(
                    text=hit_dict.get("text", ""),
                    source=hit_dict.get("source", "알 수 없음"),
                    score=hit_dict.get("score", 0.0),
                    chunk_index=hit_dict.get("chunk_index"),
                    page=hit_dict.get("page"),
                ))

        # 종합 분석 프롬프트 구성
        synthesis_prompt = SYNTHESIS_PROMPT.format(
            query=query,
            summaries=summaries_text,
            conflicts=conflicts_text,
            agreements=agreements_text,
        )

        try:
            # LLM 호출 시 검색 결과도 contexts로 전달
            answer = self.llm.generate_answer(
                query=synthesis_prompt,
                contexts=all_hits[:20],  # 상위 20개만 전달
                mode=mode,
                reasoning_strength=reasoning_strength,
            )

            # 신뢰도 계산
            confidence = self._compute_confidence(sub_results, conflicts, agreements)

            return answer, confidence

        except Exception as exc:
            logger.error("종합 분석 LLM 호출 실패: %s", exc)
            # 폴백: 검색 결과 기반 간단 요약
            fallback = self._generate_fallback_synthesis(
                query, sub_results, conflicts, agreements
            )
            confidence = 0.2  # 폴백은 낮은 신뢰도
            return fallback, confidence

    @staticmethod
    def _compute_confidence(
        sub_results: list[SubQueryResult],
        conflicts: list[DocumentConflict],
        agreements: list[DocumentAgreement],
    ) -> float:
        """추론 신뢰도 계산.

        신뢰도 요인:
        - 검색 결과의 충분성 (히트 수)
        - 일치하는 문서 수 (높을수록 신뢰)
        - 모순의 심각도 (높을수록 신뢰 하락)
        """
        # 검색 충분성: 평균 히트 수 (최대 10개 기준)
        avg_hits = sum(len(r.hits) for r in sub_results) / max(len(sub_results), 1)
        search_factor = min(avg_hits / 10.0, 1.0)

        # 일치 신뢰도: 강한 일치가 많을수록 높음
        strength_weights = {"strong": 1.0, "moderate": 0.6, "weak": 0.3}
        agreement_score = sum(
            strength_weights.get(a.strength, 0.5) for a in agreements
        )
        agreement_factor = min(agreement_score / 3.0, 1.0)

        # 모순 페널티: 심각한 모순이 많을수록 낮음
        severity_weights = {"high": 0.3, "medium": 0.6, "low": 0.9}
        conflict_score = sum(
            severity_weights.get(c.severity, 0.5) for c in conflicts
        )
        conflict_factor = conflict_score / max(len(conflicts), 1)

        # 가중 평균: 검색 30%, 일치 40%, 모순 30%
        confidence = (
            search_factor * 0.3
            + agreement_factor * 0.4
            + conflict_factor * 0.3
        )

        return round(min(max(confidence, 0.0), 1.0), 2)

    @staticmethod
    def _generate_fallback_synthesis(
        query: str,
        sub_results: list[SubQueryResult],
        conflicts: list[DocumentConflict],
        agreements: list[DocumentAgreement],
    ) -> str:
        """LLM 실패 시 폴백 종합 분석."""
        parts = [f"## 질문: {query}\n"]
        parts.append("### 검색 결과 요약\n")

        for i, result in enumerate(sub_results, 1):
            parts.append(f"**{i}. {result.sub_query.query}** ({result.sub_query.aspect})")
            if result.hits:
                for j, hit in enumerate(result.hits[:3], 1):
                    src = hit.get("source", "알 수 없음")
                    parts.append(f"  - [{src}]: {hit.get('text', '')[:150]}...")
            else:
                parts.append("  (검색 결과 없음)")

        if conflicts:
            parts.append(f"\n### 모순 ({len(conflicts)}건)")
            for c in conflicts:
                parts.append(
                    f"- {c.document_a} vs {c.document_b}: {c.description} "
                    f"[{c.severity}]"
                )

        if agreements:
            parts.append(f"\n### 일치 ({len(agreements)}건)")
            for a in agreements:
                parts.append(f"- {a.description} [{a.strength}]")

        parts.append("\n*(LLM 종합 분석 실패 — 검색 결과 기반 요약입니다)*")
        return "\n".join(parts)


# --------------------------------------------------------------------------- #
# 싱글톤
# --------------------------------------------------------------------------- #

_cross_reasoner: Optional[CrossReasoner] = None


def get_cross_reasoner() -> CrossReasoner:
    """CrossReasoner 싱글톤 인스턴스 반환."""
    global _cross_reasoner
    if _cross_reasoner is None:
        _cross_reasoner = CrossReasoner()
    return _cross_reasoner