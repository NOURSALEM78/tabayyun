"""Read source PDF pages, caching OCR or extracted text for repeatable runs."""

import logging
import subprocess
import unicodedata
from pathlib import Path

import pymupdf
import pytesseract
from pdf2image import convert_from_path
from pdf2image.exceptions import (
    PDFInfoNotInstalledError,
    PDFPageCountError,
    PDFSyntaxError,
)
from PIL import Image

from backend.ingestion.constants import (
    OCR_CONFIG,
    OCR_DPI,
    OCR_INK_THRESHOLD,
    OCR_LANGUAGE,
    OCR_MIN_INK_FRACTION,
    OCR_MIN_TEXT_CHARACTERS,
    PDFTOTEXT_COMMAND,
    TESSDATA_BEST_DIR,
    TESSDATA_BEST_MODEL,
    TEXT_LAYER_GLYPH_FIXES,
)

logger = logging.getLogger(__name__)


class PdfPageReadError(RuntimeError):
    """Raised when a source PDF page cannot be rendered or read."""


def page_cache_path(cache_dir: Path, page_number: int) -> Path:
    """Return the cache path for a one-based PDF page number."""
    return cache_dir / f"page_{page_number:03d}.txt"


def read_pdf_pages(pdf_path: Path, cache_dir: Path, text_layer: bool = False) -> list[str]:
    """Read all pages from a PDF, using cached text when available."""
    if not pdf_path.is_file():
        raise FileNotFoundError(f"Source PDF does not exist: {pdf_path}")

    cache_dir.mkdir(parents=True, exist_ok=True)
    try:
        document = pymupdf.open(pdf_path)
    except (pymupdf.FileDataError, OSError) as exc:
        raise PdfPageReadError(f"Could not open source PDF {pdf_path}: {exc}") from exc

    with document:
        if not len(document):
            raise PdfPageReadError(f"Source PDF contains no pages: {pdf_path}")
        return [
            _read_or_extract_page(page, page_number, pdf_path, cache_dir, text_layer)
            for page_number, page in enumerate(document, start=1)
        ]


def _read_or_extract_page(
    page: pymupdf.Page,
    page_number: int,
    pdf_path: Path,
    cache_dir: Path,
    text_layer: bool,
) -> str:
    """Read one cached page or extract its text from the PDF page."""
    cache_path = page_cache_path(cache_dir, page_number)
    if cache_path.is_file():
        return cache_path.read_text(encoding="utf-8")

    try:
        if text_layer:
            page_text = _extract_text_layer_page(pdf_path, page_number)
        else:
            page_text = _render_and_ocr_page(pdf_path, page_number)
    except (
        OSError,
        RuntimeError,
        subprocess.CalledProcessError,
        PDFInfoNotInstalledError,
        PDFPageCountError,
        PDFSyntaxError,
        pytesseract.TesseractError,
    ) as exc:
        raise PdfPageReadError(
            f"Could not extract page {page_number} from {pdf_path}: {exc}"
        ) from exc

    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(page_text, encoding="utf-8")
    if not page_text.strip():
        logger.error("No text extracted from %s page %d", pdf_path.name, page_number)
    return page_text


def _extract_text_layer_page(pdf_path: Path, page_number: int) -> str:
    """Read one page's embedded text with pdftotext and normalize Arabic glyphs."""
    result = subprocess.run(
        [
            PDFTOTEXT_COMMAND,
            "-f",
            str(page_number),
            "-l",
            str(page_number),
            "-enc",
            "UTF-8",
            str(pdf_path),
            "-",
        ],
        capture_output=True,
        check=True,
        text=True,
        encoding="utf-8",
    )
    text = unicodedata.normalize("NFKC", result.stdout)
    for glyph, replacement in TEXT_LAYER_GLYPH_FIXES:
        text = text.replace(glyph, replacement)
    return text


def _render_and_ocr_page(pdf_path: Path, page_number: int) -> str:
    """Render one Poppler page in grayscale and extract Arabic text with Tesseract."""
    images = convert_from_path(
        str(pdf_path),
        dpi=OCR_DPI,
        grayscale=True,
        first_page=page_number,
        last_page=page_number,
    )
    if not images:
        raise PdfPageReadError(f"Poppler rendered no image for {pdf_path} page {page_number}")

    image = images[0]
    try:
        if _is_blank(image):
            logger.error("Rendered page has no visible ink: %s page %d", pdf_path.name, page_number)
        text = pytesseract.image_to_string(
            image,
            lang=OCR_LANGUAGE,
            config=_tesseract_config(),
        )
    finally:
        image.close()

    if len(text.strip()) < OCR_MIN_TEXT_CHARACTERS:
        logger.error(
            "OCR returned fewer than %d characters for %s page %d (%d characters)",
            OCR_MIN_TEXT_CHARACTERS,
            pdf_path.name,
            page_number,
            len(text.strip()),
        )
    return text


def _is_blank(image: Image.Image) -> bool:
    """Return whether the page has almost no dark (ink) pixels.

    Text pages are mostly white paper, so blankness is measured by the share of
    dark pixels rather than the share of white ones.
    """
    grayscale = image.convert("L")
    dark_pixels = sum(grayscale.histogram()[:OCR_INK_THRESHOLD])
    pixel_count = grayscale.width * grayscale.height
    grayscale.close()
    return pixel_count == 0 or dark_pixels / pixel_count < OCR_MIN_INK_FRACTION


def _tesseract_config() -> str:
    """Use the optional best Arabic model when present, otherwise system tessdata."""
    if TESSDATA_BEST_MODEL.is_file():
        return f'{OCR_CONFIG} --tessdata-dir "{TESSDATA_BEST_DIR}"'
    return OCR_CONFIG
