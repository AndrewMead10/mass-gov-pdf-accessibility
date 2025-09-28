"""Coordinator utilities for running accessibility pipelines."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List, Optional, Sequence

from .base import PipelineContext, PipelineRunResult
from . import iter_pipelines


@dataclass(slots=True)
class ManagerConfig:
    """Configuration options for the pipeline manager."""

    attempt_resolve: bool = False
    limit_to: Optional[Sequence[str]] = None


class PipelineManager:
    """Simple orchestrator that executes registered pipelines."""

    def __init__(self, config: Optional[ManagerConfig] = None) -> None:
        self.config = config or ManagerConfig()

    def _selected_pipelines(self):
        pipelines = list(iter_pipelines())
        if not self.config.limit_to:
            return pipelines
        selected = {slug for slug in self.config.limit_to}
        return [pipeline for pipeline in pipelines if pipeline.slug in selected]

    def run(self, context: PipelineContext) -> List[PipelineRunResult]:
        """Run pipelines with the supplied context."""
        results: List[PipelineRunResult] = []
        for pipeline in self._selected_pipelines():
            result = pipeline.run(context, attempt_resolve=self.config.attempt_resolve)
            results.append(result)
        return results


__all__ = ["ManagerConfig", "PipelineManager"]
