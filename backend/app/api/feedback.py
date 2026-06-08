"""mAI-Brain — Human-in-the-Loop RAG 피드백 API

엔드포인트:
- POST /api/feedback          — 피드백 제출 (👍/👎 + 태그 + 코멘트 + 정정)
- GET  /api/feedback           — 피드백 목록 조회 (필터링 지원)
- GET  /api/feedback/stats     — 피드백 통계
- GET  /api/feedback/suggestions — 자동 개선 제안
- GET  /api/feedback/session/{session_id} — 세션별 피드백
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from app.core.feedback import get_feedback_analyzer
from app.models.feedback import (
    Feedback,
    FeedbackCreate,
    FeedbackStats,
    FeedbackSuggestion,
    FeedbackType,
)

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("", response_model=Feedback, status_code=201)
async def create_feedback(request: FeedbackCreate):
    """피드백 제출.

    사용자가 AI 응답에 대한 평가(👍/👎) 또는 정정 정보를 제출합니다.
    부정 평가 시 태그(reason)와 코멘트를 함께 제출할 수 있습니다.
    정정 제안 시 correction_type과 correction_text를 포함합니다.
    """
    analyzer = get_feedback_analyzer()

    # 정정 제안 시 필수 필드 검증
    if request.feedback_type == FeedbackType.CORRECTION and not request.correction_text:
        raise HTTPException(
            status_code=400,
            detail="정정 제안은 correction_text가 필요합니다.",
        )

    feedback = analyzer.store.add(request)
    logger.info("피드백 접수: %s (세션: %s)", feedback.id, feedback.session_id or "미지정")
    return feedback


@router.get("", response_model=list[Feedback])
async def list_feedback(
    feedback_type: Optional[FeedbackType] = Query(None, description="피드백 유형 필터"),
    session_id: Optional[str] = Query(None, description="세션 ID 필터"),
    limit: int = Query(50, ge=1, le=200, description="조회 수 제한"),
):
    """피드백 목록 조회.

    유형 또는 세션 ID로 필터링할 수 있습니다.
    """
    analyzer = get_feedback_analyzer()

    if session_id:
        feedbacks = analyzer.store.list_by_session(session_id)
    elif feedback_type:
        feedbacks = analyzer.store.list_by_type(feedback_type)
    else:
        feedbacks = analyzer.store.list_all()

    return feedbacks[:limit]


@router.get("/stats", response_model=FeedbackStats)
async def get_feedback_stats():
    """피드백 통계 조회.

    전체 피드백 수, 만족률, 태그 분포, 최근 트렌드를 반환합니다.
    """
    analyzer = get_feedback_analyzer()
    return analyzer.compute_stats()


@router.get("/suggestions", response_model=list[FeedbackSuggestion])
async def get_feedback_suggestions():
    """자동 개선 제안 조회.

    누적 피드백을 분석하여 RAG 품질 개선 제안을 생성합니다.
    분석 항목:
    - 환각 다발 → 임베딩 모델 재평가
    - 관련 없는 결과 → top-k 증설
    - 불완전 응답 → 청킹 크기 증설
    - 구식 정보 → 문서 재인덱싱
    - 잘못된 출처 → 검색 정확도 개선
    - 편향 응답 → 시스템 프롬프트 수정
    """
    analyzer = get_feedback_analyzer()
    return analyzer.generate_suggestions()


@router.get("/session/{session_id}", response_model=list[Feedback])
async def get_session_feedback(session_id: str):
    """세션별 피드백 조회."""
    analyzer = get_feedback_analyzer()
    feedbacks = analyzer.store.list_by_session(session_id)
    if not feedbacks:
        # 세션에 피드백이 없는 경우 빈 목록 반환 (404 아님)
        pass
    return feedbacks