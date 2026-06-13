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
    elif suffix in (".docx", ".doc"):
        return _extract_docx(file_path)
    elif suffix == ".hwp":
        return _extract_hwp(file_path)
    elif suffix in (".xlsx", ".xls"):
        return _extract_excel(file_path)
    elif suffix == ".csv":
        return _extract_csv(file_path)
    elif suffix in (".md", ".markdown"):
        return _extract_txt(file_path)  # 마크다운은 텍스트와 동일 처리
    else:
        raise ValueError(f"지원하지 않는 파일 형식입니다: {suffix}")


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


# ── DOC/DOCX 파서 ──────────────────────────────────────────────────────────

def _extract_docx(file_path: str) -> ExtractResult:
    """DOCX/DOC에서 텍스트를 추출합니다.

    .docx는 python-docx로 직접 파싱.
    .doc(레거시)은 LibreOffice/headless로 docx 변환 후 파싱.
    """
    path = Path(file_path)

    if path.suffix.lower() == ".docx":
        return _extract_docx_native(file_path)
    else:
        # .doc → LibreOffice로 .docx 변환 시도
        return _extract_doc_legacy(file_path)


def _extract_docx_native(file_path: str) -> ExtractResult:
    """python-docx로 DOCX 파일에서 텍스트 추출."""
    try:
        from docx import Document  # type: ignore[import-untyped]
    except ImportError:
        raise ImportError(
            "python-docx가 설치되지 않았습니다. "
            "pip install python-docx로 설치하세요."
        )

    doc = Document(file_path)
    metadata = {"source": Path(file_path).name, "method": "docx"}

    # 단락 텍스트
    paragraphs: list[str] = []
    for para in doc.paragraphs:
        if para.text.strip():
            paragraphs.append(para.text)

    # 표 텍스트 → 마크다운
    tables_md: list[str] = []
    for ti, table in enumerate(doc.tables):
        rows_data: list[list[str]] = []
        for row in table.rows:
            cells = [cell.text.strip() for cell in row.cells]
            rows_data.append(cells)
        if rows_data:
            # 마크다운 테이블 생성
            header = "| " + " | ".join(rows_data[0]) + " |"
            separator = "| " + " | ".join("---" for _ in rows_data[0]) + " |"
            body = "\n".join("| " + " | ".join(row) + " |" for row in rows_data[1:])
            tables_md.append(f"\n[표 {ti + 1}]\n{header}\n{separator}\n{body}\n")

    full_text = "\n\n".join(paragraphs)
    if tables_md:
        full_text += "\n\n" + "\n".join(tables_md)

    metadata["paragraphs"] = len(paragraphs)
    metadata["tables"] = len(doc.tables) if doc.tables else 0

    return ExtractResult(text=full_text, metadata=metadata)


def _extract_doc_legacy(file_path: str) -> ExtractResult:
    """레거시 .doc 파일에서 텍스트 추출.

    LibreOffice headless로 .doc → .docx 변환 후 python-docx로 파싱.
    LibreOffice가 없으면 olefile로 OLE 스트림에서 텍스트 추출 시도.
    """
    import subprocess
    import tempfile

    # 1차 시도: LibreOffice로 .docx 변환
    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            result = subprocess.run(
                ["libreoffice", "--headless", "--convert-to", "docx",
                 "--outdir", tmpdir, file_path],
                capture_output=True, text=True, timeout=60,
            )
            if result.returncode == 0:
                converted = Path(tmpdir) / (Path(file_path).stem + ".docx")
                if converted.exists():
                    docx_result = _extract_docx_native(str(converted))
                    docx_result.metadata["method"] = "doc_libreoffice"
                    return docx_result
    except (FileNotFoundError, subprocess.TimeoutExpired):
        logger.info("LibreOffice 없음 — olefile로 폴백")

    # 2차 시도: olefile로 OLE 스트림에서 텍스트 추출
    try:
        return _extract_doc_olefile(file_path)
    except Exception as e:
        logger.warning(".doc 파일 처리 실패 (olefile): %s", e)
        raise ValueError(f".doc 파일 처리 불가: {Path(file_path).name} — "
                         "LibreOffice 또는 olefile 필요")


def _extract_doc_olefile(file_path: str) -> ExtractResult:
    """olefile로 .doc 파일의 OLE 스트림에서 텍스트 추출."""
    try:
        import olefile  # type: ignore[import-untyped]
    except ImportError:
        raise ImportError("olefile이 설치되지 않았습니다. pip install olefile")

    ole = olefile.OleFileIO(file_path)
    metadata = {"source": Path(file_path).name, "method": "doc_olefile"}

    # WordDocument 스트림에서 텍스트 추출 시도
    text_parts: list[str] = []

    if ole.exists("WordDocument"):
        # 1. WordDocument에서 직접 텍스트 시도
        if ole.exists("1Table"):
            # Word 테이블 스트림에서 Piece Table 디코딩은 복잡하므로
            # 바이너리에서 가독 텍스트만 추출 (폴백)
            pass

    # OLE 스트림 목록에서 텍스트성 스트림 추출
    for stream_name in ole.listdir():
        stream_path = "/".join(stream_name)
        if any(s in stream_path.lower() for s in ["worddocument", "1table", "0table"]):
            try:
                data = ole.openstream(stream_name).read()
                # UTF-16LE 디코딩 시도 (Word 내부 포맷)
                try:
                    decoded = data.decode("utf-16-le", errors="ignore")
                    # 가독 텍스트만 필터링 (한글, 영문, 숫자, 기호)
                    clean = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", decoded)
                    if clean.strip():
                        text_parts.append(clean)
                except Exception:
                    pass
            except Exception:
                pass

    ole.close()

    full_text = "\n".join(text_parts)
    if not full_text.strip():
        raise ValueError("OLE 스트림에서 가독 텍스트를 추출할 수 없습니다")

    return ExtractResult(text=full_text, metadata=metadata)


# ── HWP 파서 ───────────────────────────────────────────────────────────────

def _extract_hwp(file_path: str) -> ExtractResult:
    """HWP(한글 문서)에서 텍스트를 추출합니다.

    HWP 파일은 OLE2(구버전)와 HWPX5(신버전, ZIP) 두 가지 포맷이 있습니다.
    - HWPX5(.hwpx): ZIP 내부 XML 파싱
    - HWP(OLE2): olefile로 OLE 스트림에서 텍스트 추출
    """
    path = Path(file_path)
    metadata = {"source": path.name}

    # HWPX5 포맷 감지 (ZIP 기반)
    import zipfile
    try:
        with zipfile.ZipFile(file_path, "r") as zf:
            names = zf.namelist()
            if "Contents/content.xml" in names or "content.xml" in names:
                return _extract_hwpx(file_path)
    except zipfile.BadZipFile:
        pass  # ZIP이 아니면 OLE2 포맷

    # OLE2 포맷 (레거시 HWP)
    return _extract_hwp_ole(file_path)


def _extract_hwpx(file_path: str) -> ExtractResult:
    """HWPX5(ZIP 기반) 문서에서 텍스트 추출."""
    import zipfile
    from xml.etree import ElementTree as ET

    metadata = {"source": Path(file_path).name, "method": "hwpx"}
    text_parts: list[str] = []

    with zipfile.ZipFile(file_path, "r") as zf:
        # content.xml 파싱
        for content_name in ["Contents/content.xml", "content.xml"]:
            if content_name in zf.namelist():
                with zf.open(content_name) as f:
                    try:
                        tree = ET.parse(f)
                        root = tree.getroot()
                        # 모든 텍스트 노드 추출 (네임스페이스 무시)
                        for elem in root.iter():
                            if elem.text and elem.text.strip():
                                text_parts.append(elem.text.strip())
                            if elem.tail and elem.tail.strip():
                                text_parts.append(elem.tail.strip())
                    except ET.ParseError as e:
                        logger.warning("HWPX XML 파싱 실패: %s", e)

    full_text = "\n".join(text_parts)
    metadata["paragraphs"] = len(text_parts)

    return ExtractResult(text=full_text, metadata=metadata)


def _extract_hwp_ole(file_path: str) -> ExtractResult:
    """OLE2 기반 레거시 HWP에서 텍스트 추출."""
    try:
        import olefile  # type: ignore[import-untyped]
    except ImportError:
        raise ImportError("olefile이 설치되지 않았습니다. pip install olefile")

    ole = olefile.OleFileIO(file_path)
    metadata = {"source": Path(file_path).name, "method": "hwp_ole"}
    text_parts: list[str] = []

    # HWP OLE 스트림에서 텍스트 추출
    # 주요 스트림: HWPSummaryInformation, Prism, 등
    for stream_name in ole.listdir():
        stream_path = "/".join(stream_name)
        try:
            data = ole.openstream(stream_name).read()
            # UTF-16LE 디코딩 시도 (한글 문서 내부 포맷)
            try:
                decoded = data.decode("utf-16-le", errors="ignore")
                # 한글, 영문, 숫자, 구두점만 필터링
                clean = re.sub(r"[^\uAC00-\uD7A3\u3131-\u3163a-zA-Z0-9\s.,!?;:\"'()\[\]{}<>@#$%^&*+=~/\\|—–\-]", "", decoded)
                clean = re.sub(r"\s{3,}", "\n", clean)  # 3+ 공백 → 줄바꿈
                if clean.strip():
                    text_parts.append(clean.strip())
            except Exception:
                pass
        except Exception:
            pass

    ole.close()

    full_text = "\n\n".join(text_parts)
    if not full_text.strip():
        raise ValueError("HWP 파일에서 텍스트를 추출할 수 없습니다. "
                         f"파일: {Path(file_path).name}")

    return ExtractResult(text=full_text, metadata=metadata)


# ── Excel 파서 ──────────────────────────────────────────────────────────────

def _extract_excel(file_path: str) -> ExtractResult:
    """XLSX/XLS 파일에서 텍스트를 추출합니다.

    각 시트를 마크다운 테이블로 변환하여 표 구조를 보존합니다.
    """
    path = Path(file_path)

    if path.suffix.lower() == ".xlsx":
        return _extract_xlsx(file_path)
    else:
        # .xls → openpyxl은 .xlsx만 지원하므로 xlrd 시도
        return _extract_xls(file_path)


def _extract_xlsx(file_path: str) -> ExtractResult:
    """openpyxl로 XLSX 파일에서 텍스트 추출."""
    try:
        from openpyxl import load_workbook  # type: ignore[import-untyped]
    except ImportError:
        raise ImportError("openpyxl이 설치되지 않았습니다. pip install openpyxl")

    wb = load_workbook(file_path, read_only=True, data_only=True)
    metadata = {"source": Path(file_path).name, "method": "xlsx",
                "sheets": len(wb.sheetnames)}

    all_sheets: list[str] = []

    for sheet_name in wb.sheetnames:
        ws = wb[sheet_name]
        rows_data: list[list[str]] = []

        for row in ws.iter_rows(values_only=True):
            cells = [str(cell) if cell is not None else "" for cell in row]
            # 빈 행 건너뛰기
            if any(c.strip() for c in cells):
                rows_data.append(cells)

        if not rows_data:
            continue

        # 마크다운 테이블 생성
        header = "| " + " | ".join(rows_data[0]) + " |"
        separator = "| " + " | ".join("---" for _ in rows_data[0]) + " |"
        body = "\n".join("| " + " | ".join(row) + " |" for row in rows_data[1:])

        sheet_text = f"--- 시트: {sheet_name} ---\n{header}\n{separator}\n{body}"
        all_sheets.append(sheet_text)

    wb.close()

    full_text = "\n\n".join(all_sheets)
    metadata["sheets_extracted"] = len(all_sheets)

    return ExtractResult(text=full_text, metadata=metadata)


def _extract_xls(file_path: str) -> ExtractResult:
    """xlrd로 레거시 XLS 파일에서 텍스트 추출."""
    try:
        import xlrd  # type: ignore[import-untyped]
    except ImportError:
        raise ImportError(
            "xlrd가 설치되지 않았습니다. pip install xlrd"
        )

    wb = xlrd.open_workbook(file_path)
    metadata = {"source": Path(file_path).name, "method": "xls",
                "sheets": wb.nsheets}

    all_sheets: list[str] = []

    for sheet_idx in range(wb.nsheets):
        sheet = wb.sheet_by_index(sheet_idx)
        rows_data: list[list[str]] = []

        for row_idx in range(sheet.nrows):
            cells = [str(sheet.cell_value(row_idx, col_idx))
                      for col_idx in range(sheet.ncols)]
            if any(c.strip() for c in cells):
                rows_data.append(cells)

        if not rows_data:
            continue

        header = "| " + " | ".join(rows_data[0]) + " |"
        separator = "| " + " | ".join("---" for _ in rows_data[0]) + " |"
        body = "\n".join("| " + " | ".join(row) + " |" for row in rows_data[1:])

        sheet_text = f"--- 시트: {sheet.name} ---\n{header}\n{separator}\n{body}"
        all_sheets.append(sheet_text)

    metadata["sheets_extracted"] = len(all_sheets)

    return ExtractResult(text="\n\n".join(all_sheets), metadata=metadata)


# ── CSV 파서 ────────────────────────────────────────────────────────────────

def _extract_csv(file_path: str) -> ExtractResult:
    """CSV 파일에서 텍스트를 추출합니다.

    마크다운 테이블로 변환하여 표 구조를 보존합니다.
    한국어 인코딩(cp949, euc-kr, utf-8)을 자동 감지합니다.
    """
    import csv
    import io

    # 인코딩 감지
    with open(file_path, "rb") as f:
        raw_data = f.read()

    detected = chardet.detect(raw_data)
    encoding = detected.get("encoding", "utf-8")
    confidence = detected.get("confidence", 0)

    if confidence < 0.7:
        encoding = "utf-8"

    # 한국어 인코딩 폴백
    text_content: str | None = None
    for enc in [encoding, "utf-8", "utf-8-sig", "cp949", "euc-kr"]:
        try:
            text_content = raw_data.decode(enc)
            encoding = enc
            break
        except (UnicodeDecodeError, LookupError):
            continue

    if text_content is None:
        text_content = raw_data.decode("utf-8", errors="ignore")

    # 구분자 자동 감지 (쉼표, 탭, 파이프)
    dialect = csv.Sniffer().sniff(text_content[:4096],
                                   delimiters=",\t|")
    delimiter = dialect.delimiter

    reader = csv.reader(io.StringIO(text_content), delimiter=delimiter)
    rows_data: list[list[str]] = []
    for row in reader:
        cells = [cell.strip() for cell in row]
        if any(c for c in cells):
            rows_data.append(cells)

    metadata = {"source": Path(file_path).name, "method": "csv",
                "encoding": encoding, "delimiter": delimiter,
                "rows": len(rows_data)}

    if not rows_data:
        return ExtractResult(text="", metadata=metadata)

    # 마크다운 테이블 생성
    max_cols = max(len(row) for row in rows_data)
    # 모든 행의 열 수를 맞춤
    for row in rows_data:
        while len(row) < max_cols:
            row.append("")

    header = "| " + " | ".join(rows_data[0]) + " |"
    separator = "| " + " | ".join("---" for _ in range(max_cols)) + " |"
    body = "\n".join("| " + " | ".join(row) + " |" for row in rows_data[1:])

    full_text = f"{header}\n{separator}\n{body}"
    return ExtractResult(text=full_text, metadata=metadata)


# ── URL/웹페이지 파서 ───────────────────────────────────────────────────────

def extract_url(url: str) -> ExtractResult:
    """URL에서 웹페이지 텍스트를 추출합니다.

    httpx로 페이지를 가져오고 readability로 본문을 추출합니다.
    """
    import re as _re

    try:
        import httpx
    except ImportError:
        raise ImportError("httpx가 설치되지 않았습니다. pip install httpx")

    try:
        from readability import Document  # type: ignore[import-untyped]
    except ImportError:
        # readability가 없으면 HTML 태그 제거로 폴백
        Document = None

    metadata = {"source": url, "method": "url"}

    # 웹페이지 가져오기
    resp = httpx.get(url, follow_redirects=True, timeout=30,
                     headers={"User-Agent": "mAI-Brain/1.0 (Korean RAG Bot)"})
    resp.raise_for_status()
    html = resp.text

    # 인코딩 감지
    content_type = resp.headers.get("content-type", "")
    if "charset" not in content_type.lower():
        detected = chardet.detect(resp.content)
        if detected.get("confidence", 0) > 0.7:
            html = resp.content.decode(detected.get("encoding", "utf-8"),
                                       errors="ignore")

    metadata["url"] = url
    metadata["status_code"] = resp.status_code

    # 본문 추출
    if Document is not None:
        doc = Document(html)
        title = doc.title()
        summary_html = doc.summary()
        # HTML 태그 제거
        text = _re.sub(r"<[^>]+>", " ", summary_html)
        text = _re.sub(r"\s+", " ", text).strip()
        if title:
            text = f"# {title}\n\n{text}"
        metadata["title"] = title
    else:
        # 폴백: HTML 태그 제거만
        text = _re.sub(r"<script[^>]*>.*?</script>", "", html, flags=_re.DOTALL)
        text = _re.sub(r"<style[^>]*>.*?</style>", "", text, flags=_re.DOTALL)
        text = _re.sub(r"<[^>]+>", " ", text)
        text = _re.sub(r"\s+", " ", text).strip()

    if not text.strip():
        raise ValueError(f"URL에서 텍스트를 추출할 수 없습니다: {url}")

    return ExtractResult(text=text, metadata=metadata)
