"""텍스트 추출 모듈 - PDF, EPUB, TXT에서 텍스트를 추출합니다.

OCR 파이프라인 (v3 — surya-ocr 통합):
  1. PyMuPDF로 텍스트 추출 시도
  2. 한글 비율 검사 → 깨졌으면 OCR 활성화
  3. surya-ocr (한국어+영어) 우선, tesseract 폴백
  4. 표 추출: camelot (텍스트 PDF) → img2table (스캔 PDF)
  5. 결과: 텍스트 + 표 마크다운 → 기존 청킹 파이프라인

레거시 OCR (v2 — pytesseract only):
  기존 _ocr_pdf / _ocr_page 함수는 app.core.ocr로 이전되었습니다.
  하위 호환성을 위해 본 모듈에서 재-export합니다.

메모리 최적화:
  - OCR을 순차 처리로 전환 (병렬 대신)하여 메모리 사용량 제어
  - 150 DPI로 낮추고 대비를 1.5x로 설정 (2.0x보다 한글 정확도 높음: 93.7% vs 89.5%)
  - Pixmap/PIL Image를 즉시 해제 (gc.collect)
  - 큰 PDF(100페이지+)는 청크 단위로 처리
"""

from pathlib import Path
from typing import Optional
from dataclasses import dataclass
import re
import io
import gc
import logging

import chardet
import fitz  # PyMuPDF
from ebooklib import epub as _epub_mod

from app.core.ocr import (
    ocr_document,
    ocr_pdf_to_text,
    _is_text_garbled as is_text_garbled,
    _korean_ratio as korean_ratio,
    _normalize_ocr_korean as normalize_ocr_korean,
    OcrDocumentResult,
)

logger = logging.getLogger(__name__)


@dataclass
class ExtractResult:
    """텍스트 추출 결과"""
    text: str
    metadata: dict


# ── 한글 품질 검사 ──────────────────────────────────────────────────────────
# ── 한글 품질 검사 ──────────────────────────────────────────────────────────
# NOTE: 핵심 로직은 app.core.ocr로 이전되었습니다.
# 하위 호환성을 위해 재-export합니다.

_KOREAN_RANGE = range(0xAC00, 0xD7A4)
_QUALITY_THRESHOLD = 0.05  # 5% 미만이면 OCR fallback


def _is_korean_char(ch: str) -> bool:
    """문자가 완성형 한글인지 판단"""
    return ord(ch) in _KOREAN_RANGE


def _korean_ratio(text: str) -> float:
    """텍스트에서 완성형 한글이 차지하는 비율"""
    return korean_ratio(text)


def _is_text_garbled(text: str, threshold: float = _QUALITY_THRESHOLD) -> bool:
    """추출된 텍스트가 깨졌는지 판단 (한글 비율 기준)"""
    return is_text_garbled(text, threshold)


def _normalize_ocr_korean(text: str) -> str:
    """OCR 한글 텍스트 후처리 — 음절 간 불필요한 공백 제거"""
    return normalize_ocr_korean(text)


# ── OCR (레거시 — app.core.ocr로 위임) ─────────────────────────────────────

def _ocr_page(pix: fitz.Pixmap) -> str:
    """PyMuPDF 페이지 픽스맵을 OCR 처리 (레거시 — app.core.ocr 사용 권장)"""
    from app.core.ocr import _tesseract_ocr_page, _preprocess_for_ocr
    from PIL import Image as PILImage
    img = PILImage.frombytes("RGB", [pix.width, pix.height], pix.samples)
    return _tesseract_ocr_page(img)


def _ocr_pdf(file_path: str, doc: fitz.Document, max_pages: int = 9999) -> str:
    """PDF 전체 페이지 OCR 처리 (레거시 — app.core.ocr.ocr_document 사용 권장)"""
    return ocr_pdf_to_text(file_path)


# ── 메인 추출 함수 ──────────────────────────────────────────────────────────

def extract_text(file_path: str) -> ExtractResult:
    """
    파일에서 텍스트를 추출합니다.

    PDF의 경우:
    1. PyMuPDF로 텍스트 추출
    2. 한글 비율 검사 → 깨졌으면 OCR fallback

    Args:
        file_path: 파일 경로

    Returns:
        ExtractResult: 추출된 텍스트와 메타데이터

    Raises:
        ValueError: 지원하지 않는 파일 형식
    """
    path = Path(file_path)

    if not path.exists():
        raise FileNotFoundError(f"파일을 찾을 수 없습니다: {file_path}")

    suffix = path.suffix.lower()

    if suffix == ".pdf":
        return _extract_pdf(file_path)
    elif suffix == ".epub":
        return _extract_epub(file_path)
    elif suffix == ".txt":
        return _extract_txt(file_path)
    else:
        raise ValueError(f"지원하지 않는 파일 형식입니다: {suffix} (PDF, EPUB, TXT만 지원)")


def _extract_pdf(file_path: str) -> ExtractResult:
    """PDF에서 텍스트를 추출합니다.

    파이프라인:
    1. PyMuPDF 텍스트 추출 시도
    2. 한글 비율 검사 → 깨졌으면 app.core.ocr 파이프라인 활성화
    3. surya-ocr (한국어+영어) 우선, tesseract 폴백
    4. 표 추출: camelot → img2table
    """
    metadata: dict = {"source": Path(file_path).name}

    # 1단계: PyMuPDF 텍스트 추출
    doc = fitz.open(file_path)
    metadata["total_pages"] = len(doc)

    full_text: list[str] = []
    for page_num in range(len(doc)):
        page = doc[page_num]
        page_text = str(page.get_text() or "")
        if page_text and page_text.strip():
            full_text.append(f"--- 페이지 {page_num + 1} ---\n{page_text}\n")

    extracted = "\n".join(full_text)

    # 2단계: 텍스트 품질 검사
    if not _is_text_garbled(extracted):
        doc.close()
        metadata["method"] = "text"
        return ExtractResult(text=extracted, metadata=metadata)

    # 3단계: OCR 파이프라인 (surya → tesseract, 표 추출 포함)
    doc.close()
    logger.info("OCR 파이프라인 시작: %s", file_path)
    ocr_result: OcrDocumentResult = ocr_document(file_path)

    metadata["method"] = ocr_result.method
    metadata["ocr_pages"] = ocr_result.metadata.get("ocr_pages", 0)
    metadata["total_pages"] = ocr_result.total_pages

    # OCR 결과의 전체 텍스트 반환 (페이지 구분 + 표 마크다운 포함)
    return ExtractResult(text=ocr_result.full_text, metadata=metadata)


def _extract_epub(file_path: str) -> ExtractResult:
    """EPUB에서 텍스트를 추출합니다.

    ebooklib 0.20+에서 ITEM_DOCUMENT 상수가 제거되었으므로
    isinstance(item, EpubHtml)로 문서 항목을 필터링합니다.
    EpubHtml의 get_type()은 정수 9를 반환합니다.
    """
    book = _epub_mod.read_epub(file_path)
    EpubHtml = _epub_mod.EpubHtml

    full_text: list[str] = []
    metadata: dict = {
        "source": Path(file_path).name,
        "chapters": [],
    }

    for item in book.get_items():
        # ebooklib 0.20+: ITEM_DOCUMENT 상수 제거, isinstance로 대체
        # EpubHtml이 실제 텍스트 콘텐츠(XHTML)를 담음
        # EpubNav도 XHTML이지만 목차(nav)용이므로 제외
        if isinstance(item, EpubHtml) and not isinstance(item, _epub_mod.EpubNav):
            chapter_name = item.get_name()
            metadata["chapters"].append(chapter_name)

            content = item.get_content().decode("utf-8", errors="ignore")

            # HTML 태그 제거 (단순 구현)
            text_only = re.sub(r"<[^>]+>", " ", content)
            text_only = re.sub(r"\s+", " ", text_only).strip()

            if text_only:
                full_text.append(f"--- 챕터: {chapter_name} ---\n{text_only}\n")

    if not full_text:
        logger.warning("EPUB에서 추출된 텍스트 없음: %s", file_path)

    return ExtractResult(
        text="\n".join(full_text),
        metadata=metadata,
    )


def _extract_txt(file_path: str) -> ExtractResult:
    """TXT에서 텍스트를 추출합니다. 인코딩을 자동 감지합니다."""
    with open(file_path, "rb") as f:
        raw_data = f.read()

    # 인코딩 자동 감지
    detected = chardet.detect(raw_data)
    encoding = detected.get("encoding", "utf-8")
    confidence = detected.get("confidence", 0)

    if confidence < 0.7:
        encoding = "utf-8"

    try:
        text = raw_data.decode(encoding)
    except UnicodeDecodeError:
        try:
            text = raw_data.decode("cp949")
        except UnicodeDecodeError:
            text = raw_data.decode("euc-kr", errors="ignore")

    return ExtractResult(
        text=text,
        metadata={
            "source": Path(file_path).name,
            "encoding": encoding,
        },
    )
