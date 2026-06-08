"""조선어 청킹 모듈 - 텍스트를 조선어 문장 기준으로 분할하여 청크 생성"""

from typing import List, Optional
from dataclasses import dataclass


@dataclass
class Chunk:
    """텍스트 청크"""
    text: str
    metadata: dict


def chunk_text(text: str, metadata: dict, chunk_size: int = 700, chunk_overlap: int = 150) -> List[Chunk]:
    """
    텍스트를 조선어 문장 기준으로 청킹합니다.
    문장 단위로 분할한 후, chunk_size가 될 때까지 문장을 누적합니다.

    Args:
        text: 전체 텍스트
        metadata: 원본 메타데이터
        chunk_size: 청크 크기 (글자 수)
        chunk_overlap: 청크 오버랩 (글자 수)

    Returns:
        List[Chunk]: 청크 목록
    """
    # 조선어 문장 분할 수행
    sentences = _split_choson_sentences(text)

    # 문장 단위로 청킹
    chunks_text = _chunk_by_sentences(sentences, chunk_size, chunk_overlap)

    # Chunk 객체 생성 (메타데이터 추가)
    chunks = []
    source = metadata.get("source", "unknown")

    for idx, chunk_text in enumerate(chunks_text):
        chunk_meta = metadata.copy()
        chunk_meta.update({
            "chunk_index": idx,
            "source": source,
            # PDF인 경우 페이지번호, EPUB인 경우 챕터명 보존
            **{k: v for k, v in metadata.items() if k in ["total_pages", "chapters"]},
        })

        chunks.append(Chunk(
            text=chunk_text.strip(),
            metadata=chunk_meta,
        ))

    return chunks


def _chunk_by_sentences(sentences: List[str], chunk_size: int, chunk_overlap: int) -> List[str]:
    """
    문장 목록을 chunk_size/overlap 기준으로 청킹합니다.
    청크 경계는 문장 끝에 맞춥니다.

    Args:
        sentences: 문장 목록
        chunk_size: 청크 크기 (글자 수)
        chunk_overlap: 청크 오버랩 (글자 수)

    Returns:
        List[str]: 청크된 텍스트 목록
    """
    if not sentences:
        return []

    chunks = []
    current_chunk_sentences = []
    current_length = 0

    # Overlap을 위한 문장 추적
    previous_chunk_sentences = []

    for sentence in sentences:
        sentence_len = len(sentence)

        # 현재 청크에 문장 추가 시 크기 초과 체크
        if current_length + sentence_len > chunk_size and current_chunk_sentences:
            # 현재 청크 저장
            chunks.append(" ".join(current_chunk_sentences))

            # 오버랩을 위한 이전 문장들 추적
            # 이전 청크의 마지막 문장들에서부터 오버랩 크기만큼 추적
            overlap_sentences = _get_overlap_sentences(
                current_chunk_sentences,
                chunk_overlap
            )

            # 새로운 청크 시작 (overlap 문장 포함)
            current_chunk_sentences = overlap_sentences
            current_length = sum(len(s) for s in overlap_sentences)

        # 문장 추가 (공백 포함)
        if current_chunk_sentences:
            current_chunk_sentences.append(sentence)
            current_length += 1 + sentence_len  # 문장 사이 공백 + 문장 길이
        else:
            current_chunk_sentences = [sentence]
            current_length = sentence_len

    # 마지막 청크 저장
    if current_chunk_sentences:
        chunks.append(" ".join(current_chunk_sentences))

    return chunks


def _get_overlap_sentences(sentences: List[str], overlap_size: int) -> List[str]:
    """
    이전 청크에서 overlap 크기만큼의 문장을 반환합니다.

    Args:
        sentences: 이전 청크의 문장 목록
        overlap_size: 오버랩 크기 (글자 수)

    Returns:
        List[str]: 오버랩할 문장 목록
    """
    if overlap_size <= 0:
        return []

    # 뒤에서부터 문장을 누적해서 overlap_size에 맞춤
    overlap_sentences = []
    current_overlap = 0

    for sentence in reversed(sentences):
        sentence_len = len(sentence)

        # 공백 포함 계산
        if overlap_sentences:
            if current_overlap + 1 + sentence_len <= overlap_size:
                overlap_sentences.append(sentence)
                current_overlap += 1 + sentence_len
            else:
                break
        else:
            if sentence_len <= overlap_size:
                overlap_sentences.append(sentence)
                current_overlap = sentence_len
            else:
                break

    # 역순으로 되어 있으므로 다시 순서대로
    return list(reversed(overlap_sentences))


def _split_choson_sentences(text: str) -> List[str]:
    """
    조선어 종결어미 기반으로 문장을 분할합니다.

    조선어 종결어미 패턴:
    - 다$ (평서문)
    - 합니다$ (정중체)
    - 하였다$ (과거 평서문)
    - 한다$ (구어체)
    - 하자$ (청유형)
    - 합시다$ (정중 청유형)
    - 것이다$ (사실 강조)
    - 바이다$ (정의형)
    """
    from app.utils.text import split_choson_sentences
    return split_choson_sentences(text)