"""Run the complete source-only document ingestion and export pipeline."""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from backend.ingestion.clean import AmendmentMarker, clean_document_pages
from backend.ingestion.constants import (
    DOCUMENT_SPECS,
    EXPORT_PATH,
    PAGE_TEXT_CACHE_DIR,
    RAW_DATA_DIR,
    SOURCE_FILENAMES,
    TEXT_LAYER_SOURCE_FILENAMES,
)
from backend.ingestion.corrections import apply_text_corrections
from backend.ingestion.export import write_workbook
from backend.ingestion.extract import ExtractionResult, extract_knowledge
from backend.ingestion.ocr import read_pdf_pages
from backend.ingestion.split import (
    ArticleRecord,
    split_articles,
    split_nationality_sections,
)
from backend.ingestion.validate import ValidationRow, log_validation, validate_articles

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class PipelineSummary:
    """Summarize pipeline results for logs and callers."""

    extraction: ExtractionResult
    validation_rows: tuple[ValidationRow, ...]
    article_counts: dict[str, int]
    cache_counts: dict[str, int]
    workbook_path: Path


def _read_sources() -> tuple[dict[str, list[str]], dict[str, str]]:
    """Read each supplied PDF once using page caches and compute source hashes."""
    source_pages: dict[str, list[str]] = {}
    source_hashes: dict[str, str] = {}

    for filename in SOURCE_FILENAMES:
        pdf_path = RAW_DATA_DIR / filename
        if not pdf_path.is_file():
            raise FileNotFoundError(f"Required source PDF is missing: {pdf_path}")
        cache_dir = PAGE_TEXT_CACHE_DIR / pdf_path.stem
        source_pages[filename] = read_pdf_pages(
            pdf_path,
            cache_dir,
            text_layer=filename in TEXT_LAYER_SOURCE_FILENAMES,
        )
        source_hashes[filename] = hashlib.sha256(pdf_path.read_bytes()).hexdigest()
        logger.info("Read %s pages from %s", len(source_pages[filename]), filename)
    return source_pages, source_hashes


def _header_markers_for_source(filename: str) -> tuple[str, ...]:
    """Collect unique title markers for all logical documents in one PDF."""
    markers = dict.fromkeys(
        marker
        for spec in DOCUMENT_SPECS
        if spec.source_filename == filename
        for marker in spec.header_markers
    )
    return tuple(markers)


def _clean_sources(source_pages: dict[str, list[str]]) -> dict[str, str]:
    """Clean page text and split the combined nationality source logically."""
    cleaned_sources = {
        filename: clean_document_pages(
            pages,
            _header_markers_for_source(filename),
            join_lines=filename not in TEXT_LAYER_SOURCE_FILENAMES,
        )
        for filename, pages in source_pages.items()
    }
    nationality_filename = TEXT_LAYER_SOURCE_FILENAMES[0]
    nationality_law, nationality_regulation = split_nationality_sections(
        cleaned_sources[nationality_filename]
    )
    return {
        **cleaned_sources,
        "NAT": nationality_law,
        "NATR": nationality_regulation,
    }


def _split_documents(
    cleaned_sources: dict[str, str],
) -> tuple[tuple[ArticleRecord, ...], tuple[dict[str, Any], ...], dict[str, int]]:
    """Split each logical document and retain every detected amendment marker."""
    articles: list[ArticleRecord] = []
    amendment_markers: list[AmendmentMarker] = []
    article_counts: dict[str, int] = {}

    for spec in DOCUMENT_SPECS:
        source_text = cleaned_sources.get(spec.code, "")
        if spec.code not in cleaned_sources:
            source_text = cleaned_sources[spec.source_filename]
        split_result = split_articles(source_text, spec)
        articles.extend(split_result.articles)
        amendment_markers.extend(
            {
                "article_no": marker["article_no"],
                "marker_text": marker["marker_text"],
                "document_code": spec.code,
            }
            for marker in split_result.amendment_markers
        )
        article_counts[spec.code] = len(split_result.articles)
        if split_result.unassigned_text:
            logger.warning(
                "%s has unassigned source text after article splitting: %s",
                spec.code,
                split_result.unassigned_text[:240],
            )
    return tuple(articles), tuple(amendment_markers), article_counts


def _log_results(summary: PipelineSummary) -> None:
    """Log article counts, validation findings, and export totals."""
    for row in summary.validation_rows:
        log_validation(row)
    logger.info("Article counts by document: %s", summary.article_counts)
    logger.info(
        "Totals: articles=%d chunks=%d relations=%d draft_procedures=%d",
        len(summary.extraction.articles),
        len(summary.extraction.chunks),
        len(summary.extraction.document_relations),
        len(summary.extraction.procedures),
    )
    logger.info("OCR/text page cache counts: %s", summary.cache_counts)
    logger.info("Workbook: %s", summary.workbook_path)


def load_corrected_articles() -> tuple[ArticleRecord, ...]:
    """Read, clean and split every source, then apply the reviewed text corrections."""
    source_pages, _ = _read_sources()
    articles, _, _ = _split_documents(_clean_sources(source_pages))
    return apply_text_corrections(articles)


def run_pipeline() -> PipelineSummary:
    """Run all ingestion stages, export results, and return a count summary."""
    source_pages, source_hashes = _read_sources()
    cleaned_sources = _clean_sources(source_pages)
    articles, amendment_markers, article_counts = _split_documents(cleaned_sources)
    articles = apply_text_corrections(articles)
    validation_rows = tuple(
        validate_articles(
            spec,
            tuple(article for article in articles if article.document_code == spec.code),
            page_count=len(source_pages[spec.source_filename]),
        )
        for spec in DOCUMENT_SPECS
    )
    extraction = extract_knowledge(articles, source_hashes, amendment_markers)
    workbook_path = write_workbook(extraction, validation_rows, EXPORT_PATH)
    summary = PipelineSummary(
        extraction=extraction,
        validation_rows=validation_rows,
        article_counts=article_counts,
        cache_counts={filename: len(pages) for filename, pages in source_pages.items()},
        workbook_path=workbook_path,
    )
    _log_results(summary)
    return summary


def main() -> None:
    """Configure logging and execute the ingestion pipeline."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    run_pipeline()


if __name__ == "__main__":
    main()
