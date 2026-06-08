"""mAI-Brain — Human-in-the-Loop RAG 피드백 분석 엔진

사용자 피드백 수집, 통계 분석, 자동 개선 제안 시스템.

핵심 기능:
- 피드백 저장/조회 (메모리 + 파일 영속화)
- 통계 집계 (만족률, 태그 분포, 최근 트렌드)
- 오답 로그 기반 청크 품질 분석 → top-k, 청킹 크기, 임베딩 모델 튜닝 제안
- 세션별 피드백 조회
"""

from __future__ import annotations

import json
import logging
from collections import Counter
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

from app.models.feedback import (
    Feedback,
    FeedbackCreate,
    FeedbackStats,
    FeedbackSuggestion,
    FeedbackType,
    FeedbackTag,
    ImprovementTarget,
)

logger = logging.getLogger(__name__)

# 피드백 저장 경로
FEEDBACK_DIR = "data/feedback"


# --------------------------------------------------------------------------- #
# 피드백 스토어 (JSON 파일 기반)
# --------------------------------------------------------------------------- #

class FeedbackStore:
    """피드백 파일 기반 저장소."""

    def __init__(self, base_dir: str = FEEDBACK_DIR) -> None:
        self._dir = Path(base_dir)
        self._dir.mkdir(parents=True, exist_ok=True)
        self._file = self._dir / "feedbacks.json"
        self._feedbacks: list[Feedback] = self._load()

    def _load(self) -> list[Feedback]:
        if not self._file.exists():
            return []
        try:
            data = json.loads(self._file.read_text(encoding="utf-8"))
            return [Feedback(**item) for item in data]
        except (json.JSONDecodeError, KeyError) as exc:
            logger.error("피드백 로드 실패: %s", exc)
            return []

    def _save(self) -> None:
        self._file.write_text(
            json.dumps(
                [fb.model_dump() for fb in self._feedbacks],
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

    def add(self, create: FeedbackCreate) -> Feedback:
        """피드백 추가."""
        feedback = Feedback(**create.model_dump())
        self._feedbacks.append(feedback)
        self._save()
        logger.info("피드백 추가: %s (%s)", feedback.id, feedback.feedback_type)
        return feedback

    def get(self, feedback_id: str) -> Optional[Feedback]:
        """피드백 ID로 조회."""
        for fb in self._feedbacks:
            if fb.id == feedback_id:
                return fb
        return None

    def list_all(self) -> list[Feedback]:
        """전체 피드백 목록 (최신순)."""
        return sorted(self._feedbacks, key=lambda fb: fb.created_at, reverse=True)

    def list_by_session(self, session_id: str) -> list[Feedback]:
        """세션별 피드백 조회."""
        return [
            fb for fb in self._feedbacks
            if fb.session_id == session_id
        ]

    def list_by_type(self, feedback_type: FeedbackType) -> list[Feedback]:
        """유형별 피드백 조회."""
        return [
            fb for fb in self._feedbacks
            if fb.feedback_type == feedback_type
        ]

    def get_thumbs_down_feedbacks(self) -> list[Feedback]:
        """부정 평가 피드백만 조회 (개선 제안 분석용)."""
        return [
            fb for fb in self._feedbacks
            if fb.feedback_type == FeedbackType.THUMBS_DOWN
        ]

    def get_corrections(self) -> list[Feedback]:
        """정정 제안 피드백만 조회."""
        return [
            fb for fb in self._feedbacks
            if fb.feedback_type == FeedbackType.CORRECTION
        ]


# --------------------------------------------------------------------------- #
# 피드백 분석 엔진
# --------------------------------------------------------------------------- #

class FeedbackAnalyzer:
    """피드백 분석 및 개선 제안 엔진.

    분석 파이프라인:
    1. 누적 피드백 통계 집계 (만족률, 태그 분포, 트렌드)
    2. 오답 로그에서 패턴 추출 (어떤 청크가 자주 오답 유발?)
    3. RAG 파라미터 튜닝 제안 (top-k, 청킹 크기, 임베딩 모델)
    """

    def __init__(self) -> None:
        self._store = FeedbackStore()

    @property
    def store(self) -> FeedbackStore:
        return self._store

    def compute_stats(self) -> FeedbackStats:
        """피드백 통계 집계."""
        all_feedbacks = self._store.list_all()
        if not all_feedbacks:
            return FeedbackStats()

        # 유형별 카운트
        thumbs_up = sum(1 for fb in all_feedbacks if fb.feedback_type == FeedbackType.THUMBS_UP)
        thumbs_down = sum(1 for fb in all_feedbacks if fb.feedback_type == FeedbackType.THUMBS_DOWN)
        corrections = sum(1 for fb in all_feedbacks if fb.feedback_type == FeedbackType.CORRECTION)

        # 만족률
        total = thumbs_up + thumbs_down
        satisfaction_rate = thumbs_up / total if total > 0 else 0.0

        # 태그 분포
        tag_counter: Counter[str] = Counter()
        for fb in all_feedbacks:
            for tag in fb.tags:
                tag_counter[tag.value] += 1

        # 최근 7일 트렌드
        now = datetime.now(timezone.utc)
        week_ago = now - timedelta(days=7)
        recent = [
            fb for fb in all_feedbacks
            if datetime.fromisoformat(fb.created_at) > week_ago
        ]
        recent_up = sum(1 for fb in recent if fb.feedback_type == FeedbackType.THUMBS_UP)
        recent_down = sum(1 for fb in recent if fb.feedback_type == FeedbackType.THUMBS_DOWN)

        return FeedbackStats(
            total_feedbacks=len(all_feedbacks),
            thumbs_up=thumbs_up,
            thumbs_down=thumbs_down,
            corrections=corrections,
            satisfaction_rate=round(satisfaction_rate, 4),
            tag_distribution=dict(tag_counter),
            recent_trend={"thumbs_up": recent_up, "thumbs_down": recent_down},
        )

    def generate_suggestions(self) -> list[FeedbackSuggestion]:
        """자동 개선 제안 생성.

        분석 로직:
        1. 환각 태그 빈도 → 임베딩 모델 재평가 제안
        2. 관련 없는 결과 태그 → top-k 증설 제안
        3. 불완전 응답 태그 → 청킹 크기 증설 제안
        4. 구식 정보 태그 → 문서 재인덱싱 제안
        5. 정정 제안 → 해당 응답 정정 사항 반영
        """
        thumbs_down_list = self._store.get_thumbs_down_feedbacks()
        corrections_list = self._store.get_corrections()
        stats = self.compute_stats()
        suggestions: list[FeedbackSuggestion] = []

        # 태그별 카운트
        tag_counter = Counter(tag for fb in thumbs_down_list for tag in fb.tags)

        # 1. 환각(Hallucination) 다발 → 임베딩 모델 재평가
        hallucination_count = tag_counter.get(FeedbackTag.HALLUCINATION, 0)
        if hallucination_count >= 2:
            suggestions.append(FeedbackSuggestion(
                target=ImprovementTarget.EMBEDDING_MODEL,
                title="임베딩 모델 재평가 필요",
                description=f"환각(Hallucination) 피드백 {hallucination_count}건 — 검색 결과와 질문의 의미적 유사도를 제대로 포착하지 못하고 있을 가능성. 임베딩 모델 교체 또는 파인튜닝을 권장합니다.",
                priority="high" if hallucination_count >= 5 else "medium",
                affected_feedback_ids=[fb.id for fb in thumbs_down_list if FeedbackTag.HALLUCINATION in fb.tags],
                data={"hallucination_count": hallucination_count},
            ))

        # 2. 관련 없는 결과(irrelevant) → top-k 증설
        irrelevant_count = tag_counter.get(FeedbackTag.IRRELEVANT, 0)
        if irrelevant_count >= 2:
            suggestions.append(FeedbackSuggestion(
                target=ImprovementTarget.TOP_K,
                title="검색 결과 수(top-k) 증설 권장",
                description=f"관련 없는 결과(irrelevant) 피드백 {irrelevant_count}건 — 현재 top-k가 너무 작아 관련 문서를 놓치고 있을 가능성. top-k를 5→10으로 증설 후 재검증하세요.",
                priority="medium",
                affected_feedback_ids=[fb.id for fb in thumbs_down_list if FeedbackTag.IRRELEVANT in fb.tags],
                data={"irrelevant_count": irrelevant_count},
            ))

        # 3. 불완전 응답(incomplete) → 청킹 크기 증설
        incomplete_count = tag_counter.get(FeedbackTag.INCOMPLETE, 0)
        if incomplete_count >= 2:
            suggestions.append(FeedbackSuggestion(
                target=ImprovementTarget.CHUNK_SIZE,
                title="청킹 크기 증설 권장",
                description=f"불완전 응답(incomplete) 피드백 {incomplete_count}건 — 청크가 너무 작아 문맥이 끊길 가능성. 청킹 크기를 늘리거나 오버랩을 증설하세요.",
                priority="medium",
                affected_feedback_ids=[fb.id for fb in thumbs_down_list if FeedbackTag.INCOMPLETE in fb.tags],
                data={"incomplete_count": incomplete_count},
            ))

        # 4. 구식 정보(outdated) → 문서 재인덱싱
        outdated_count = tag_counter.get(FeedbackTag.OUTDATED, 0)
        if outdated_count >= 2:
            suggestions.append(FeedbackSuggestion(
                target=ImprovementTarget.REINDEX,
                title="문서 재인덱싱 필요",
                description=f"구식 정보(outdated) 피드백 {outdated_count}건 — 인덱싱된 문서가 최신이 아닐 가능성. 문서를 업데이트하고 재인덱싱하세요.",
                priority="high",
                affected_feedback_ids=[fb.id for fb in thumbs_down_list if FeedbackTag.OUTDATED in fb.tags],
                data={"outdated_count": outdated_count},
            ))

        # 5. 잘못된 출처(wrong_source) → 검색 정확도 개선
        wrong_source_count = tag_counter.get(FeedbackTag.WRONG_SOURCE, 0)
        if wrong_source_count >= 2:
            suggestions.append(FeedbackSuggestion(
                target=ImprovementTarget.TOP_K,
                title="검색 정확도 개선 필요",
                description=f"잘못된 출처(wrong_source) 피드백 {wrong_source_count}건 — 검색 결과의 출처가 질문과 무관. 하이브리드 검색 가중치 조정 또는 리랭킹 도입을 권장합니다.",
                priority="high" if wrong_source_count >= 5 else "medium",
                affected_feedback_ids=[fb.id for fb in thumbs_down_list if FeedbackTag.WRONG_SOURCE in fb.tags],
                data={"wrong_source_count": wrong_source_count},
            ))

        # 6. 편향(biased) → 프롬프트 수정
        biased_count = tag_counter.get(FeedbackTag.BIASED, 0)
        if biased_count >= 1:
            suggestions.append(FeedbackSuggestion(
                target=ImprovementTarget.PROMPT,
                title="시스템 프롬프트 중립성 검토",
                description=f"편향(biased) 피드백 {biased_count}건 — AI 응답이 특정 관점에 치우칠 가능성. 시스템 프롬프트에 중립성 가이드를 추가하세요.",
                priority="medium",
                affected_feedback_ids=[fb.id for fb in thumbs_down_list if FeedbackTag.BIASED in fb.tags],
                data={"biased_count": biased_count},
            ))

        # 7. 불분명(unclear) → 응답 포맷 개선
        unclear_count = tag_counter.get(FeedbackTag.UNCLEAR, 0)
        if unclear_count >= 2:
            suggestions.append(FeedbackSuggestion(
                target=ImprovementTarget.PROMPT,
                title="응답 명확성 개선 권장",
                description=f"불분명(unclear) 피드백 {unclear_count}건 — AI 응답이 사용자에게 충분히 명확하지 않음. 요약 포맷, 구조화 가이드를 프롬프트에 추가하세요.",
                priority="low",
                affected_feedback_ids=[fb.id for fb in thumbs_down_list if FeedbackTag.UNCLEAR in fb.tags],
                data={"unclear_count": unclear_count},
            ))

        # 8. 만족률이 70% 미만이면 전반적 개선 제안
        if stats.total_feedbacks >= 5 and stats.satisfaction_rate < 0.7:
            suggestions.append(FeedbackSuggestion(
                target=ImprovementTarget.EMBEDDING_MODEL,
                title="전반적 품질 개선 필요",
                description=f"만족률이 {stats.satisfaction_rate * 100:.1f}%로 낮습니다. 임베딩 모델, 청킹 전략, top-k 설정을 종합적으로 재검토하세요.",
                priority="high",
                affected_feedback_ids=[fb.id for fb in thumbs_down_list[:10]],
                data={
                    "satisfaction_rate": stats.satisfaction_rate,
                    "total_feedbacks": stats.total_feedbacks,
                },
            ))

        # 9. 정정 제안 반영
        for correction in corrections_list[:5]:
            suggestions.append(FeedbackSuggestion(
                target=ImprovementTarget.REINDEX,
                title=f"정정 제안: {correction.query[:40]}{'...' if len(correction.query) > 40 else ''}",
                description=f"사용자 정정 — 유형: {correction.correction_type.value if correction.correction_type else '미지정'}\n내용: {correction.correction_text[:200]}{'...' if len(correction.correction_text) > 200 else ''}",
                priority="medium",
                affected_feedback_ids=[correction.id],
                data={
                    "correction_type": correction.correction_type.value if correction.correction_type else None,
                    "original_query": correction.query,
                    "correction_text": correction.correction_text,
                },
            ))

        # 우선순위 정렬
        priority_order = {"high": 0, "medium": 1, "low": 2}
        suggestions.sort(key=lambda s: priority_order.get(s.priority, 1))

        return suggestions


# --------------------------------------------------------------------------- #
# 싱글톤
# --------------------------------------------------------------------------- #

_analyzer: Optional[FeedbackAnalyzer] = None


def get_feedback_analyzer() -> FeedbackAnalyzer:
    """FeedbackAnalyzer 싱글톤 인스턴스 반환."""
    global _analyzer
    if _analyzer is None:
        _analyzer = FeedbackAnalyzer()
    return _analyzer