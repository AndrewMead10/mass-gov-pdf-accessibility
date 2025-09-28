from concurrent.futures import ThreadPoolExecutor, as_completed
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
import os
import threading
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from app.database import get_db
from app import crud
from app.models import ProcessingStatus, PipelineRunStatus
from app.pdf_accessibility_checker import PDFAccessibilityChecker
from app.schemas import ProcessingStatusResponse
from app.pipelines.base import PipelineContext, PipelineRunResult
from app.pipelines.manager import PipelineManager, ManagerConfig
from app.pipelines.helpers import serialize_findings

router = APIRouter()

# Default pool size can be overridden via PAGE_PROCESSING_WORKERS env var
PAGE_WORKER_FALLBACK = 8
PIPELINE_OUTPUT_ROOT = os.path.join("output_pdfs", "pipelines")
FILENAME_PIPELINE_SLUG = "filename-from-h1"


def _resolve_worker_count(total_pages: int) -> int:
    """Determine how many workers to use for per-page processing."""
    if total_pages <= 0:
        return 0

    configured = os.getenv("PAGE_PROCESSING_WORKERS")
    workers = PAGE_WORKER_FALLBACK
    if configured:
        try:
            workers = int(configured)
        except ValueError:
            # Fall back to default when the env var is not an integer
            workers = PAGE_WORKER_FALLBACK

    workers = max(1, workers)
    return min(total_pages, workers)


def _collect_page_reports(
    file_path: str,
    page_numbers: Iterable[int],
    credentials_file: Optional[str],
) -> List[Tuple[int, dict]]:
    """Run per-page accessibility checks in parallel and return ordered results."""
    pages = list(page_numbers)
    if not pages:
        return []

    max_workers = _resolve_worker_count(len(pages))
    thread_local = threading.local()

    def _get_checker() -> PDFAccessibilityChecker:
        checker = getattr(thread_local, "checker", None)
        if checker is None:
            checker = PDFAccessibilityChecker(credentials_file=credentials_file)
            thread_local.checker = checker
        return checker

    def _process_page(page_num: int) -> Tuple[int, dict]:
        checker = _get_checker()
        page_result = checker.check_accessibility(
            file_path,
            page_start=page_num,
            page_end=page_num,
            save_tagged_pdf=False,
        )
        return page_num, page_result["accessibility_report_json"]

    results: List[Tuple[int, dict]] = []
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_page = {executor.submit(_process_page, page): page for page in pages}
        for future in as_completed(future_to_page):
            page_num = future_to_page[future]
            try:
                results.append(future.result())
            except Exception as exc:
                # Cancel any pending tasks before bubbling up the error
                for pending_future in future_to_page:
                    pending_future.cancel()
                raise RuntimeError(f"Failed to process page {page_num}: {exc}") from exc

    results.sort(key=lambda item: item[0])
    return results


def _derive_pipeline_status(result: PipelineRunResult, attempt_resolve: bool) -> PipelineRunStatus:
    if not result.errors:
        return PipelineRunStatus.SUCCEEDED
    if attempt_resolve and result.resolve and result.identify.has_findings():
        return PipelineRunStatus.PARTIAL
    return PipelineRunStatus.FAILED


def _extract_filename_suggestion(result: PipelineRunResult) -> Optional[str]:
    """Return the suggested filename from a pipeline run when available."""
    if not result.resolve:
        return None

    for change in result.resolve.change_log:
        suggested = change.annotations.get("suggested_filename") if change.annotations else None
        if suggested:
            return os.path.basename(suggested)

    resolved_path = result.resolve.resolved_pdf_path
    if resolved_path:
        return Path(resolved_path).name

    return None

def process_pdf_background(document_id: int, db_url: str, credentials_file: str = None):
    """Background task to process PDF"""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    # Create new database session for background task
    engine = create_engine(db_url, connect_args={"check_same_thread": False})
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = SessionLocal()

    try:
        # Update status to processing
        crud.update_document_status(db, document_id, ProcessingStatus.PROCESSING)

        # Get document
        document = crud.get_pdf_document(db, document_id)
        if not document:
            return

        # Process PDF
        checker = PDFAccessibilityChecker(credentials_file=credentials_file)

        # 1) Run full-document check to produce tagged PDF and overall summary
        overall_result = checker.check_accessibility(document.file_path)

        # 2) Determine page count
        try:
            from pypdf import PdfReader
            reader = PdfReader(document.file_path)
            page_count = len(reader.pages)
        except Exception as e:
            # If unable to read page count, mark as failed
            raise RuntimeError(f"Failed to read PDF page count: {e}")

        # 3) Analyze each page in parallel and store results
        page_reports = _collect_page_reports(
            file_path=document.file_path,
            page_numbers=range(1, page_count + 1),
            credentials_file=credentials_file,
        )
        for page_num, accessibility_report in page_reports:
            crud.create_page_result(
                db=db,
                document_id=document_id,
                page_number=page_num,
                accessibility_report=accessibility_report,
            )

        # 4) Update document with overall results and mark as completed
        crud.update_document_results(
            db=db,
            document_id=document_id,
            accessibility_report=overall_result['accessibility_report_json'],
            tagged_pdf_path=overall_result['tagged_pdf_path']
        )

        # 5) Execute registered pipelines for detailed analysis
        attempt_resolve = os.getenv("PIPELINES_ATTEMPT_RESOLVE", "false").lower() in {"1", "true", "yes"}
        pipeline_output_dir = os.path.join(PIPELINE_OUTPUT_ROOT, str(document_id))
        os.makedirs(pipeline_output_dir, exist_ok=True)

        page_payloads: List[Dict[str, Any]] = [
            {
                "page_number": page_num,
                "report": accessibility_report,
            }
            for page_num, accessibility_report in page_reports
        ]

        pipeline_context = PipelineContext(
            document_id=document_id,
            pdf_path=document.file_path,
            document_report=overall_result['accessibility_report_json'],
            page_reports=page_payloads,
            output_dir=pipeline_output_dir,
            metadata={
                "tagged_pdf_path": overall_result['tagged_pdf_path'],
                "autotagged_pdf_path": overall_result.get('autotagged_pdf_path'),
                "source_pdf_path": overall_result.get('source_pdf_path', document.file_path),
                "page_count": page_count,
            },
            db_session=db,
        )

        manager = PipelineManager(ManagerConfig(attempt_resolve=attempt_resolve))
        pipeline_results = manager.run(pipeline_context)

        original_display_name = os.path.basename(document.original_filename) if document.original_filename else None
        chosen_display_name = original_display_name or document.filename

        for result in pipeline_results:
            identify_payload = {
                "summary": result.identify.summary,
                "generated_at": result.identify.generated_at.isoformat(),
                "findings": serialize_findings(result.identify.findings),
            }

            resolve_payload = None
            if result.resolve:
                resolve_payload = {
                    "resolved_pdf_path": result.resolve.resolved_pdf_path,
                    "notes": result.resolve.notes,
                    "generated_at": result.resolve.generated_at.isoformat(),
                    "change_log": [
                        {
                            "description": change.description,
                            "pages_impacted": list(change.pages_impacted),
                            "annotations": change.annotations,
                        }
                        for change in result.resolve.change_log
                    ],
                }

            status = _derive_pipeline_status(result, attempt_resolve)

            run_row = crud.create_pipeline_run(
                db=db,
                document_id=document_id,
                pipeline_slug=result.identify.pipeline_slug,
                attempt_resolve=attempt_resolve,
                status=status,
                identify_payload=identify_payload,
                resolve_payload=resolve_payload,
                errors=result.errors,
            )

            crud.create_pipeline_issues(
                db=db,
                pipeline_run_id=run_row.id,
                issues=identify_payload["findings"],
            )

            crud.finalize_pipeline_run(db, run_row)

            if result.identify.pipeline_slug == FILENAME_PIPELINE_SLUG:
                if not result.identify.findings:
                    chosen_display_name = original_display_name or chosen_display_name
                else:
                    suggestion = _extract_filename_suggestion(result)
                    if suggestion:
                        chosen_display_name = suggestion

        if chosen_display_name and chosen_display_name != document.filename:
            crud.update_document_filename(
                db=db,
                document_id=document_id,
                filename=chosen_display_name,
            )
            document.filename = chosen_display_name

    except Exception as e:
        crud.update_document_status(
            db, document_id, ProcessingStatus.FAILED,
            error_message=str(e)
        )
    finally:
        db.close()

@router.post("/process/{document_id}", response_model=ProcessingStatusResponse)
def start_processing(
    document_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """Start processing a PDF document"""
    document = crud.get_pdf_document(db, document_id=document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found")

    if document.status != ProcessingStatus.PENDING:
        raise HTTPException(
            status_code=400,
            detail=f"Document is already {document.status.value}"
        )

    # Start background processing
    credentials_file = "pdfservices-api-credentials.json" if os.path.exists("pdfservices-api-credentials.json") else None
    background_tasks.add_task(
        process_pdf_background,
        document_id,
        "sqlite:///./pdf_accessibility.db",
        credentials_file
    )

    # Update status to processing
    document = crud.update_document_status(db, document_id, ProcessingStatus.PROCESSING)

    return ProcessingStatusResponse(
        id=document.id,
        status=document.status,
        processing_started=document.processing_started,
        processing_completed=document.processing_completed,
        error_message=document.error_message
    )


def process_pdf_pages_background(document_id: int, db_url: str, credentials_file: str = None):
    """Background task to compute per-page results for an existing document"""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    engine = create_engine(db_url, connect_args={"check_same_thread": False})
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = SessionLocal()

    try:
        document = crud.get_pdf_document(db, document_id)
        if not document:
            return

        # Determine page count
        try:
            from pypdf import PdfReader
            reader = PdfReader(document.file_path)
            page_count = len(reader.pages)
        except Exception as e:
            raise RuntimeError(f"Failed to read PDF page count: {e}")

        # Create missing page results in parallel
        missing_pages = [
            page_num
            for page_num in range(1, page_count + 1)
            if not crud.get_page_result(db, document_id=document_id, page_number=page_num)
        ]

        page_reports = _collect_page_reports(
            file_path=document.file_path,
            page_numbers=missing_pages,
            credentials_file=credentials_file,
        )

        for page_num, accessibility_report in page_reports:
            crud.create_page_result(
                db=db,
                document_id=document_id,
                page_number=page_num,
                accessibility_report=accessibility_report,
            )
    finally:
        db.close()


@router.post("/process/{document_id}/pages")
def start_processing_pages(
    document_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """Start background job to compute per-page summaries for a document.
    Can be run on completed documents; only missing pages are computed.
    """
    document = crud.get_pdf_document(db, document_id=document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found")

    # Start background processing of pages
    credentials_file = "pdfservices-api-credentials.json" if os.path.exists("pdfservices-api-credentials.json") else None
    background_tasks.add_task(
        process_pdf_pages_background,
        document_id,
        "sqlite:///./pdf_accessibility.db",
        credentials_file
    )

    return {"message": "Per-page processing started"}
