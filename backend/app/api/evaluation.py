"""mAI-Brain — RAG 평가 API

엔드포인트:
- POST /api/evaluation/run        — 평가 실행
- GET  /api/evaluation/results     — 평가 결과 목록 조회
- GET  /api/evaluation/results/{id} — 특정 평가 결과 조회
- GET  /api/evaluation/stats       — 평가 통계 조회

QA pairs 관리:
- GET    /api/evaluation/qa-pairs       — QA pairs 목록
- POST   /api/evaluation/qa-pairs       — QA pair 생성
- PUT    /api/evaluation/qa-pairs/{id}  — QA pair 수정
- DELETE /api/evaluation/qa-pairs/{id}  — QA pair 삭제
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException

from app.core.evaluator import get_evaluator
from app.models.evaluation import (
    QAPair,
    QAPairCreate,
    QAPairUpdate,
    EvaluationRun,
    EvaluationRunRequest,
    EvaluationStats,
)

logger = logging.getLogger(__name__)

router = APIRouter()


# ── QA Pairs 관리 ──────────────────────────────────────────────────────────

@router.get("/qa-pairs", response_model=list[QAPair])
async def list_qa_pairs():
    """QA pairs 목록 조회."""
    evaluator = get_evaluator()
    return evaluator.qa_store.list_all()


@router.post("/qa-pairs", response_model=QAPair, status_code=201)
async def create_qa_pair(create: QAPairCreate):
    """QA pair 생성."""
    evaluator = get_evaluator()
    return evaluator.qa_store.add(create)


@router.put("/qa-pairs/{qa_id}", response_model=QAPair)
async def update_qa_pair(qa_id: str, update: QAPairUpdate):
    """QA pair 수정."""
    evaluator = get_evaluator()
    pair = evaluator.qa_store.update(qa_id, update)
    if pair is None:
        raise HTTPException(status_code=404, detail=f"QA pair를 찾을 수 없습니다: {qa_id}")
    return pair


@router.delete("/qa-pairs/{qa_id}", status_code=204)
async def delete_qa_pair(qa_id: str):
    """QA pair 삭제."""
    evaluator = get_evaluator()
    if not evaluator.qa_store.delete(qa_id):
        raise HTTPException(status_code=404, detail=f"QA pair를 찾을 수 없습니다: {qa_id}")


# ── 평가 실행 및 결과 ──────────────────────────────────────────────────────

@router.post("/run", response_model=EvaluationRun)
async def run_evaluation(request: EvaluationRunRequest):
    """평가 실행.

    지정된 QA pairs에 대해 RAG 시스템을 실행하고 품질 지표를 계산합니다.
    qa_pair_ids가 비어있으면 전체 QA pairs를 평가합니다.
    """
    evaluator = get_evaluator()

    try:
        result = evaluator.run_evaluation(
            qa_pair_ids=request.qa_pair_ids or None,
            mode=request.mode,
        )
        return result
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.error("평가 실행 오류: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"평가 실행 중 오류가 발생했습니다: {exc}",
        ) from exc


@router.get("/results", response_model=list[EvaluationRun])
async def list_evaluation_results():
    """평가 결과 목록 조회 (최신순)."""
    evaluator = get_evaluator()
    return evaluator.result_store.list_all()


@router.get("/results/{eval_id}", response_model=EvaluationRun)
async def get_evaluation_result(eval_id: str):
    """특정 평가 결과 조회."""
    evaluator = get_evaluator()
    result = evaluator.result_store.get(eval_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"평가 결과를 찾을 수 없습니다: {eval_id}")
    return result


@router.get("/stats", response_model=EvaluationStats)
async def get_evaluation_stats():
    """평가 통계 조회."""
    evaluator = get_evaluator()
    return evaluator.get_stats()