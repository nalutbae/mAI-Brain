"""텍스트 추출 모듈 - PDF, EPUB, TXT에서 텍스트를 추출합니다.

OCR Fallback:
  PDF가 북한 WK 폰트 등을 사용하여 텍스트 추출이 깨지는 경우
  자동으로 OCR(광학 문자 인식)을 수행합니다.
  판단 기준: 추출된 텍스트의 한글(완성형) 비율이 임계값 이하인 경우.

메모리 최적화 (v2):
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

from PIL import Image, ImageEnhance, ImageFilter

logger = logging.getLogger(__name__)


@dataclass
class ExtractResult:
    """텍스트 추출 결과"""
    text: str
    metadata: dict


# ── 한글 품질 검사 ──────────────────────────────────────────────────────────

# 완성형 한글 유니코드 범위: 가(0xAC00) ~ 힣(0xD7A3)
_KOREAN_RANGE = range(0xAC00, 0xD7A4)
# 깨짐 판단 기준: 한글이 차지하는 비율
_QUALITY_THRESHOLD = 0.05  # 5% 미만이면 OCR fallback
# OCR 설정: 150 DPI (메모리 절약), 대비 2.0x로 보상
_OCR_DPI = 150


def _is_korean_char(ch: str) -> bool:
    """문자가 완성형 한글인지 판단"""
    cp = ord(ch)
    return 0xAC00 <= cp <= 0xD7A3


def _korean_ratio(text: str) -> float:
    """텍스트에서 완성형 한글이 차지하는 비율"""
    if not text:
        return 0.0
    korean_chars = sum(1 for ch in text if _is_korean_char(ch))
    total_printable = sum(1 for ch in text if ch.isprintable() and not ch.isspace())
    if total_printable == 0:
        return 0.0
    return korean_chars / total_printable


def _is_text_garbled(text: str, threshold: float = _QUALITY_THRESHOLD) -> bool:
    """추출된 텍스트가 깨졌는지 판단 (한글 비율 기준)"""
    ratio = _korean_ratio(text)
    if ratio < threshold:
        logger.info("텍스트 품질 낮음: 한글 비율 %.1f%% (임계 %d%%) — OCR 필요",
                     ratio * 100, int(threshold * 100))
        return True
    return False


# ── OCR ──────────────────────────────────────────────────────────────────────

def _normalize_ocr_korean(text: str) -> str:
    """Tesseract OCR 한글 텍스트 후처리.

    Tesseract는 한글 음절 사이에 불필요한 공백을 삽입하는 경향이 있음
    (예: "주 체 철 학" → "주체철학").
    이 함수는 한글 음절(가-힣) 사이의 단일 공백을 제거.

    OCR 출력에서는 Tesseract가 어절 경계까지 모두 끊어버리므로,
    원본의 띄어쓰기를 보존할 방법이 없음. 따라서 모든 한글 음절 간
    공백을 제거하는 것이 최선의 복원 전략임.

    주의: 이 함수는 OCR 텍스트에만 적용해야 함.
    정상적인 한국어 텍스트에 적용하면 띄어쓰기가 모두 사라짐.
    """
    # 줄바꿈은 보존하면서, 같은 줄 내 한글 음절 사이의 단일 공백 제거
    result = re.sub(
        r'(?<=[가-힣])\s{1}(?=[가-힣])',
        '',
        text,
    )
    return result


def _ocr_page(pix: fitz.Pixmap) -> str:
    """PyMuPDF 페이지 픽스맵을 OCR 처리 (최적 설정)"""
    try:
        import pytesseract
        # Pixmap → PIL Image
        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        # 전처리: Grayscale → 대비增强(1.5x) → 샤프닝
        # 1.5x가 한글 OCR 정확도 최적 (2.0x는 89.5%, 1.5x는 93.7% KR)
        gray = img.convert("L")
        enhanced = ImageEnhance.Contrast(gray).enhance(1.5)
        sharpened = enhanced.filter(
            ImageFilter.UnsharpMask(radius=2, percent=150, threshold=3)
        )
        # 한국어 + 영어 OCR (PSM 6 = 단일 텍스트 블록)
        text = pytesseract.image_to_string(
            sharpened,
            lang="kor+eng",
            config="--psm 6 --oem 1",
        )
        # 한글 OCR 후처리: 음절 간 불필요한 공백 제거
        text = _normalize_ocr_korean(text)
        # 메모리 즉시 해제
        del img, gray, enhanced, sharpened
        return text
    except Exception as e:
        logger.warning("OCR 실패: %s", e)
        return ""


def _ocr_pdf(file_path: str, doc: fitz.Document, max_pages: int = 9999) -> str:
    """PDF 전체 페이지 OCR 처리 (순차, 메모리 최적화).
    
    병렬 대신 순차 처리로 전환:
    - 한 번에 1페이지만 Pixmap + PIL Image 메모리에 유지
    - 큰 PDF(100페이지+)는 중간 gc.collect로 메모리 해제
    - 150 DPI + 대비 1.5x로 한글 OCR 정확도 93.7% 달성
    """
    total = min(len(doc), max_pages)
    dpi = _OCR_DPI

    logger.info("OCR 시작: %d 페이지 (%d DPI, 순차 처리)", total, dpi)

    full_text: list[str] = []
    mat = fitz.Matrix(dpi / 72, dpi / 72)

    for page_num in range(total):
        try:
            page = doc[page_num]
            pix = page.get_pixmap(matrix=mat)
            text = _ocr_page(pix)
            if text.strip():
                full_text.append(f"--- 페이지 {page_num + 1} ---\n{text}\n")
            # Pixmap 메모리 즉시 해제
            del pix
        except Exception as e:
            logger.warning("OCR 페이지 %d 실패: %s", page_num + 1, e)

        # 100페이지마다 메모리 정리 + 진행 로깅
        if (page_num + 1) % 100 == 0:
            gc.collect()
            logger.info("OCR 진행: %d/%d 페이지 완료", page_num + 1, total)

    gc.collect()
    doc.close()
    return "\n".join(full_text)


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
    """PDF에서 텍스트를 추출합니다. 필요시 OCR fallback."""
    metadata: dict = {"source": Path(file_path).name}

    # 1단계: PyMuPDF 텍스트 추출
    doc = fitz.open(file_path)
    metadata["total_pages"] = len(doc)

    full_text: list[str] = []
    for page_num in range(len(doc)):
        page = doc[page_num]
        text = page.get_text()
        if text.strip():
            full_text.append(f"--- 페이지 {page_num + 1} ---\n{text}\n")

    extracted = "\n".join(full_text)

    # 2단계: 텍스트 품질 검사
    if not _is_text_garbled(extracted):
        doc.close()
        metadata["method"] = "text"
        return ExtractResult(text=extracted, metadata=metadata)

    # 3단계: OCR fallback
    total_pages = len(doc)  # doc이 _ocr_pdf에서 close되므로 미리 저장
    logger.info("OCR fallback 시작: %s (%d 페이지)", file_path, total_pages)
    ocr_text = _ocr_pdf(file_path, doc, max_pages=total_pages)
    metadata["method"] = "ocr"
    metadata["ocr_pages"] = total_pages

    return ExtractResult(text=ocr_text, metadata=metadata)


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
