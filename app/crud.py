from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.models import (
    PDFDocument,
    PDFPageResult,
    PipelineIssue,
    PipelineRun,
    PipelineRunStatus,
    ProcessingStatus,
)
from app.schemas import PDFDocumentCreate

def create_pdf_document(db: Session, pdf_document: PDFDocumentCreate) -> PDFDocument:
    db_document = PDFDocument(**pdf_document.dict())
    db.add(db_document)
    db.commit()
    db.refresh(db_document)
    return db_document

def get_pdf_document(db: Session, document_id: int) -> Optional[PDFDocument]:
    return db.query(PDFDocument).filter(PDFDocument.id == document_id).first()

def get_pdf_documents(db: Session, skip: int = 0, limit: int = 100) -> List[PDFDocument]:
    return (
        db.query(PDFDocument)
        .order_by(PDFDocument.upload_timestamp.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )

def update_document_status(db: Session, document_id: int, status: ProcessingStatus,
                          error_message: Optional[str] = None) -> Optional[PDFDocument]:
    document = get_pdf_document(db, document_id)
    if document:
        document.status = status
        if status == ProcessingStatus.PROCESSING:
            document.processing_started = datetime.utcnow()
        elif status in [ProcessingStatus.COMPLETED, ProcessingStatus.FAILED]:
            document.processing_completed = datetime.utcnow()
        if error_message:
            document.error_message = error_message
        db.commit()
        db.refresh(document)
    return document

def update_document_results(db: Session, document_id: int,
                          accessibility_report: dict,
                          tagged_pdf_path: str) -> Optional[PDFDocument]:
    document = get_pdf_document(db, document_id)
    if document:
        document.accessibility_report_json = accessibility_report
        document.tagged_pdf_path = tagged_pdf_path

        # Extract summary stats
        summary = accessibility_report.get("Summary", {})
        document.total_failed = summary.get("Failed", 0)
        document.total_passed = summary.get("Passed", 0)
        document.needs_manual_check = summary.get("Needs manual check", 0)

        document.status = ProcessingStatus.COMPLETED
        document.processing_completed = datetime.utcnow()

        db.commit()
        db.refresh(document)
    return document


def update_document_filename(
    db: Session,
    document_id: int,
    *,
    filename: str,
) -> Optional[PDFDocument]:
    """Persist a new display filename for a document."""
    document = get_pdf_document(db, document_id)
    if document:
        document.filename = filename
        db.commit()
        db.refresh(document)
    return document

def delete_pdf_document(db: Session, document_id: int) -> bool:
    document = get_pdf_document(db, document_id)
    if document:
        # Delete related page results first to avoid orphans
        db.query(PDFPageResult).filter(PDFPageResult.document_id == document_id).delete()

        run_ids = [run.id for run in document.pipeline_runs]
        if run_ids:
            db.query(PipelineIssue).filter(PipelineIssue.pipeline_run_id.in_(run_ids)).delete(
                synchronize_session=False
            )
            db.query(PipelineRun).filter(PipelineRun.id.in_(run_ids)).delete(
                synchronize_session=False
            )

        db.delete(document)
        db.commit()
        return True
    return False

# --- Per-page results CRUD ---

def create_page_result(
    db: Session,
    document_id: int,
    page_number: int,
    accessibility_report: dict
) -> PDFPageResult:
    summary = accessibility_report.get("Summary", {}) if accessibility_report else {}

    page_result = PDFPageResult(
        document_id=document_id,
        page_number=page_number,
        accessibility_report_json=accessibility_report,
        total_failed=summary.get("Failed", 0),
        total_passed=summary.get("Passed", 0),
        needs_manual_check=summary.get("Needs manual check", 0)
    )
    db.add(page_result)
    db.commit()
    db.refresh(page_result)
    return page_result

def get_page_results_for_document(db: Session, document_id: int) -> List[PDFPageResult]:
    return (
        db.query(PDFPageResult)
        .filter(PDFPageResult.document_id == document_id)
        .order_by(PDFPageResult.page_number.asc())
        .all()
    )

def get_page_result(db: Session, document_id: int, page_number: int) -> Optional[PDFPageResult]:
    return (
        db.query(PDFPageResult)
        .filter(PDFPageResult.document_id == document_id, PDFPageResult.page_number == page_number)
        .first()
    )

def delete_page_results_for_document(db: Session, document_id: int) -> int:
    return db.query(PDFPageResult).filter(PDFPageResult.document_id == document_id).delete()

def count_page_results_for_document(db: Session, document_id: int) -> int:
    return db.query(PDFPageResult).filter(PDFPageResult.document_id == document_id).count()


# --- Pipeline run helpers ---

def create_pipeline_run(
    db: Session,
    *,
    document_id: int,
    pipeline_slug: str,
    attempt_resolve: bool,
    status: PipelineRunStatus,
    identify_payload: Optional[Dict[str, Any]],
    resolve_payload: Optional[Dict[str, Any]],
    errors: Optional[List[str]],
) -> PipelineRun:
    run = PipelineRun(
        document_id=document_id,
        pipeline_slug=pipeline_slug,
        attempt_resolve=attempt_resolve,
        status=status,
        identify_payload=identify_payload,
        resolve_payload=resolve_payload,
        errors=errors or [],
    )
    db.add(run)
    db.flush()
    return run


def create_pipeline_issues(
    db: Session,
    *,
    pipeline_run_id: int,
    issues: List[Dict[str, Any]],
) -> None:
    if not issues:
        return
    records = [
        PipelineIssue(
            pipeline_run_id=pipeline_run_id,
            issue_code=item["issue_code"],
            summary=item["summary"],
            detail=item["detail"],
            pages=item.get("pages", []),
            wcag_references=item.get("wcag_references", []),
            extra=item.get("extra"),
        )
        for item in issues
    ]
    db.bulk_save_objects(records)


def finalize_pipeline_run(db: Session, run: PipelineRun) -> PipelineRun:
    run.completed_at = datetime.utcnow()
    db.commit()
    db.refresh(run)
    return run


def get_pipeline_runs_for_document(db: Session, document_id: int) -> List[PipelineRun]:
    return (
        db.query(PipelineRun)
        .filter(PipelineRun.document_id == document_id)
        .order_by(PipelineRun.created_at.asc())
        .all()
    )


def count_pipeline_runs_for_document(db: Session, document_id: int) -> int:
    return db.query(PipelineRun).filter(PipelineRun.document_id == document_id).count()
