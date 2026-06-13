"""mAI-Brain — 한국어 OCR + 레이아웃 분석 파이프라인

PDF/이미지에서 텍스트, 표, 레이아웃을 추출합니다.

지원 OCR 엔진:
  - surya-ocr: 한국어 지원 오픈소스 OCR (기본). 레이아웃 분석 내장.
  - tesseract: 기존 pytesseract 폴백 (surya 미설치 시)

파이프라인:
  1. PDF → 페이지 이미지 렌더링 (config DPI)
  2. surya 레이아웃 분석 → 표/그림/단락 영역 감지
  3. surya OCR → 텍스트 인식 (한국어 + 영어)
  4. 표 영역 → camelot/img2table으로 표 구조 추출 (선택)
  5. 텍스트 + 표 마크다운 → 기존 청킹 파이프라인으로 전달

메모리 관리:
  - surya 모델은 싱글톤으로 로드 (최초 1회)
  - MPS(Apple Silicon) / CUDA(NVIDIA) / CPU 자동 감지
  - 대용량 PDF는 청크 단위 처리 + gc.collect()
"""

from __future__ import annotations

import gc
import io
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import fitz  # PyMuPDF
from PIL import Image, ImageEnhance, ImageFilter

from app.config import get_settings

logger = logging.getLogger(__name__)


# ── 데이터 클래스 ────────────────────────────────────────────────────────────

@dataclass
class OcrPageResult:
    """단일 페이지 OCR 결과"""
    page_number: int  # 1-based
    text: str  # 추출된 텍스트
    method: str = "unknown"  # "surya" | "tesseract" | "text" | "none"
    tables: list[str] = field(default_factory=list)  # 표 마크다운 리스트
    has_ocr: bool = False  # OCR을 사용했는지 여부


@dataclass
class OcrDocumentResult:
    """문서 전체 OCR 결과"""
    pages: list[OcrPageResult] = field(default_factory=list)
    total_pages: int = 0
    method: str = "unknown"  # 전체 문서의 대표 처리 방식
    metadata: dict = field(default_factory=dict)

    @property
    def full_text(self) -> str:
        """모든 페이지 텍스트를 합친 전체 텍스트"""
        parts = []
        for page in self.pages:
            if page.text.strip():
                parts.append(f"--- 페이지 {page.page_number} ---\n{page.text}")
            for table_md in page.tables:
                parts.append(table_md)
        return "\n\n".join(parts)


# ── Surya OCR 엔진 ──────────────────────────────────────────────────────────

_surya_ocr = None
_surya_layout = None
_surya_available: Optional[bool] = None


def _check_surya_available() -> bool:
    """surya-ocr 패키지 가용성 확인"""
    global _surya_available
    if _surya_available is not None:
        return _surya_available
    try:
        from surya.ocr import run_ocr  # noqa: F401
        from surya.layout import run_layout  # noqa: F401
        _surya_available = True
        logger.info("surya-ocr 사용 가능")
    except ImportError:
        _surya_available = False
        logger.warning("surya-ocr 미설치 — tesseract로 폴백합니다. 설치: pip install surya-ocr")
    return _surya_available


def _get_surya_ocr_engine():
    """surya OCR 모델 싱글톤 로드"""
    global _surya_ocr
    if _surya_ocr is not None:
        return _surya_ocr
    try:
        from surya.ocr import run_ocr
        from surya.model.detection.model import load_model as load_det_model
        from surya.model.detection.processor import load_processor as load_det_processor
        from surya.model.recognition.model import load_model as load_rec_model
        from surya.model.recognition.processor import load_processor as load_rec_processor

        logger.info("surya OCR 모델 로딩 중...")
        det_processor = load_det_processor()
        det_model = load_det_model()
        rec_processor = load_rec_processor()
        rec_model = load_rec_model()
        _surya_ocr = {
            "run_ocr": run_ocr,
            "det_processor": det_processor,
            "det_model": det_model,
            "rec_processor": rec_processor,
            "rec_model": rec_model,
        }
        logger.info("surya OCR 모델 로딩 완료")
        return _surya_ocr
    except Exception as e:
        logger.error("surya OCR 모델 로딩 실패: %s", e)
        _surya_ocr = None
        raise


def _get_surya_layout_engine():
    """surya 레이아웃 분석 모델 싱글톤 로드"""
    global _surya_layout
    if _surya_layout is not None:
        return _surya_layout
    try:
        from surya.layout import run_layout
        from surya.model.layout_detector import load_layout_detector

        logger.info("surya 레이아웃 모델 로딩 중...")
        layout_model = load_layout_detector()
        _surya_layout = {
            "run_layout": run_layout,
            "layout_model": layout_model,
        }
        logger.info("surya 레이아웃 모델 로딩 완료")
        return _surya_layout
    except Exception as e:
        logger.error("surya 레이아웃 모델 로딩 실패: %s", e)
        _surya_layout = None
        raise


# ── 이미지 전처리 ────────────────────────────────────────────────────────────

def _render_page_image(page: fitz.Page, dpi: int = 200) -> Image.Image:
    """PyMuPDF 페이지를 PIL Image로 렌더링"""
    mat = fitz.Matrix(dpi / 72, dpi / 72)
    pix = page.get_pixmap(matrix=mat)
    img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
    del pix
    return img


def _preprocess_for_ocr(img: Image.Image) -> Image.Image:
    """OCR 정확도 향상을 위한 이미지 전처리"""
    # 그레이스케일 → 대비 향상(1.5x) → 언샵 마스크
    gray = img.convert("L")
    enhanced = ImageEnhance.Contrast(gray).enhance(1.5)
    sharpened = enhanced.filter(
        ImageFilter.UnsharpMask(radius=2, percent=150, threshold=3)
    )
    # surya는 RGB 입력 필요
    return sharpened.convert("RGB")


# ── 텍스트 품질 검사 (기존 로직 유지) ──────────────────────────────────────

_KOREAN_RANGE = range(0xAC00, 0xD7A4)
_QUALITY_THRESHOLD = 0.05


def _korean_ratio(text: str) -> float:
    """텍스트에서 완성형 한글 비율"""
    if not text:
        return 0.0
    korean_chars = sum(1 for ch in text if 0xAC00 <= ord(ch) <= 0xD7A3)
    total_printable = sum(1 for ch in text if ch.isprintable() and not ch.isspace())
    if total_printable == 0:
        return 0.0
    return korean_chars / total_printable


def _is_text_garbled(text: str, threshold: float = _QUALITY_THRESHOLD) -> bool:
    """추출된 텍스트가 깨졌는지 판단 (한글 비율 < threshold)"""
    ratio = _korean_ratio(text)
    if ratio < threshold:
        logger.info("텍스트 품질 낮음: 한글 비율 %.1f%% (임계 %d%%) — OCR 필요",
                     ratio * 100, int(threshold * 100))
        return True
    return False


def _normalize_ocr_korean(text: str) -> str:
    """OCR 한글 텍스트 후처리 — 음절 간 불필요한 공백 제거"""
    return re.sub(r'(?<=[가-힣])\s{1}(?=[가-힣])', '', text)


# ── Surya OCR 처리 ───────────────────────────────────────────────────────────

def _surya_ocr_page(img: Image.Image, languages: list[str] | None = None) -> str:
    """surya-ocr로 단일 이미지에서 텍스트 추출"""
    if languages is None:
        languages = get_settings().ocr_languages

    try:
        engine = _get_surya_ocr_engine()
        run_ocr = engine["run_ocr"]

        from surya.schema import OCRResponse

        result: OCRResponse = run_ocr(
            images=[img],
            langs=[languages],
            det_processor=engine["det_processor"],
            det_model=engine["det_model"],
            rec_processor=engine["rec_processor"],
            rec_model=engine["rec_model"],
        )

        # 첫 번째 이미지 결과의 텍스트 라인 결합
        if result and len(result) > 0:
            lines = []
            for line in result[0].text_lines:
                lines.append(line.text)
            text = "\n".join(lines)
            text = _normalize_ocr_korean(text)
            return text

        return ""
    except Exception as e:
        logger.warning("surya OCR 처리 실패: %s", e)
        return ""


def _surya_layout_detect(img: Image.Image) -> list[dict]:
    """surya 레이아웃 분석으로 표/그림/단락 영역 감지"""
    try:
        engine = _get_surya_layout_engine()
        run_layout = engine["run_layout"]
        layout_model = engine["layout_model"]

        result = run_layout(
            images=[img],
            model=layout_model,
        )

        regions = []
        if result and len(result) > 0:
            for bbox in result[0].bboxes:
                regions.append({
                    "label": bbox.label,
                    "confidence": bbox.confidence,
                    "bbox": [bbox.x1, bbox.y1, bbox.x2, bbox.y2],
                })
        return regions
    except Exception as e:
        logger.warning("surya 레이아웃 분석 실패: %s", e)
        return []


# ── 표 추출 ──────────────────────────────────────────────────────────────────

def _extract_tables_camelot(file_path: str, pages: list[int] | None = None) -> list[str]:
    """camelot로 PDF에서 표 추출 → 마크다운.

    Args:
        file_path: PDF 파일 경로
        pages: 추출할 페이지 번호 리스트 (1-based). None이면 전체 페이지.

    Returns:
        표 마크다운 문자열 리스트
    """
    try:
        import camelot
        tables_md = []
        page_range = ",".join(str(p) for p in pages) if pages else "all"

        tables = camelot.read_pdf(file_path, pages=page_range, flavor="lattice")
        for i, table in enumerate(tables):
            try:
                md = table.df.to_markdown(index=False)
                tables_md.append(f"\n[표 {i + 1}]\n{md}\n")
            except Exception as e:
                logger.debug("표 %d 마크다운 변환 실패: %s", i + 1, e)

        if tables_md:
            logger.info("camelot 표 %d개 추출 완료", len(tables_md))
        return tables_md
    except ImportError:
        logger.debug("camelot 미설치 — 표 추출 건너뜀")
        return []
    except Exception as e:
        logger.warning("camelot 표 추출 오류: %s", e)
        return []


def _extract_tables_from_images(
    images: list[Image.Image],
    page_numbers: list[int],
) -> list[str]:
    """이미지에서 표 추출 (img2table 폴백).

    스캔 PDF 등에서 camelot이 동작하지 않을 때 사용.
    """
    try:
        from img2table.document import Image as Img2TableImage
        from img2table.ocr import SuryaOCR as Img2TableSurya

        tables_md = []
        ocr_instance = None

        # surya를 img2table의 OCR 백엔드로 사용 (가능한 경우)
        try:
            ocr_instance = Img2TableSurya()
        except Exception:
            pass

        for img, page_num in zip(images, page_numbers):
            try:
                doc = Img2TableImage(img)
                extracted = doc.extract_tables(ocr=ocr_instance)
                for table in extracted:
                    try:
                        md = table.df.to_markdown(index=False)
                        tables_md.append(f"\n[표 — 페이지 {page_num}]\n{md}\n")
                    except Exception:
                        pass
            except Exception as e:
                logger.debug("img2table 페이지 %d 처리 실패: %s", page_num, e)

        if tables_md:
            logger.info("img2table 표 %d개 추출 완료", len(tables_md))
        return tables_md
    except ImportError:
        logger.debug("img2table 미설치 — 이미지 표 추출 건너뜀")
        return []
    except Exception as e:
        logger.warning("img2table 표 추출 오류: %s", e)
        return []


# ── Tesseract OCR 폴백 (기존 로직) ──────────────────────────────────────────

def _tesseract_ocr_page(img: Image.Image) -> str:
    """pytesseract로 단일 이미지에서 텍스트 추출 (폴백)"""
    try:
        import pytesseract

        # 전처리: 그레이스케일 → 대비 1.5x → 언샵 마스크
        gray = img.convert("L")
        enhanced = ImageEnhance.Contrast(gray).enhance(1.5)
        sharpened = enhanced.filter(
            ImageFilter.UnsharpMask(radius=2, percent=150, threshold=3)
        )

        text = pytesseract.image_to_string(
            sharpened,
            lang="kor+eng",
            config="--psm 6 --oem 1",
        )
        text = _normalize_ocr_korean(text)
        del gray, enhanced, sharpened
        return text
    except Exception as e:
        logger.warning("tesseract OCR 실패: %s", e)
        return ""


# ── 메인 OCR 파이프라인 ──────────────────────────────────────────────────────

def ocr_document(file_path: str) -> OcrDocumentResult:
    """문서 OCR 처리 — 메인 진입점.

    파이프라인:
    1. PyMuPDF로 텍스트 추출 시도
    2. 텍스트 품질 검사 (한글 비율 < 5% → OCR 필요)
    3. OCR 처리 (surya 우선, tesseract 폴백)
    4. 표 추출 (camelot → img2table 순서)
    5. 결과 병합

    Args:
        file_path: PDF/이미지 파일 경로

    Returns:
        OcrDocumentResult: 페이지별 OCR 결과
    """
    settings = get_settings()
    path = Path(file_path)

    if not path.exists():
        raise FileNotFoundError(f"파일을 찾을 수 없습니다: {file_path}")

    suffix = path.suffix.lower()
    if suffix != ".pdf":
        raise ValueError(f"OCR은 PDF만 지원합니다: {suffix}")

    result = OcrDocumentResult(metadata={"source": path.name})

    doc = fitz.open(file_path)
    total_pages = min(len(doc), settings.ocr_max_pages)
    result.total_pages = total_pages
    result.metadata["total_pages"] = total_pages

    # 1단계: PyMuPDF 텍스트 추출
    logger.info("PDF 텍스트 추출 시도: %s (%d 페이지)", path.name, total_pages)
    text_pages: dict[int, str] = {}
    for page_num in range(total_pages):
        page = doc[page_num]
        text = page.get_text()
        if text and text.strip():
            text_pages[page_num + 1] = text

    full_extracted = "\n".join(text_pages.values())

    # 2단계: 품질 검사
    needs_ocr = _is_text_garbled(full_extracted)
    ocr_provider = settings.ocr_provider

    # ocr_provider가 "none"이면 OCR 건너뜀
    if ocr_provider == "none":
        needs_ocr = False

    # surya 사용 가능한지 확인
    use_surya = needs_ocr and ocr_provider == "surya" and _check_surya_available()

    # 3단계: 페이지별 처리
    images_for_tables: list[Image.Image] = []
    image_page_numbers: list[int] = []

    for page_num in range(total_pages):
        page_number = page_num + 1
        page = doc[page_num]
        extracted_text = text_pages.get(page_number, "")

        # 텍스트가 충분하면 OCR 건너뜀
        page_needs_ocr = needs_ocr or _is_text_garbled(extracted_text)

        if not page_needs_ocr and extracted_text.strip():
            result.pages.append(OcrPageResult(
                page_number=page_number,
                text=extracted_text,
                method="text",
                has_ocr=False,
            ))
            continue

        # OCR 필요 — 이미지 렌더링
        try:
            img = _render_page_image(page, dpi=settings.ocr_dpi)
            images_for_tables.append(img)
            image_page_numbers.append(page_number)

            # surya 또는 tesseract로 OCR
            if use_surya:
                ocr_text = _surya_ocr_page(img, settings.ocr_languages)
                method = "surya"
            else:
                ocr_text = _tesseract_ocr_page(img)
                method = "tesseract"

            # OCR 결과가 빈 페이지면 원본 텍스트 사용
            if not ocr_text.strip() and extracted_text.strip():
                ocr_text = extracted_text
                method = "text_fallback"

            result.pages.append(OcrPageResult(
                page_number=page_number,
                text=ocr_text,
                method=method,
                has_ocr=True,
            ))

            del img
        except Exception as e:
            logger.warning("페이지 %d OCR 처리 실패: %s", page_number, e)
            # 폴백: 원본 텍스트 사용
            result.pages.append(OcrPageResult(
                page_number=page_number,
                text=extracted_text or "",
                method="error",
                has_ocr=False,
            ))

        # 100페이지마다 메모리 정리
        if (page_num + 1) % 100 == 0:
            gc.collect()
            logger.info("OCR 진행: %d/%d 페이지 완료", page_num + 1, total_pages)

    doc.close()
    gc.collect()

    # 4단계: 표 추출 (선택)
    if settings.ocr_enable_table:
        # camelot으로 PDF에서 직접 표 추출 시도
        table_pages = [p for p in result.pages if p.has_ocr or _is_text_garbled(p.text)]
        table_page_numbers = [p.page_number for p in table_pages]

        tables_md: list[str] = []

        # camelot 시도 (텍스트 기반 PDF에 효과적)
        tables_md.extend(_extract_tables_camelot(file_path, table_page_numbers or None))

        # camelot 실패 시 img2table으로 이미지에서 표 추출
        if not tables_md and images_for_tables:
            tables_md.extend(
                _extract_tables_from_images(images_for_tables, image_page_numbers)
            )

        # 표를 해당 페이지 결과에 추가
        if tables_md:
            # 모든 표를 마지막 페이지에 추가 (간단한 구현)
            # TODO: 표의 페이지 위치를 파악하여 정확한 페이지에 삽입
            for page in result.pages:
                if page.page_number == result.pages[-1].page_number:
                    page.tables.extend(tables_md)
                    break

    # 메모리 정리
    del images_for_tables
    gc.collect()

    # 대표 처리 방식 결정
    methods = [p.method for p in result.pages if p.method != "unknown"]
    if methods:
        result.method = max(set(methods), key=methods.count)

    result.metadata["method"] = result.method
    result.metadata["ocr_pages"] = sum(1 for p in result.pages if p.has_ocr)

    logger.info("OCR 완료: %s — %d페이지, 방식=%s, OCR=%d페이지, 표=%d개",
                path.name, total_pages, result.method,
                result.metadata.get("ocr_pages", 0),
                sum(len(p.tables) for p in result.pages))

    return result


# ── 편의 함수: 기존 파서와의 호환 ──────────────────────────────────────────

def ocr_pdf_to_text(file_path: str) -> str:
    """PDF OCR 처리 후 전체 텍스트만 반환 (기존 _ocr_pdf 대체용).

    Args:
        file_path: PDF 파일 경로

    Returns:
        전체 텍스트 (페이지 구분 포함)
    """
    result = ocr_document(file_path)
    return result.full_text