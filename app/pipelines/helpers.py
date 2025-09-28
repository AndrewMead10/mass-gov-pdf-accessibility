"""Shared helpers available to pipeline implementations."""

from __future__ import annotations

import io
import json
import logging
import os
import re
import zipfile
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import openai
from adobe.pdfservices.operation.auth.service_principal_credentials import ServicePrincipalCredentials
from adobe.pdfservices.operation.exception.exceptions import (
    ServiceApiException,
    ServiceUsageException,
    SdkException,
)
from adobe.pdfservices.operation.pdf_services import PDFServices
from adobe.pdfservices.operation.pdf_services_media_type import PDFServicesMediaType
from adobe.pdfservices.operation.pdfjobs.jobs.extract_pdf_job import ExtractPDFJob
from adobe.pdfservices.operation.pdfjobs.params.extract_pdf.extract_element_type import (
    ExtractElementType,
)
from adobe.pdfservices.operation.pdfjobs.params.extract_pdf.extract_pdf_params import (
    ExtractPDFParams,
)
from adobe.pdfservices.operation.pdfjobs.result.extract_pdf_result import ExtractPDFResult
from dotenv import load_dotenv

from .base import IdentifyFinding


load_dotenv()

logger = logging.getLogger(__name__)


class PDFHeadingError(Exception):
    """Raised when a PDF does not expose a top-level H1 heading."""


def _pdf_services_client() -> PDFServices:
    client_id = os.getenv("ADOBE_CLIENT_ID") or os.getenv("PDF_SERVICES_CLIENT_ID")
    client_secret = os.getenv("ADOBE_CLIENT_SECRET") or os.getenv("PDF_SERVICES_CLIENT_SECRET")
    if not client_id or not client_secret:
        raise RuntimeError(
            "Adobe PDF Services credentials (ADOBE_CLIENT_ID/SECRET or PDF_SERVICES_CLIENT_ID/SECRET) must be set"
        )
    credentials = ServicePrincipalCredentials(client_id=client_id, client_secret=client_secret)
    return PDFServices(credentials=credentials)


def extract_structure_from_pdf(pdf_path: str) -> Dict[str, Any]:
    """Return structured data extracted via Adobe PDF Services."""
    try:
        with open(pdf_path, "rb") as handle:
            input_stream = handle.read()

        pdf_services = _pdf_services_client()
        input_asset = pdf_services.upload(input_stream=input_stream, mime_type=PDFServicesMediaType.PDF)

        extract_pdf_params = ExtractPDFParams(elements_to_extract=[ExtractElementType.TEXT])
        extract_pdf_job = ExtractPDFJob(input_asset=input_asset, extract_pdf_params=extract_pdf_params)

        location = pdf_services.submit(extract_pdf_job)
        pdf_services_response = pdf_services.get_job_result(location, ExtractPDFResult)

        result_asset = pdf_services_response.get_result().get_resource()
        stream_asset = pdf_services.get_content(result_asset)

        zip_bytes = stream_asset.get_input_stream()
    except (ServiceApiException, ServiceUsageException, SdkException) as exc:  # noqa: BLE001
        raise RuntimeError(f"Adobe PDF Services API error: {exc}") from exc
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"Unable to extract structure from PDF {pdf_path}: {exc}") from exc

    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zip_file:
        json_data = zip_file.read("structuredData.json")
        return json.loads(json_data)


def _iter_text_elements(structure_data: Dict[str, Any]):
    for element in structure_data.get("elements", []):
        if "Text" in element:
            content = (element.get("Text") or "").strip()
            if content:
                yield element, content


def has_h1_heading(structure_data: Dict[str, Any]) -> bool:
    """True when the structured payload contains a meaningful H1/Title node."""
    for element, content in _iter_text_elements(structure_data):
        if element.get("Path", "").endswith("/H1") and content:
            return True

    for element, content in _iter_text_elements(structure_data):
        if element.get("Path", "").endswith("/Title") and content:
            return True

    text_candidates = [content for _, content in _iter_text_elements(structure_data)]
    for text in text_candidates[:10]:
        upper = text.upper()
        if any(keyword in upper for keyword in ("FORM", "CERTIFICATE", "APPLICATION", "SALES")):
            return True
        if len(text) < 50 and not text.endswith(".") and text.isupper():
            return True
    return False


def get_h1_heading(structure_data: Dict[str, Any]) -> Optional[str]:
    """Return the first plausible H1 text extracted from Adobe structured data."""
    for element, content in _iter_text_elements(structure_data):
        if element.get("Path", "").endswith("/H1"):
            return content

    for element, content in _iter_text_elements(structure_data):
        if element.get("Path", "").endswith("/Title"):
            return content

    text_candidates = [content for _, content in _iter_text_elements(structure_data)]
    for text in text_candidates[:10]:
        upper = text.upper()
        if any(keyword in upper for keyword in ("FORM", "CERTIFICATE", "APPLICATION", "SALES")):
            return text
        if len(text) < 50 and not text.endswith(".") and text.isupper():
            return text
    return None


def check_pdf_for_h1(pdf_path: str, verbose: bool = False) -> str:
    """Return the H1 heading text or raise when none is present."""
    try:
        structure_data = extract_structure_from_pdf(pdf_path)
    except Exception as exc:  # noqa: BLE001
        if verbose:
            logger.error("Failed to extract structure for %s: %s", pdf_path, exc)
        raise

    if not has_h1_heading(structure_data):
        raise PDFHeadingError(f"PDF does not have an H1 heading: {pdf_path}")

    heading = get_h1_heading(structure_data)
    if not heading:
        raise PDFHeadingError(f"Adobe extraction yielded no usable H1 text for: {pdf_path}")
    return heading


_openai_client: Optional[openai.OpenAI] = None


def _openai() -> openai.OpenAI:
    global _openai_client
    if _openai_client is None:
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY environment variable not set; cannot generate filenames")
        _openai_client = openai.OpenAI(api_key=api_key)
    return _openai_client


def validate_filename(filename: str, h1_heading: str) -> Tuple[bool, str]:
    """Return whether filename mirrors the H1 heading and a reason explaining the decision."""
    filename_lower = filename.lower()
    h1_lower = h1_heading.lower()

    filename_words = set(re.findall(r"\w+", filename_lower))
    heading_words = set(re.findall(r"\w+", h1_lower))

    stop_words = {"the", "a", "an", "and", "or", "but", "of", "for", "in", "on", "to", "with"}
    heading_words = {word for word in heading_words if word not in stop_words and len(word) > 2}

    matches = len(filename_words.intersection(heading_words))
    has_hyphenation = "-" in filename

    if matches >= 2 and has_hyphenation:
        return True, "Filename matches H1 heading pattern"
    if not has_hyphenation:
        return False, "Filename should use hyphen separation"
    return False, "Filename doesn't contain enough words from the H1 heading"


def suggest_filename_with_openai(h1_heading: str, current_filename: str) -> str:
    """Generate an improved filename for the PDF via OpenAI, falling back to heuristics."""
    try:
        client = _openai()
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            max_tokens=100,
            temperature=0.0,
            messages=[
                {
                    "role": "user",
                    "content": (
                        "Given the H1 heading from a PDF: \"{heading}\"\n\nCurrent filename: \"{current}\"\n\n"
                        "Generate a better filename that:\n"
                        "1. Contains key words from the H1 heading\n"
                        "2. Uses hyphen-separation between words\n"
                        "3. Is all lowercase\n"
                        "4. Excludes common words like \"the\", \"and\", etc.\n"
                        "5. Is concise but descriptive\n\n"
                        "Return ONLY the suggested filename without any explanation or additional text."
                    ).format(heading=h1_heading, current=current_filename),
                }
            ],
        )

        suggested = (response.choices[0].message.content or "").strip()
        suggested = re.sub(r"[^\w\-]", "", suggested)
        return suggested
    except Exception as exc:  # noqa: BLE001
        logger.warning("OpenAI filename suggestion failed: %s", exc)
        words = re.findall(r"\w+", h1_heading.lower())
        words = [word for word in words if len(word) > 2 and word not in {"the", "and", "for", "with"}]
        return "-".join(words[:4])


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
    "PDFHeadingError",
    "check_pdf_for_h1",
    "dump_findings_to_json",
    "ensure_pipeline_output_dir",
    "extract_adobe_issue_nodes",
    "extract_structure_from_pdf",
    "get_h1_heading",
    "has_h1_heading",
    "load_pdf_bytes",
    "serialize_findings",
    "suggest_filename_with_openai",
    "validate_filename",
]
