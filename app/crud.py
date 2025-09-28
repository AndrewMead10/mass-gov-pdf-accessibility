from sqlalchemy.orm import Session
from app.models import PDFDocument, ProcessingStatus, PDFPageResult
from app.schemas import PDFDocumentCreate
from typing import List, Optional
import json
from datetime import datetime

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

def delete_pdf_document(db: Session, document_id: int) -> bool:
    document = get_pdf_document(db, document_id)
    if document:
        # Delete related page results first to avoid orphans
        db.query(PDFPageResult).filter(PDFPageResult.document_id == document_id).delete()
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
