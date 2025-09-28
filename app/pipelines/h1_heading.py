"""Pipeline that verifies a document exposes a top-level H1 heading."""

from __future__ import annotations

from typing import Dict, List

from .base import BasePipeline, IdentifyFinding, IdentifyResult, PipelineContext
from .helpers import PDFHeadingError, check_pdf_for_h1


CACHE_BUCKET = "pipeline_cache"
CACHE_HEADING_KEY = "document_h1_heading"


def _truncate(text: str, max_len: int = 120) -> str:
    """Return a shortened representation that fits within `max_len` characters."""
    if len(text) <= max_len:
        return text
    return f"{text[: max_len - 3]}..."


# Check: Confirm that the PDF includes a top-level H1/Title tag extracted via Adobe APIs.
# Why: Without a primary heading, screen readers and downstream automation lack a reliable entry point.
# Resolve: Not applicable; the pipeline reports the absence but cannot generate missing structural tags automatically.
class H1PresencePipeline(BasePipeline):
    """Identify whether a PDF exposes a usable H1 heading."""

    slug = "h1-heading-presence"
    title = "H1 Heading Presence"
    description = "Detects whether Adobe structural data yields a top-level heading for the document."

    @staticmethod
    def _cache(context: PipelineContext) -> Dict[str, object]:
        return context.metadata.setdefault(CACHE_BUCKET, {})

    def identify(self, context: PipelineContext) -> IdentifyResult:
        """Look up the document's H1 heading and surface a finding when absent."""
        cache = self._cache(context)

        findings: List[IdentifyFinding] = []
        summary: str = ""

        try:
            heading = check_pdf_for_h1(context.pdf_path)
        except PDFHeadingError:
            cache[CACHE_HEADING_KEY] = None
            findings.append(
                IdentifyFinding(
                    issue_code="document.missing_h1",
                    summary="Document lacks a top-level H1 heading",
                    detail=(
                        "Adobe structural extraction could not locate an H1/Title element. "
                        "Manual remediation is required to add a logical document heading."
                    ),
                    pages=(),
                    wcag_references=["WCAG 2.4.6"],
                    extra={"pdf_path": context.pdf_path},
                )
            )
            summary = "No H1 heading detected in the document structure."
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError("Failed to analyse document heading structure") from exc
        else:
            cache[CACHE_HEADING_KEY] = heading
            summary = f"Found top-level heading: {_truncate(heading)}"

        return IdentifyResult(
            pipeline_slug=self.slug,
            findings=findings,
            summary=summary,
        )
