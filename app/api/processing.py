from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
import os

from app.database import get_db
from app import crud
from app.models import ProcessingStatus
from app.pdf_accessibility_checker import PDFAccessibilityChecker
from app.schemas import ProcessingStatusResponse

router = APIRouter()

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

        # 3) Analyze each page individually and store results
        for page_num in range(1, page_count + 1):
            page_result = checker.check_accessibility(
                document.file_path,
                page_start=page_num,
                page_end=page_num,
                save_tagged_pdf=False,
            )
            crud.create_page_result(
                db=db,
                document_id=document_id,
                page_number=page_num,
                accessibility_report=page_result['accessibility_report_json']
            )

        # 4) Update document with overall results and mark as completed
        crud.update_document_results(
            db=db,
            document_id=document_id,
            accessibility_report=overall_result['accessibility_report_json'],
            tagged_pdf_path=overall_result['tagged_pdf_path']
        )

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

        checker = PDFAccessibilityChecker(credentials_file=credentials_file)

        # Determine page count
        try:
            from pypdf import PdfReader
            reader = PdfReader(document.file_path)
            page_count = len(reader.pages)
        except Exception as e:
            raise RuntimeError(f"Failed to read PDF page count: {e}")

        # Create missing page results only
        for page_num in range(1, page_count + 1):
            existing = crud.get_page_result(db, document_id=document_id, page_number=page_num)
            if existing:
                continue
            page_result = checker.check_accessibility(
                document.file_path,
                page_start=page_num,
                page_end=page_num,
                save_tagged_pdf=False,
            )
            crud.create_page_result(
                db=db,
                document_id=document_id,
                page_number=page_num,
                accessibility_report=page_result['accessibility_report_json']
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
