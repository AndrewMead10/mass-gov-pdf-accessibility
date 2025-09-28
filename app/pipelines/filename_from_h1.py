"""Pipeline that ensures filenames reflect the extracted H1 heading."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Dict, Optional

from .base import (
    BasePipeline,
    IdentifyFinding,
    IdentifyResult,
    PipelineContext,
    PipelineError,
    ResolveChange,
    ResolveResult,
)
from .helpers import (
    PDFHeadingError,
    check_pdf_for_h1,
    ensure_pipeline_output_dir,
    suggest_filename_with_openai,
    validate_filename,
)
from ..crud import update_document_filename


CACHE_BUCKET = "pipeline_cache"
CACHE_HEADING_KEY = "document_h1_heading"
CACHE_VALIDATION_KEY = "filename_validation"


# Check: Verify that stored filenames reuse meaningful terms from the document's H1 heading.
# Why: Descriptive filenames improve search, indexing, and pairing PDFs with their accessible alternatives.
# Resolve: When mismatched, generate an AI-assisted rename suggestion and stage a renamed copy for review.
class FilenameFromHeadingPipeline(BasePipeline):
    """Compare the PDF filename with the detected H1 heading and suggest improvements."""

    slug = "filename-from-h1"
    title = "Filename Mirrors H1"
    description = "Flags PDFs whose filenames do not align with the detected H1 heading and proposes fixes."

    @staticmethod
    def _cache(context: PipelineContext) -> Dict[str, object]:
        return context.metadata.setdefault(CACHE_BUCKET, {})

    def _ensure_heading(self, context: PipelineContext) -> Optional[str]:
        cache = self._cache(context)
        if CACHE_HEADING_KEY not in cache:
            try:
                heading = check_pdf_for_h1(context.pdf_path)
            except PDFHeadingError:
                cache[CACHE_HEADING_KEY] = None
            except Exception as exc:  # noqa: BLE001
                raise RuntimeError("Failed to extract H1 heading for filename validation") from exc
            else:
                cache[CACHE_HEADING_KEY] = heading
        return cache.get(CACHE_HEADING_KEY)

    def identify(self, context: PipelineContext) -> IdentifyResult:
        """Inspect the current filename and surface a finding when it diverges from the H1 heading."""
        cache = self._cache(context)
        heading = self._ensure_heading(context)

        if not heading:
            summary = "Skipped filename validation because the document has no detectable H1 heading."
            return IdentifyResult(pipeline_slug=self.slug, findings=[], summary=summary)

        current_name = Path(context.pdf_path).stem
        is_valid, reason = validate_filename(current_name, heading)

        cache[CACHE_VALIDATION_KEY] = {
            "current": current_name,
            "heading": heading,
            "is_valid": is_valid,
            "reason": reason,
        }

        if is_valid:
            return IdentifyResult(
                pipeline_slug=self.slug,
                findings=[],
                summary="Filename already reflects the detected H1 heading.",
            )

        finding = IdentifyFinding(
            issue_code="document.filename_mismatch",
            summary="Filename does not incorporate terms from the H1 heading",
            detail=(
                "The current filename should use hyphen-separated keywords taken from the H1 heading. "
                f"Reason: {reason}."
            ),
            pages=(),
            extra={
                "current_filename": current_name,
                "h1_heading": heading,
            },
        )

        return IdentifyResult(
            pipeline_slug=self.slug,
            findings=[finding],
            summary="Filename is missing H1-derived keywords and hyphenation.",
        )

    def resolve(self, context: PipelineContext, identify: IdentifyResult) -> ResolveResult:
        """Create a renamed copy of the PDF using an AI-generated filename suggestion."""
        cache = self._cache(context)
        metadata = cache.get(CACHE_VALIDATION_KEY)
        if not metadata or metadata.get("is_valid"):
            raise PipelineError("Resolve requested but filename is already considered valid")

        heading = metadata.get("heading") or self._ensure_heading(context)
        if not heading:
            raise PipelineError("Cannot resolve filename without an H1 heading")

        current_name = metadata.get("current") or Path(context.pdf_path).stem

        suggested_base = suggest_filename_with_openai(heading, current_name)
        if not suggested_base:
            raise RuntimeError("AI did not return a filename suggestion")

        target_dir = ensure_pipeline_output_dir(context.output_dir, self.slug)
        target_path = Path(target_dir) / f"{suggested_base}.pdf"

        counter = 1
        while target_path.exists():
            target_path = Path(target_dir) / f"{suggested_base}-{counter}.pdf"
            counter += 1

        shutil.copy2(context.pdf_path, target_path)

        # Update the database filename if we have a database session
        if context.db_session:
            update_document_filename(
                db=context.db_session,
                document_id=context.document_id,
                filename=suggested_base,
            )

        cache[CACHE_VALIDATION_KEY]["suggested"] = target_path.name

        change = ResolveChange(
            description=f"Suggested renaming file to {target_path.name}",
            pages_impacted=(),
            annotations={
                "suggested_filename": target_path.name,
                "source_filename": Path(context.pdf_path).name,
            },
        )

        notes = (
            "Generated filename via OpenAI to mirror the H1 heading; output is staged as a copy for review."
        )

        return ResolveResult(
            pipeline_slug=self.slug,
            resolved_pdf_path=str(target_path),
            change_log=[change],
            notes=notes,
        )
