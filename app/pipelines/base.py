"""Core abstractions for accessibility pipelines."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional


class PipelineError(RuntimeError):
    """Base exception raised when a pipeline fails."""


@dataclass(slots=True)
class PipelineContext:
    """Provides pipelines with the data they need to run."""

    document_id: int
    pdf_path: str
    document_report: Optional[Dict[str, Any]]
    page_reports: List[Dict[str, Any]]
    output_dir: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    db_session: Optional[Any] = None


@dataclass(slots=True)
class IdentifyFinding:
    """Represents a single issue surfaced by a pipeline identify pass."""

    issue_code: str
    summary: str
    detail: str
    pages: Iterable[int]
    wcag_references: List[str] = field(default_factory=list)
    extra: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.pages, tuple):
            self.pages = tuple(self.pages)


@dataclass(slots=True)
class IdentifyResult:
    """Aggregated identify results for a pipeline run."""

    pipeline_slug: str
    findings: List[IdentifyFinding]
    generated_at: datetime = field(default_factory=datetime.utcnow)
    summary: Optional[str] = None

    def has_findings(self) -> bool:
        return bool(self.findings)


@dataclass(slots=True)
class ResolveChange:
    """Describes a concrete change made by a resolve step."""

    description: str
    pages_impacted: Iterable[int]
    annotations: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.pages_impacted, tuple):
            self.pages_impacted = tuple(self.pages_impacted)


@dataclass(slots=True)
class ResolveResult:
    """Captures resolve output for a pipeline."""

    pipeline_slug: str
    resolved_pdf_path: str
    change_log: List[ResolveChange]
    generated_at: datetime = field(default_factory=datetime.utcnow)
    notes: Optional[str] = None


@dataclass(slots=True)
class PipelineRunResult:
    """Combined outcome of identify/resolve for a pipeline invocation."""

    identify: IdentifyResult
    resolve: Optional[ResolveResult] = None
    errors: List[str] = field(default_factory=list)

    def succeeded(self) -> bool:
        return not self.errors


class BasePipeline(ABC):
    """Abstract base class for all identify/resolve pipelines."""

    #: Unique identifier for the pipeline used in storage and routing.
    slug: str
    #: Human-friendly name displayed in the UI documentation.
    title: str
    #: Short description of the pipeline purpose.
    description: str = ""

    def __init__(self) -> None:
        if not getattr(self, "slug", None):
            raise ValueError("Pipeline subclasses must define a slug")
        if not getattr(self, "title", None):
            raise ValueError("Pipeline subclasses must define a title")

    @abstractmethod
    def identify(self, context: PipelineContext) -> IdentifyResult:
        """Return accessibility issues detected by this pipeline."""

    def resolve(self, context: PipelineContext, identify: IdentifyResult) -> ResolveResult:
        """Optional step to attempt automatic remediation.

        Subclasses should override only when they can produce a fixed PDF.
        """
        raise PipelineError("Resolve step not implemented for this pipeline")

    def run(self, context: PipelineContext, attempt_resolve: bool = False) -> PipelineRunResult:
        """Execute identify (and optional resolve) phase with safety guards."""
        errors: List[str] = []
        identify_result: Optional[IdentifyResult] = None
        resolve_result: Optional[ResolveResult] = None

        try:
            identify_result = self.identify(context)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"identify_failed: {exc}")

        if identify_result and attempt_resolve:
            try:
                resolve_result = self.resolve(context, identify_result)
            except PipelineError as exc:
                errors.append(f"resolve_not_supported: {exc}")
            except Exception as exc:  # noqa: BLE001
                errors.append(f"resolve_failed: {exc}")

        if identify_result is None:
            identify_result = IdentifyResult(pipeline_slug=self.slug, findings=[])

        return PipelineRunResult(identify=identify_result, resolve=resolve_result, errors=errors)


__all__ = [
    "BasePipeline",
    "IdentifyFinding",
    "IdentifyResult",
    "PipelineContext",
    "PipelineError",
    "PipelineRunResult",
    "ResolveChange",
    "ResolveResult",
]
