"""mAI-Brain — 교차 문서 추론(Cross-Document Reasoning) 단위 테스트

순수 로직 테스트 (LLM/Qdrant 의존성 없이 실행 가능):
- 데이터 모델 검증 (Pydantic)
- CrossReasoner 정적 파싱 메서드 (_parse_sub_queries, _parse_conflicts)
- 신뢰도 계산 (_compute_confidence)
- 폴백 종합 분석 (_generate_fallback_synthesis)
- 검색 결과 포맷팅 (_format_sub_results)

전체 파이프라인 테스트는 무거운 의존성(PIL, FlagEmbedding 등)이 필요합니다.
HAS_CROSS_REASONER가 False인 환경에서는 파이프라인 테스트가 스킵됩니다.
"""

import json

import pytest

from app.models.cross_reasoning import (
    ConflictType,
    CrossReasoningReport,
    CrossReasoningRequest,
    CrossReasoningResponse,
    CrossReasoningStatus,
    DocumentAgreement,
    DocumentConflict,
    SubQuery,
    SubQueryResult,
)

# CrossReasoner는 무거운 의존성(PIL → ingestion chain)을 필요로 함
# 설치되지 않은 환경에서는 스킵
try:
    from app.core.cross_reasoner import CrossReasoner

    HAS_CROSS_REASONER = True
except ImportError:
    HAS_CROSS_REASONER = False

# 모델 테스트는 CrossReasoner 없이도 실행 가능.
# CrossReasoner가 필요한 클래스에는 개별적으로 skipif를 적용합니다.


# ========================================================================== #
# 데이터 모델 테스트 (의존성 없이 항상 실행)
# ========================================================================== #


class TestSubQuery:
    """SubQuery 모델 테스트."""

    def test_create_sub_query(self):
        """기본 하위 질문 생성."""
        sq = SubQuery(query="북한 경제 정책 변화", aspect="fact", order=0)
        assert sq.query == "북한 경제 정책 변화"
        assert sq.aspect == "fact"
        assert sq.order == 0
        assert sq.id.startswith("sq_")

    def test_sub_query_default_aspect(self):
        """aspect 기본값은 general."""
        sq = SubQuery(query="테스트 질문")
        assert sq.aspect == "general"

    def test_sub_query_default_order(self):
        """order 기본값은 0."""
        sq = SubQuery(query="테스트")
        assert sq.order == 0


class TestDocumentConflict:
    """DocumentConflict 모델 테스트."""

    def test_create_conflict(self):
        """모순 생성 기본."""
        conflict = DocumentConflict(
            conflict_type=ConflictType.DIRECT_CONTRADICTION,
            description="문서 A와 B가 상반된 주장",
            document_a="doc_A.pdf",
            document_b="doc_B.pdf",
            claim_a="X는 참이다",
            claim_b="X는 거짓이다",
            severity="high",
        )
        assert conflict.conflict_type == ConflictType.DIRECT_CONTRADICTION
        assert conflict.severity == "high"
        assert conflict.document_a == "doc_A.pdf"

    def test_conflict_types(self):
        """모순 유형 열거형."""
        assert ConflictType.DIRECT_CONTRADICTION == "direct_contradiction"
        assert ConflictType.TEMPORAL_CONFLICT == "temporal_conflict"
        assert ConflictType.PARTIAL_DISAGREEMENT == "partial_disagreement"
        assert ConflictType.EVIDENCE_GAP == "evidence_gap"

    def test_conflict_with_resolution_hint(self):
        """해소 힌트가 포함된 모순."""
        conflict = DocumentConflict(
            conflict_type=ConflictType.TEMPORAL_CONFLICT,
            description="시간적 차이",
            document_a="2020_보고서.pdf",
            document_b="2024_보고서.pdf",
            claim_a="과거 정책",
            claim_b="현재 정책",
            severity="medium",
            resolution_hint="시기 차이로 인한 차이",
        )
        assert conflict.resolution_hint == "시기 차이로 인한 차이"

    def test_conflict_without_resolution_hint(self):
        """해소 힌트 없는 모순 (선택 필드)."""
        conflict = DocumentConflict(
            description="테스트",
            document_a="a.pdf",
            document_b="b.pdf",
            claim_a="A",
            claim_b="B",
        )
        assert conflict.resolution_hint is None

    def test_conflict_default_severity(self):
        """severity 기본값은 medium."""
        conflict = DocumentConflict(
            description="테스트",
            document_a="a.pdf",
            document_b="b.pdf",
            claim_a="A",
            claim_b="B",
        )
        assert conflict.severity == "medium"


class TestDocumentAgreement:
    """DocumentAgreement 모델 테스트."""

    def test_create_agreement(self):
        """일치 생성 기본."""
        agreement = DocumentAgreement(
            description="세 문서가 동일한 사실 확인",
            documents=["doc_A.pdf", "doc_B.pdf", "doc_C.pdf"],
            theme="경제 개혁",
            strength="strong",
        )
        assert agreement.strength == "strong"
        assert len(agreement.documents) == 3

    def test_agreement_default_strength(self):
        """일치 강도 기본값은 moderate."""
        agreement = DocumentAgreement(
            description="테스트 일치",
            documents=["doc.pdf"],
        )
        assert agreement.strength == "moderate"


class TestCrossReasoningReport:
    """CrossReasoningReport 모델 테스트."""

    def test_create_report(self):
        """보고서 기본 생성."""
        report = CrossReasoningReport(
            original_query="북한 경제 개혁",
        )
        assert report.original_query == "북한 경제 개혁"
        assert report.status == CrossReasoningStatus.PENDING
        assert report.confidence == 0.0
        assert report.sub_queries == []
        assert report.conflicts == []
        assert report.agreements == []
        assert report.id.startswith("cr_")

    def test_report_with_results(self):
        """결과가 포함된 보고서."""
        report = CrossReasoningReport(
            original_query="테스트",
            status=CrossReasoningStatus.COMPLETED,
            sub_queries=[
                SubQuery(query="하위 질문 1", aspect="fact", order=0),
                SubQuery(query="하위 질문 2", aspect="comparison", order=1),
            ],
            conflicts=[
                DocumentConflict(
                    description="모순",
                    document_a="a.pdf",
                    document_b="b.pdf",
                    claim_a="A",
                    claim_b="B",
                ),
            ],
            agreements=[
                DocumentAgreement(
                    description="일치",
                    documents=["a.pdf", "b.pdf"],
                ),
            ],
            synthesis="종합 분석 결과",
            confidence=0.75,
        )
        assert len(report.sub_queries) == 2
        assert len(report.conflicts) == 1
        assert len(report.agreements) == 1
        assert report.confidence == 0.75


class TestCrossReasoningRequest:
    """CrossReasoningRequest 모델 테스트."""

    def test_basic_request(self):
        """기본 요청."""
        req = CrossReasoningRequest(query="테스트 질문")
        assert req.query == "테스트 질문"
        assert req.mode.value == "reasoning"
        assert req.session_id is None
        assert req.sub_queries is None

    def test_request_with_manual_sub_queries(self):
        """수동 하위 질문 지정."""
        req = CrossReasoningRequest(
            query="원본 질문",
            sub_queries=["하위 1", "하위 2"],
        )
        assert req.sub_queries == ["하위 1", "하위 2"]


class TestCrossReasoningResponse:
    """CrossReasoningResponse 모델 테스트."""

    def test_response(self):
        """응답 모델."""
        report = CrossReasoningReport(original_query="테스트")
        response = CrossReasoningResponse(
            report=report,
            answer="종합 분석 결과",
        )
        assert response.answer == "종합 분석 결과"
        assert response.report.original_query == "테스트"


# ========================================================================== #
# CrossReasoner 로직 테스트 (HAS_CROSS_REASONER 필요)
# ========================================================================== #


@pytest.mark.skipif(not HAS_CROSS_REASONER, reason="Requires CrossReasoner import")
class TestCrossReasonerParsing:
    """CrossReasoner 파싱 로직 테스트."""

    def test_parse_sub_queries_valid_json(self):
        """유효한 JSON에서 하위 질문 파싱."""
        response = '''```json
{
  "sub_queries": [
    {"query": "북한 경제 정책의 변화", "aspect": "fact"},
    {"query": "남한의 대응 정책", "aspect": "comparison"}
  ]
}
```'''
        result = CrossReasoner._parse_sub_queries(response)
        assert len(result) == 2
        assert result[0].query == "북한 경제 정책의 변화"
        assert result[0].aspect == "fact"
        assert result[1].query == "남한의 대응 정책"
        assert result[1].aspect == "comparison"

    def test_parse_sub_queries_no_code_block(self):
        """코드 블록 없이 JSON만 있는 경우."""
        response = '{"sub_queries": [{"query": "테스트", "aspect": "general"}]}'
        result = CrossReasoner._parse_sub_queries(response)
        assert len(result) == 1
        assert result[0].query == "테스트"

    def test_parse_sub_queries_invalid_json(self):
        """잘못된 JSON — 폴백."""
        response = "이것은 JSON이 아닙니다"
        result = CrossReasoner._parse_sub_queries(response)
        assert len(result) == 1
        assert result[0].aspect == "general"  # 폴백

    def test_parse_sub_queries_empty_query_filtered(self):
        """빈 질문 필터링."""
        response = '{"sub_queries": [{"query": "", "aspect": "fact"}, {"query": "유효한 질문", "aspect": "general"}]}'
        result = CrossReasoner._parse_sub_queries(response)
        assert len(result) == 1
        assert result[0].query == "유효한 질문"

    def test_parse_conflicts_valid(self):
        """유효한 모순/일치 파싱."""
        response = '''```json
{
  "conflicts": [
    {
      "conflict_type": "direct_contradiction",
      "description": "직접적 모순",
      "document_a": "a.pdf",
      "document_b": "b.pdf",
      "claim_a": "A 주장",
      "claim_b": "B 주장",
      "severity": "high"
    }
  ],
  "agreements": [
    {
      "description": "공통 주장",
      "documents": ["a.pdf", "b.pdf"],
      "theme": "경제",
      "strength": "strong"
    }
  ]
}
```'''
        conflicts, agreements = CrossReasoner._parse_conflicts(response)
        assert len(conflicts) == 1
        assert len(agreements) == 1
        assert conflicts[0].conflict_type == ConflictType.DIRECT_CONTRADICTION
        assert conflicts[0].severity == "high"
        assert agreements[0].strength == "strong"

    def test_parse_conflicts_empty(self):
        """모순/일치 없는 응답."""
        response = '''```json
{
  "conflicts": [],
  "agreements": []
}
```'''
        conflicts, agreements = CrossReasoner._parse_conflicts(response)
        assert len(conflicts) == 0
        assert len(agreements) == 0

    def test_parse_conflicts_invalid_json(self):
        """잘못된 JSON — 빈 결과 반환."""
        response = "이것은 JSON이 아닙니다"
        conflicts, agreements = CrossReasoner._parse_conflicts(response)
        assert len(conflicts) == 0
        assert len(agreements) == 0

    def test_parse_conflicts_invalid_conflict_type(self):
        """잘못된 모순 유형 — 기본값 사용."""
        response = '''```json
{
  "conflicts": [
    {
      "conflict_type": "unknown_type",
      "description": "테스트",
      "document_a": "a.pdf",
      "document_b": "b.pdf",
      "claim_a": "A",
      "claim_b": "B"
    }
  ],
  "agreements": []
}
```'''
        conflicts, agreements = CrossReasoner._parse_conflicts(response)
        assert len(conflicts) == 1
        # 잘못된 타입 → 기본값 partial_disagreement
        assert conflicts[0].conflict_type == ConflictType.PARTIAL_DISAGREEMENT


@pytest.mark.skipif(not HAS_CROSS_REASONER, reason="Requires CrossReasoner import")
class TestCrossReasonerConfidence:
    """신뢰도 계산 테스트."""

    def test_confidence_high_hits_and_agreements(self):
        """검색 결과 충분, 강한 일치 → 높은 신뢰도."""
        sub_results = [
            SubQueryResult(
                sub_query=SubQuery(query="q1", aspect="fact", order=0),
                hits=[
                    {"text": "t1", "source": "a.pdf", "score": 0.9},
                    {"text": "t2", "source": "b.pdf", "score": 0.8},
                    {"text": "t3", "source": "c.pdf", "score": 0.7},
                ],
                summary="",
            ),
            SubQueryResult(
                sub_query=SubQuery(query="q2", aspect="comparison", order=1),
                hits=[
                    {"text": "t4", "source": "d.pdf", "score": 0.85},
                    {"text": "t5", "source": "e.pdf", "score": 0.75},
                ],
                summary="",
            ),
        ]
        conflicts = []
        agreements = [
            DocumentAgreement(
                description="강한 일치",
                documents=["a.pdf", "b.pdf"],
                strength="strong",
            ),
        ]

        confidence = CrossReasoner._compute_confidence(
            sub_results, conflicts, agreements
        )
        assert confidence > 0.5  # 충분한 히트 + 강한 일치

    def test_confidence_low_no_hits(self):
        """검색 결과 없음 → 낮은 신뢰도."""
        sub_results = [
            SubQueryResult(
                sub_query=SubQuery(query="q1", aspect="fact", order=0),
                hits=[],
                summary="",
            ),
        ]
        conflicts = []
        agreements = []

        confidence = CrossReasoner._compute_confidence(
            sub_results, conflicts, agreements
        )
        assert confidence < 0.3

    def test_confidence_with_severe_conflicts(self):
        """심각한 모순 → 신뢰도 하락."""
        sub_results = [
            SubQueryResult(
                sub_query=SubQuery(query="q1", aspect="fact", order=0),
                hits=[
                    {"text": "t1", "source": "a.pdf", "score": 0.9},
                    {"text": "t2", "source": "b.pdf", "score": 0.8},
                ],
                summary="",
            ),
        ]
        conflicts = [
            DocumentConflict(
                conflict_type=ConflictType.DIRECT_CONTRADICTION,
                description="직접적 모순",
                document_a="a.pdf",
                document_b="b.pdf",
                claim_a="A",
                claim_b="NOT A",
                severity="high",
            ),
        ]
        agreements = []

        confidence = CrossReasoner._compute_confidence(
            sub_results, conflicts, agreements
        )
        assert confidence < 0.6

    def test_confidence_bounded(self):
        """신뢰도는 항상 0~1 범위."""
        sub_results = [
            SubQueryResult(
                sub_query=SubQuery(query="q1", aspect="fact", order=0),
                hits=[{"text": "t1", "source": "a.pdf", "score": 0.9}],
                summary="",
            ),
        ]
        conflicts = []
        agreements = [
            DocumentAgreement(
                description="강한 일치",
                documents=["a.pdf", "b.pdf"],
                strength="strong",
            ),
            DocumentAgreement(
                description="강한 일치 2",
                documents=["a.pdf", "c.pdf"],
                strength="strong",
            ),
        ]

        confidence = CrossReasoner._compute_confidence(
            sub_results, conflicts, agreements
        )
        assert 0.0 <= confidence <= 1.0


@pytest.mark.skipif(not HAS_CROSS_REASONER, reason="Requires CrossReasoner import")
class TestCrossReasonerFallbackSynthesis:
    """폴백 종합 분석 테스트."""

    def test_fallback_synthesis_basic(self):
        """기본 폴백 종합 분석."""
        sub_results = [
            SubQueryResult(
                sub_query=SubQuery(query="테스트 질문", aspect="fact", order=0),
                hits=[
                    {"text": "검색 결과 텍스트", "source": "doc.pdf", "score": 0.9, "page": 1},
                ],
                summary="",
            ),
        ]
        conflicts = [
            DocumentConflict(
                conflict_type=ConflictType.PARTIAL_DISAGREEMENT,
                description="부분 불일치",
                document_a="a.pdf",
                document_b="b.pdf",
                claim_a="A",
                claim_b="B",
                severity="medium",
            ),
        ]
        agreements = [
            DocumentAgreement(
                description="일치 항목",
                documents=["a.pdf", "b.pdf"],
                strength="moderate",
            ),
        ]

        result = CrossReasoner._generate_fallback_synthesis(
            "원본 질문", sub_results, conflicts, agreements
        )
        assert "원본 질문" in result
        assert "1건" in result  # 모순 1건
        assert "일치" in result

    def test_fallback_synthesis_no_results(self):
        """검색 결과 없는 폴백."""
        sub_results = [
            SubQueryResult(
                sub_query=SubQuery(query="q1", aspect="fact", order=0),
                hits=[],
                summary="",
            ),
        ]
        result = CrossReasoner._generate_fallback_synthesis(
            "질문", sub_results, [], []
        )
        assert "검색 결과 없음" in result


@pytest.mark.skipif(not HAS_CROSS_REASONER, reason="Requires CrossReasoner import")
class TestCrossReasonerFormatSubResults:
    """검색 결과 포맷팅 테스트."""

    def test_format_sub_results_with_hits(self):
        """검색 결과가 있는 경우 포맷팅."""
        sub_results = [
            SubQueryResult(
                sub_query=SubQuery(query="북한 경제", aspect="fact", order=0),
                hits=[
                    {"text": "경제 개혁 내용", "source": "report.pdf", "score": 0.9, "page": 5},
                    {"text": "정책 변화", "source": "white_paper.pdf", "score": 0.8},
                ],
                summary="",
            ),
        ]

        result = CrossReasoner()._format_sub_results(sub_results)
        assert "북한 경제" in result
        assert "report.pdf" in result

    def test_format_sub_results_empty(self):
        """검색 결과가 없는 경우."""
        sub_results = [
            SubQueryResult(
                sub_query=SubQuery(query="빈 질문", aspect="general", order=0),
                hits=[],
                summary="",
            ),
        ]
        result = CrossReasoner()._format_sub_results(sub_results)
        assert "검색 결과 없음" in result