"""mAI-Brain — 교차 문서 추론(Cross-Document Reasoning) API

엔드포인트:
- POST /api/cross-reasoning/analyze — 교차 문서 추론 분석 실행
- POST /api/cross-reasoning/decompose — 질문 분해만 수행 (디버그용)
- POST /api/cross-reasoning/detect — 모순/일치 탐지만 수행 (디버그용)

핵심 플로우:
1. 사용자 질문 수신
2. (선택) 하위 질문 자동 분해
3. 각 하위 질문 독립 RAG 검색
4. 검색 결과 간 모순/일치 탐지
5. 종합 분석 보고서 + 최종 답변 생성
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException

from app.config import ChatMode
from app.core.cross_reasoner import get_cross_reasoner
from app.models.cross_reasoning import (
    CrossReasoningRequest,
    CrossReasoningResponse,
    CrossReasoningReport,
    CrossReasoningStatus,
)

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/analyze", response_model=CrossReasoningResponse)
async def analyze_cross_reasoning(request: CrossReasoningRequest):
    """교차 문서 추론 분석 실행.

    전체 파이프라인:
    질문 분해 → 하위 질문 검색 → 모순/일치 탐지 → 종합 분석

    요청 바디:
        query: 원본 질문 (필수)
        mode: 채팅 모드 (기본: reasoning)
        session_id: 세션 ID (선택)
        reasoning_strength: 추론 강도 필터 (선택)
        sub_queries: 수동 하위 질문 (선택, 없으면 자동 생성)

    응답:
        report: 전체 분석 보고서
        answer: 최종 답변 (synthesis 요약)
    """
    if not request.query.strip():
        raise HTTPException(
            status_code=400,
            detail="질문을 입력해주세요.",
        )

    cross_reasoner = get_cross_reasoner()

    try:
        report = cross_reasoner.analyze(request)

        # 최종 답변: synthesis를 answer로 반환 (프론트엔드 호환성)
        answer = report.synthesis

        return CrossReasoningResponse(
            report=report,
            answer=answer,
        )

    except Exception as exc:
        logger.error("교차 추론 분석 오류: %s", exc, exc_info=True)

        # 부분 결과라도 반환
        error_report = CrossReasoningReport(
            original_query=request.query,
            mode=request.mode,
            status=CrossReasoningStatus.FAILED,
            synthesis=f"교차 추론 분석 중 오류가 발생했습니다: {exc}",
        )

        return CrossReasoningResponse(
            report=error_report,
            answer=error_report.synthesis,
        )


@router.post("/decompose", response_model=list)
async def decompose_query(query: str):
    """질문 분해만 수행 (디버그/테스트용).

    Args:
        query: 분해할 원본 질문

    Returns:
        분해된 하위 질문 리스트
    """
    if not query.strip():
        raise HTTPException(
            status_code=400,
            detail="질문을 입력해주세요.",
        )

    cross_reasoner = get_cross_reasoner()

    try:
        sub_queries = cross_reasoner.decompose_query(query=query)
        return [sq.model_dump() for sq in sub_queries]
    except Exception as exc:
        logger.error("질문 분해 오류: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"질문 분해 중 오류가 발생했습니다: {exc}",
        ) from exc


@router.post("/detect")
async def detect_conflicts(query: str):
    """모순/일치 탐지만 수행 (디버그/테스트용).

    주어진 질문으로 검색 후 모순/일치를 탐지합니다.
    질문 분해는 자동으로 수행됩니다.

    Args:
        query: 탐지할 원본 질문

    Returns:
        모순과 일치 목록
    """
    if not query.strip():
        raise HTTPException(
            status_code=400,
            detail="질문을 입력해주세요.",
        )

    cross_reasoner = get_cross_reasoner()

    try:
        # 질문 분해
        sub_queries = cross_reasoner.decompose_query(query=query)

        # 검색
        sub_results = cross_reasoner.search_sub_queries(
            sub_queries=sub_queries,
            mode=ChatMode.REASONING,
        )

        # 모순/일치 탐지
        conflicts, agreements = cross_reasoner.detect_conflicts(
            query=query,
            sub_results=sub_results,
        )

        return {
            "query": query,
            "conflicts": [c.model_dump() for c in conflicts],
            "agreements": [a.model_dump() for a in agreements],
            "sub_queries": [sq.model_dump() for sq in sub_queries],
        }

    except Exception as exc:
        logger.error("모순 탐지 오류: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"모순 탐지 중 오류가 발생했습니다: {exc}",
        ) from exc