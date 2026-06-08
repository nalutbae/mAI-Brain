"""mAI-Brain — 도메인별 시맨틱 청킹 프로파일 시스템

도메인 특화 청킹 프로파일을 관리하고, 텍스트를 프로파일에 따라 분할합니다.

프로파일:
- legal (법률): 조문 단위 (제X조 경계 인식)
- paper (논문): 섹션 단위 (Abstract/Method/Results)
- news (뉴스): 기사 단위 (5W1H 구조)
- general (일반): 기본 700토큰 고정 청킹 (현재 기본값)

구조:
- BUILTIN_PROFILES: 내장 기본 프로파일 (수정 불가)
- ProfileStore: 커스텀 프로파일 CRUD (인메모리, P1에서 영속화)
- chunk_with_profile(): 프로파일 기반 청킹 실행
"""

from __future__ import annotations

import re
import logging
from datetime import datetime, timezone
from typing import Optional

from app.models.chunking import (
    ChunkPreview,
    ChunkPreviewRequest,
    ChunkingProfile,
    ChunkingProfileCreate,
    ChunkingProfileUpdate,
    ChunkingStrategy,
)
from app.ingestion.chunker import Chunk, chunk_text

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 내장 프로파일 정의 (수정 불가)
# ---------------------------------------------------------------------------

def _create_builtin_profiles() -> list[ChunkingProfile]:
    """내장 프로파일 목록 생성."""
    now = datetime.now(timezone.utc).isoformat()
    return [
        ChunkingProfile(
            id="builtin_general",
            name="general",
            description="일반 텍스트 — 700토큰 고정 청킹 (기본값)",
            strategy=ChunkingStrategy.FIXED,
            chunk_size=700,
            chunk_overlap=150,
            min_chunk_size=50,
            is_default=True,
            created_at=now,
        ),
        ChunkingProfile(
            id="builtin_legal",
            name="legal",
            description="법률 — 조문 단위 청킹 (제X조 경계 인식)",
            strategy=ChunkingStrategy.ARTICLE,
            chunk_size=1200,
            chunk_overlap=200,
            separator_pattern=r"(?=제\d+조)",
            min_chunk_size=100,
            metadata_fields=["article_number", "chapter"],
            created_at=now,
        ),
        ChunkingProfile(
            id="builtin_paper",
            name="paper",
            description="논문 — 섹션 단위 청킹 (Abstract/Method/Results)",
            strategy=ChunkingStrategy.SECTION,
            chunk_size=1500,
            chunk_overlap=300,
            separator_pattern=r"(?=(?:Abstract|Introduction|Method|Results?|Discussion|Conclusion|References?|초록|서론|방법|결과|논의|결론|참고문헌)[\s:])",
            min_chunk_size=100,
            metadata_fields=["section_name"],
            created_at=now,
        ),
        ChunkingProfile(
            id="builtin_news",
            name="news",
            description="뉴스 — 기사 단위 청킹 (5W1H 구조)",
            strategy=ChunkingStrategy.PARAGRAPH,
            chunk_size=1000,
            chunk_overlap=150,
            separator_pattern=r"\n\s*\n",
            min_chunk_size=80,
            metadata_fields=["paragraph_index"],
            created_at=now,
        ),
    ]


# ---------------------------------------------------------------------------
# 프로파일 저장소 (인메모리, P1에서 영속화)
# ---------------------------------------------------------------------------

class ProfileStore:
    """청킹 프로파일 저장소.

    내장 프로파일(builtin_*)은 읽기 전용이며,
    커스텀 프로파일은 CRUD가 가능합니다.
    """

    def __init__(self) -> None:
        self._profiles: dict[str, ChunkingProfile] = {}
        for p in _create_builtin_profiles():
            self._profiles[p.id] = p

    def list_profiles(self) -> list[ChunkingProfile]:
        """모든 프로파일 목록 반환."""
        return list(self._profiles.values())

    def get_profile(self, profile_id: str) -> Optional[ChunkingProfile]:
        """ID로 프로파일 조회."""
        return self._profiles.get(profile_id)

    def get_default(self) -> ChunkingProfile:
        """기본 프로파일 반환."""
        default = next(
            (p for p in self._profiles.values() if p.is_default),
            None,
        )
        if default is None:
            raise ValueError("기본 프로파일이 설정되지 않았습니다")
        return default

    def get_by_name(self, name: str) -> Optional[ChunkingProfile]:
        """이름으로 프로파일 조회."""
        return next(
            (p for p in self._profiles.values() if p.name == name),
            None,
        )

    def create_profile(self, data: ChunkingProfileCreate) -> ChunkingProfile:
        """커스텀 프로파일 생성.

        내장 프로파일과 이름이 중복되면 생성 불가.

        Args:
            data: 프로파일 생성 요청 데이터

        Returns:
            생성된 프로파일

        Raises:
            ValueError: 이름 중복 시
        """
        # 이름 중복 확인
        if self.get_by_name(data.name):
            raise ValueError(f"프로파일 이름이 이미 존재합니다: {data.name}")

        now = datetime.now(timezone.utc).isoformat()
        profile = ChunkingProfile(
            id=f"profile_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}",
            name=data.name,
            description=data.description,
            strategy=data.strategy,
            chunk_size=data.chunk_size,
            chunk_overlap=data.chunk_overlap,
            separator_pattern=data.separator_pattern,
            min_chunk_size=data.min_chunk_size,
            metadata_fields=data.metadata_fields,
            is_default=False,
            created_at=now,
        )
        self._profiles[profile.id] = profile
        logger.info("프로파일 생성: %s (id=%s, strategy=%s)", profile.name, profile.id, profile.strategy)
        return profile

    def update_profile(
        self, profile_id: str, data: ChunkingProfileUpdate
    ) -> Optional[ChunkingProfile]:
        """커스텀 프로파일 수정.

        내장 프로파일(builtin_*)은 수정 불가.

        Args:
            profile_id: 프로파일 ID
            data: 수정할 필드

        Returns:
            수정된 프로파일 (없으면 None)

        Raises:
            ValueError: 내장 프로파일 수정 시도
        """
        profile = self._profiles.get(profile_id)
        if profile is None:
            return None

        if profile_id.startswith("builtin_"):
            raise ValueError(f"내장 프로파일은 수정할 수 없습니다: {profile.name}")

        # 이름 중복 확인 (변경하는 경우)
        if data.name is not None and data.name != profile.name:
            if self.get_by_name(data.name):
                raise ValueError(f"프로파일 이름이 이미 존재합니다: {data.name}")

        update_data = data.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            setattr(profile, key, value)

        logger.info("프로파일 수정: %s (id=%s)", profile.name, profile.id)
        return profile

    def delete_profile(self, profile_id: str) -> bool:
        """커스텀 프로파일 삭제.

        내장 프로파일(builtin_*)은 삭제 불가.
        기본 프로파일도 삭제 불가 (다른 프로파일을 기본으로 먼저 설정해야 함).

        Args:
            profile_id: 프로파일 ID

        Returns:
            삭제 성공 여부

        Raises:
            ValueError: 내장 프로파일 삭제 시도 또는 기본 프로파일 삭제 시도
        """
        profile = self._profiles.get(profile_id)
        if profile is None:
            return False

        if profile_id.startswith("builtin_"):
            raise ValueError(f"내장 프로파일은 삭제할 수 없습니다: {profile.name}")
        if profile.is_default:
            raise ValueError("기본 프로파일은 삭제할 수 없습니다. 다른 프로파일을 먼저 기본으로 설정하세요.")

        del self._profiles[profile_id]
        logger.info("프로파일 삭제: %s (id=%s)", profile.name, profile_id)
        return True

    def set_default(self, profile_id: str) -> Optional[ChunkingProfile]:
        """기본 프로파일 변경.

        Args:
            profile_id: 기본으로 설정할 프로파일 ID

        Returns:
            변경된 기본 프로파일 (없으면 None)
        """
        profile = self._profiles.get(profile_id)
        if profile is None:
            return None

        # 기존 기본 해제
        for p in self._profiles.values():
            p.is_default = False

        # 새 기본 설정
        profile.is_default = True
        logger.info("기본 프로파일 변경: %s (id=%s)", profile.name, profile_id)
        return profile


# 전역 싱글톤
_store: Optional[ProfileStore] = None


def get_profile_store() -> ProfileStore:
    """ProfileStore 싱글톤 반환."""
    global _store
    if _store is None:
        _store = ProfileStore()
    return _store


# ---------------------------------------------------------------------------
# 프로파일 기반 청킹 엔진
# ---------------------------------------------------------------------------

# 법률 조문 분할 패턴
_LEGAL_ARTICLE_PATTERN = re.compile(r"(?=제\d+조)", re.MULTILINE)

# 논문 섹션 분할 패턴
_PAPER_SECTION_PATTERN = re.compile(
    r"(?=(?:Abstract|Introduction|Method|Results?|Discussion|Conclusion|References?"
    r"|초록|서론|방법|결과|논의|결론|참고문헌)[\s:.\n])",
    re.IGNORECASE,
)

# 뉴스 단락 분할 패턴 (빈 줄)
_NEWS_PARAGRAPH_PATTERN = re.compile(r"\n\s*\n")


def chunk_with_profile(
    text: str,
    metadata: dict,
    profile: Optional[ChunkingProfile] = None,
) -> list[Chunk]:
    """프로파일 기반 청킹 실행.

    프로파일의 strategy와 separator_pattern에 따라 텍스트를 분할합니다.
    프로파일이 없으면 기본 general 프로파일을 사용합니다.

    Args:
        text: 원본 텍스트
        metadata: 원본 메타데이터
        profile: 적용할 청킹 프로파일 (None이면 기본값)

    Returns:
        프로파일이 적용된 청크 목록
    """
    store = get_profile_store()

    if profile is None:
        profile = store.get_default()

    strategy = profile.strategy

    if strategy == ChunkingStrategy.FIXED:
        # 기존 chunk_text 함수 위임 (general 기본 동작)
        return chunk_text(
            text,
            metadata,
            chunk_size=profile.chunk_size,
            chunk_overlap=profile.chunk_overlap,
        )

    elif strategy == ChunkingStrategy.ARTICLE:
        return _chunk_by_articles(text, metadata, profile)

    elif strategy == ChunkingStrategy.SECTION:
        return _chunk_by_sections(text, metadata, profile)

    elif strategy == ChunkingStrategy.PARAGRAPH:
        return _chunk_by_paragraphs(text, metadata, profile)

    elif strategy == ChunkingStrategy.SENTENCE:
        return _chunk_by_sentences(text, metadata, profile)

    else:
        logger.warning("알 수 없는 청킹 전략: %s, 기본값 사용", strategy)
        return chunk_text(
            text,
            metadata,
            chunk_size=profile.chunk_size,
            chunk_overlap=profile.chunk_overlap,
        )


def _split_by_pattern(text: str, pattern: str | re.Pattern) -> list[str]:
    """정규식 패턴으로 텍스트를 섹션으로 분할.

    Args:
        text: 원본 텍스트
        pattern: 분할 정규식 패턴

    Returns:
        분할된 섹션 목록 (빈 섹션 제외)
    """
    if isinstance(pattern, str):
        if pattern:
            pattern = re.compile(pattern, re.MULTILINE)
        else:
            # 패턴이 없으면 전체 텍스트를 하나의 섹션으로
            return [text] if text.strip() else []

    sections = pattern.split(text)
    # 빈 섹션 제거
    return [s for s in sections if s.strip()]


def _merge_small_chunks(
    chunks: list[dict],
    min_size: int,
    max_size: int,
    overlap: int,
) -> list[dict]:
    """작은 청크를 병합하고 큰 청크를 분할합니다.

    Args:
        chunks: 청크 딕셔너리 목록 (text, metadata 키 포함)
        min_size: 최소 청크 크기 (이보다 작으면 다음 청크와 병합)
        max_size: 최대 청크 크기 (이보다 크면 분할)
        overlap: 청크 오버랩 크기

    Returns:
        병합/분할된 청크 목록
    """
    if not chunks:
        return []

    result = []
    carry = ""

    for chunk in chunks:
        text = carry + (" " if carry else "") + chunk["text"] if carry else chunk["text"]
        carry = ""

        if len(text) < min_size:
            # 너무 작으면 다음 청크와 병합을 위해 보류
            carry = text
            continue

        if len(text) > max_size:
            # 너무 크면 분할
            sub_chunks = _split_large_text(text, max_size, overlap)
            for sub in sub_chunks:
                result.append({
                    **chunk,
                    "text": sub,
                })
        else:
            result.append({
                **chunk,
                "text": text,
            })

    # 남은 carry 처리
    if carry:
        if result:
            # 마지막 청크에 병합
            result[-1]["text"] += " " + carry
        else:
            # 청크가 없으면 그대로 추가
            base = chunks[0] if chunks else {}
            result.append({
                **base,
                "text": carry,
            })

    return result


def _split_large_text(text: str, max_size: int, overlap: int) -> list[str]:
    """큰 텍스트를 문장 경계에서 분할합니다.

    Args:
        text: 분할할 텍스트
        max_size: 최대 청크 크기
        overlap: 오버랩 크기

    Returns:
        분할된 텍스트 목록
    """
    from app.utils.text import split_choson_sentences

    sentences = split_choson_sentences(text)

    chunks: list[str] = []
    current = ""

    for sentence in sentences:
        if current and len(current) + len(sentence) + 1 > max_size:
            chunks.append(current.strip())
            # 오버랩 적용
            if overlap > 0 and len(current) > overlap:
                current = current[-overlap:] + " " + sentence
            else:
                current = sentence
        else:
            current = (current + " " + sentence).strip() if current else sentence

    if current.strip():
        chunks.append(current.strip())

    return chunks if chunks else [text[:max_size]]


def _chunk_by_articles(
    text: str, metadata: dict, profile: ChunkingProfile
) -> list[Chunk]:
    """법률 조문 단위 청킹.

    '제X조' 패턴으로 조문을 식별하고, 각 조를 청크로 생성합니다.
    짧은 조는 다음 조와 병합합니다.
    """
    pattern = profile.separator_pattern or r"(?=제\d+조)"
    sections = _split_by_pattern(text, pattern)

    # 각 조문에 메타데이터 부여
    raw_chunks = []
    for i, section in enumerate(sections):
        article_match = re.search(r"제(\d+)조", section)
        article_number = article_match.group(1) if article_match else str(i + 1)
        raw_chunks.append({
            "text": section.strip(),
            "metadata": {
                **metadata,
                "chunk_index": i,
                "article_number": f"제{article_number}조",
                "chunking_strategy": "article",
            },
        })

    # 병합/분할 적용
    merged = _merge_small_chunks(
        raw_chunks,
        min_size=profile.min_chunk_size,
        max_size=profile.chunk_size,
        overlap=profile.chunk_overlap,
    )

    # 인덱스 재부여
    return [
        Chunk(text=c["text"], metadata={**c.get("metadata", metadata), "chunk_index": i})
        for i, c in enumerate(merged)
    ]


def _chunk_by_sections(
    text: str, metadata: dict, profile: ChunkingProfile
) -> list[Chunk]:
    """논문 섹션 단위 청킹.

    Abstract/Method/Results 등 섹션 헤더로 분할합니다.
    """
    pattern = profile.separator_pattern or r"(?=(?:Abstract|Introduction|Method|Results?|Discussion|Conclusion|References?)[\s:])"
    sections = _split_by_pattern(text, pattern)

    raw_chunks = []
    for i, section in enumerate(sections):
        # 섹션 이름 추출
        first_line = section.strip().split("\n")[0] if section.strip() else ""
        section_name = first_line.strip().rstrip(":").strip()[:50] if first_line else f"Section {i+1}"
        raw_chunks.append({
            "text": section.strip(),
            "metadata": {
                **metadata,
                "chunk_index": i,
                "section_name": section_name,
                "chunking_strategy": "section",
            },
        })

    merged = _merge_small_chunks(
        raw_chunks,
        min_size=profile.min_chunk_size,
        max_size=profile.chunk_size,
        overlap=profile.chunk_overlap,
    )

    return [
        Chunk(text=c["text"], metadata={**c.get("metadata", metadata), "chunk_index": i})
        for i, c in enumerate(merged)
    ]


def _chunk_by_paragraphs(
    text: str, metadata: dict, profile: ChunkingProfile
) -> list[Chunk]:
    """뉴스/기사 단락 단위 청킹.

    빈 줄로 단락을 분할하고, 짧은 단락은 병합합니다.
    """
    pattern = profile.separator_pattern or r"\n\s*\n"
    sections = _split_by_pattern(text, pattern)

    raw_chunks = []
    for i, section in enumerate(sections):
        raw_chunks.append({
            "text": section.strip(),
            "metadata": {
                **metadata,
                "chunk_index": i,
                "paragraph_index": i,
                "chunking_strategy": "paragraph",
            },
        })

    merged = _merge_small_chunks(
        raw_chunks,
        min_size=profile.min_chunk_size,
        max_size=profile.chunk_size,
        overlap=profile.chunk_overlap,
    )

    return [
        Chunk(text=c["text"], metadata={**c.get("metadata", metadata), "chunk_index": i})
        for i, c in enumerate(merged)
    ]


def _chunk_by_sentences(
    text: str, metadata: dict, profile: ChunkingProfile
) -> list[Chunk]:
    """문장 단위 청킹.

    조선어 문장 분할기를 사용하여 문장 단위로 청킹합니다.
    오버랩 없이 문장 단위로 누적합니다.
    """
    from app.utils.text import split_choson_sentences

    sentences = split_choson_sentences(text)

    raw_chunks = []
    current_text = ""

    for i, sentence in enumerate(sentences):
        if current_text and len(current_text) + len(sentence) + 1 > profile.chunk_size:
            raw_chunks.append({
                "text": current_text.strip(),
                "metadata": {
                    **metadata,
                    "chunk_index": len(raw_chunks),
                    "chunking_strategy": "sentence",
                },
            })
            current_text = sentence
        else:
            current_text = (current_text + " " + sentence).strip() if current_text else sentence

    if current_text.strip():
        raw_chunks.append({
            "text": current_text.strip(),
            "metadata": {
                **metadata,
                "chunk_index": len(raw_chunks),
                "chunking_strategy": "sentence",
            },
        })

    merged = _merge_small_chunks(
        raw_chunks,
        min_size=profile.min_chunk_size,
        max_size=profile.chunk_size,
        overlap=profile.chunk_overlap,
    )

    return [
        Chunk(text=c["text"], metadata={**c.get("metadata", metadata), "chunk_index": i})
        for i, c in enumerate(merged)
    ]


def preview_chunks(request: ChunkPreviewRequest) -> ChunkPreview:
    """청킹 미리보기.

    텍스트를 프로파일(또는 커스텀 파라미터)로 청킹한 결과를 반환합니다.
    실제 인덱싱에 영향을 주지 않는 읽기 전용 작업입니다.

    Args:
        request: 미리보기 요청 (텍스트, 프로파일 ID 또는 커스텀 파라미터)

    Returns:
        청킹 미리보기 결과 (최대 10개 청크 + 통계)
    """
    store = get_profile_store()

    # 프로파일 결정
    if request.profile_id:
        profile = store.get_profile(request.profile_id)
        if profile is None:
            raise ValueError(f"프로파일을 찾을 수 없습니다: {request.profile_id}")
    else:
        # 커스텀 파라미터로 임시 프로파일 생성
        profile = ChunkingProfile(
            id="preview",
            name="preview",
            strategy=ChunkingStrategy.FIXED,
            chunk_size=request.chunk_size or 700,
            chunk_overlap=request.chunk_overlap or 150,
        )

    # 청킹 실행
    metadata = {"source": "preview"}
    chunks = chunk_with_profile(request.text, metadata, profile)

    # 통계 계산
    total_chars = sum(len(c.text) for c in chunks)
    avg_size = total_chars / len(chunks) if chunks else 0

    # 미리보기는 최대 10개 청크만 반환
    preview_chunks = chunks[:10]
    preview_data = [
        {
            "index": c.metadata.get("chunk_index", i),
            "text": c.text[:300] + ("..." if len(c.text) > 300 else ""),
            "full_length": len(c.text),
            "metadata": c.metadata,
        }
        for i, c in enumerate(preview_chunks)
    ]

    return ChunkPreview(
        profile_id=profile.id,
        total_chunks=len(chunks),
        chunks=preview_data,
        avg_chunk_size=round(avg_size, 1),
        total_chars=total_chars,
    )