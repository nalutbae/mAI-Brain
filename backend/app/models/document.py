"""mAI-Brain AI 챗봇 — 문서 관련 Pydantic 모델

문서 업로드 요청, 인덱싱 상태 응답, 문서 목록 응답 모델을 정의합니다.
"""

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


# --------------------------------------------------------------------------- #
# Enums
# --------------------------------------------------------------------------- #

class IndexingStatus(str, Enum):
    """문서 인덱싱 상태"""
    PENDING = "pending"       # 대기 중
    INDEXING = "indexing"      # 인덱싱 진행 중
    COMPLETED = "completed"    # 인덱싱 완료
    FAILED = "failed"          # 인덱싱 실패


# --------------------------------------------------------------------------- #
# 요청 모델
# --------------------------------------------------------------------------- #

class DocumentUploadRequest(BaseModel):
    """문서 업로드 요청 (multipart 폼 데이터의 메타데이터 부분)

    파일 자체는 UploadFile로 수신하며, 이 모델은 추가 메타데이터가
    필요해질 때 확장용으로 사용.
    """
    # 향후 확장: 문서 타입 태그, 언어 지정 등
    pass


# --------------------------------------------------------------------------- #
# 응답 모델
# --------------------------------------------------------------------------- #

class DocumentUploadResponse(BaseModel):
    """문서 업로드 응답

    업로드 즉시 반환되며, 클라이언트는 document_id로 상태를 폴링.
    """
    document_id: str = Field(
        ...,
        description="문서 식별자 (파일명 기반 UUID 아님)",
    )
    filename: str = Field(
        ...,
        description="원본 파일명",
    )
    status: IndexingStatus = Field(
        default=IndexingStatus.INDEXING,
        description="초기 인덱싱 상태 (업로드 직후 = indexing)",
    )
    message: str = Field(
        default="파일이 업로드되었으며 인덱싱이 시작되었습니다.",
        description="안내 메시지",
    )


class DocumentStatusResponse(BaseModel):
    """인덱싱 상태 조회 응답"""
    document_id: str = Field(..., description="문서 식별자")
    filename: str = Field(..., description="원본 파일명")
    status: IndexingStatus = Field(..., description="현재 인덱싱 상태")
    total_chunks: Optional[int] = Field(
        default=None,
        description="총 청크 수 (인덱싱 완료 후 설정)",
    )
    error: Optional[str] = Field(
        default=None,
        description="실패 시 에러 메시지",
    )
    created_at: Optional[datetime] = Field(
        default=None,
        description="최초 인덱싱 시작 시각",
    )
    completed_at: Optional[datetime] = Field(
        default=None,
        description="인덱싱 완료 시각",
    )


class DocumentInfo(BaseModel):
    """문서 목록의 개별 항목"""
    document_id: str = Field(..., description="문서 식별자")
    filename: str = Field(..., description="원본 파일명")
    status: IndexingStatus = Field(..., description="인덱싱 상태")
    total_chunks: Optional[int] = Field(default=None, description="총 청크 수")
    created_at: Optional[datetime] = Field(default=None, description="생성 시각")


class DocumentListResponse(BaseModel):
    """인덱싱된 문서 목록 응답"""
    documents: list[DocumentInfo] = Field(
        default_factory=list,
        description="문서 목록",
    )
    total: int = Field(
        ...,
        description="전체 문서 수",
    )


class IndexResult(BaseModel):
    """인덱싱 결과 (내부용 — indexer → API로 전달)

    indexer.index_document() 의 반환값.
    """
    document_id: str = Field(..., description="문서 식별자")
    filename: str = Field(..., description="원본 파일명")
    status: IndexingStatus = Field(..., description="인덱싱 결과 상태")
    total_chunks: int = Field(default=0, description="생성된 총 청크 수")
    error: Optional[str] = Field(default=None, description="실패 시 에러 메시지")