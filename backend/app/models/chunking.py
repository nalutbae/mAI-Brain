"""mAI-Brain — Semantic Chunking Profiles 데이터 모델

도메인별 시맨틱 청킹 프로파일을 정의합니다.

프로파일:
- legal (법률): 조문 단위 (제X조 경계 인식)
- paper (논문): 섹션 단위 (Abstract/Method/Results)
- news (뉴스): 기사 단위 (5W1H 구조)
- general (일반): 기본 700토큰 고정 청킹 (현재 기본값)
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


# --------------------------------------------------------------------------- #
# 청킹 프로파일
# --------------------------------------------------------------------------- #

class ChunkingStrategy(str, Enum):
    """청킹 전략 유형."""
    FIXED = "fixed"            # 고정 크기 청킹 (기본)
    SENTENCE = "sentence"      # 문장 단위 청킹
    PARAGRAPH = "paragraph"    # 단락 단위 청킹
    SECTION = "section"        # 섹션/장 단위 청킹
    ARTICLE = "article"        # 조/항 단위 청킹 (법률)


class ChunkingProfile(BaseModel):
    """시맨틱 청킹 프로파일.

    Attributes:
        id: 프로파일 고유 ID
        name: 프로파일 이름 (legal, paper, news, general 등)
        description: 프로파일 설명
        strategy: 청킹 전략
        chunk_size: 청크 최대 크기 (글자 수)
        chunk_overlap: 청크 오버랩 (글자 수)
        separator_pattern: 섹션 분할 정규식 패턴 (선택)
        min_chunk_size: 최소 청크 크기 (이보다 작으면 병합)
        metadata_fields: 청크 메타데이터에 포함할 추가 필드
        is_default: 기본 프로파일 여부
        created_at: 생성 시각
    """

    id: str = Field(default_factory=lambda: f"profile_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}")
    name: str
    description: str = ""
    strategy: ChunkingStrategy = ChunkingStrategy.FIXED
    chunk_size: int = 700
    chunk_overlap: int = 150
    separator_pattern: str = ""
    min_chunk_size: int = 50
    metadata_fields: list[str] = Field(default_factory=list)
    is_default: bool = False
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class ChunkingProfileCreate(BaseModel):
    """청킹 프로파일 생성 요청."""
    name: str
    description: str = ""
    strategy: ChunkingStrategy = ChunkingStrategy.FIXED
    chunk_size: int = 700
    chunk_overlap: int = 150
    separator_pattern: str = ""
    min_chunk_size: int = 50
    metadata_fields: list[str] = Field(default_factory=list)


class ChunkingProfileUpdate(BaseModel):
    """청킹 프로파일 수정 요청."""
    name: Optional[str] = None
    description: Optional[str] = None
    strategy: Optional[ChunkingStrategy] = None
    chunk_size: Optional[int] = None
    chunk_overlap: Optional[int] = None
    separator_pattern: Optional[str] = None
    min_chunk_size: Optional[int] = None
    metadata_fields: Optional[list[str]] = None


# --------------------------------------------------------------------------- #
# 청킹 미리보기
# --------------------------------------------------------------------------- #

class ChunkPreview(BaseModel):
    """청킹 미리보기 결과.

   Attributes:
        profile_id: 적용된 프로파일 ID
        total_chunks: 생성된 청크 수
        chunks: 미리보기용 청크 리스트 (최대 10개)
        avg_chunk_size: 평균 청크 크기
        total_chars: 전체 글자 수
    """

    profile_id: str
    total_chunks: int
    chunks: list[dict] = Field(default_factory=list)
    avg_chunk_size: float = 0.0
    total_chars: int = 0


class ChunkPreviewRequest(BaseModel):
    """청킹 미리보기 요청."""
    text: str
    profile_id: Optional[str] = None
    chunk_size: Optional[int] = None
    chunk_overlap: Optional[int] = None