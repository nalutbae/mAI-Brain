"""mAI-Brain — Cross-Document Reasoning API

엔드포인트:
- POST /api/cross-reasoning/analyze       — 교차 검증 분석 실행
- GET  /api/cross-reasoning/analyses       — 분석 결과 목록 조회
- GET  /api/cross-reasoning/analyses/{id}  — 특정 분석 결과 조회
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException

from app.core.cross_reasoner import get_cross_reasoner
from app.models.cross_reasoning import (
    CrossAnalysis,
    CrossAnalysisRequest,
)

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/analyze", response_model=CrossAnalysis)
async def analyze_cross_document(request: CrossAnalysisRequest):
    """교차 검증 분석 실행.

    원본 질문을 다중 하위 질문으로 분해하고,
    각 하위 질문을 독립 검색한 후 문서 간 모순/일치를 분석합니다.
    """
    cross_reasoner = get_cross_reasoner()

    try:
        result = cross_reasoner.analyze(request)
        return result
    except Exception as exc:
        logger.error("교차 검증 분석 오류: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"교차 검증 분석 중 오류가 발생했습니다: {exc}",
        ) from exc


@router.get("/analyses", response_model=list[CrossAnalysis])
async def list_analyses():
    """분석 결과 목록 조회 (최신순)."""
    cross_reasoner = get_cross_reasoner()
    return cross_reasoner.store.list_all()


@router.get("/analyses/{analysis_id}", response_model=CrossAnalysis)
async def get_analysis(analysis_id: str):
    """특정 분석 결과 조회."""
    cross_reasoner = get_cross_reasoner()
    result = cross_reasoner.store.get(analysis_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"분석 결과를 찾을 수 없습니다: {analysis_id}")
    return result