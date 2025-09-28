"""Shared helpers available to pipeline implementations."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from .base import IdentifyFinding


def load_pdf_bytes(pdf_path: str) -> bytes:
    """Return the raw bytes for a PDF file."""
    path = Path(pdf_path)
    if not path.exists():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")
    return path.read_bytes()


def ensure_pipeline_output_dir(base_dir: str, pipeline_slug: str) -> str:
    """Ensure an output folder exists for a pipeline resolve run."""
    path = Path(base_dir) / pipeline_slug
    path.mkdir(parents=True, exist_ok=True)
    return str(path)


def extract_adobe_issue_nodes(report: Optional[Dict[str, Any]], issue_codes: Iterable[str]) -> List[Dict[str, Any]]:
    """Search the Adobe accessibility JSON for nodes matching issue codes."""
    if not report:
        return []
    codes = set(issue_codes)
    matches: List[Dict[str, Any]] = []

    def _walk(node: Any) -> None:
        if isinstance(node, dict):
            code = node.get("CheckId") or node.get("RuleId")
            if code and code in codes:
                matches.append(node)
            for value in node.values():
                _walk(value)
        elif isinstance(node, list):
            for item in node:
                _walk(item)

    _walk(report)
    return matches


def serialize_findings(findings: Iterable[IdentifyFinding]) -> List[Dict[str, Any]]:
    """Convert identify findings into a JSON-serialisable payload."""
    payload: List[Dict[str, Any]] = []
    for finding in findings:
        payload.append({
            "issue_code": finding.issue_code,
            "summary": finding.summary,
            "detail": finding.detail,
            "pages": list(finding.pages),
            "wcag_references": list(finding.wcag_references),
            "extra": finding.extra,
        })
    return payload


def dump_findings_to_json(findings: Iterable[IdentifyFinding], path: str) -> None:
    """Persist identify findings for debugging/development workflows."""
    data = serialize_findings(findings)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2)


__all__ = [
    "dump_findings_to_json",
    "ensure_pipeline_output_dir",
    "extract_adobe_issue_nodes",
    "load_pdf_bytes",
    "serialize_findings",
]
