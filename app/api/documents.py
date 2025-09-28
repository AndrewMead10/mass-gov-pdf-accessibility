from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from typing import List
import os

from app.database import get_db
from app import crud
from app.schemas import (
    PDFDocumentResponse,
    ProcessingStatusResponse,
    PDFPageResultResponse,
    PDFPageSummaryResponse,
)

router = APIRouter()

@router.get("/documents", response_model=List[PDFDocumentResponse])
def get_documents(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    """Get list of all documents (most recent first), with per-page count."""
    documents = crud.get_pdf_documents(db, skip=skip, limit=limit)
    # Attach page result counts for visibility
    enriched = []
    for d in documents:
        count = crud.count_page_results_for_document(db, d.id)
        # Create a lightweight view object with extra field
        d_dict = {
            'id': d.id,
            'filename': d.filename,
            'original_filename': d.original_filename,
            'file_path': d.file_path,
            'status': d.status,
            'upload_timestamp': d.upload_timestamp,
            'processing_started': d.processing_started,
            'processing_completed': d.processing_completed,
            'accessibility_report_json': d.accessibility_report_json,
            'tagged_pdf_path': d.tagged_pdf_path,
            'total_failed': d.total_failed,
            'total_passed': d.total_passed,
            'needs_manual_check': d.needs_manual_check,
            'error_message': d.error_message,
            'page_results_count': count,
        }
        enriched.append(d_dict)
    return enriched

@router.get("/documents/{document_id}", response_model=PDFDocumentResponse)
def get_document(document_id: int, db: Session = Depends(get_db)):
    """Get specific document details, with per-page count."""
    document = crud.get_pdf_document(db, document_id=document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found")
    count = crud.count_page_results_for_document(db, document_id)
    d = document
    return {
        'id': d.id,
        'filename': d.filename,
        'original_filename': d.original_filename,
        'file_path': d.file_path,
        'status': d.status,
        'upload_timestamp': d.upload_timestamp,
        'processing_started': d.processing_started,
        'processing_completed': d.processing_completed,
        'accessibility_report_json': d.accessibility_report_json,
        'tagged_pdf_path': d.tagged_pdf_path,
        'total_failed': d.total_failed,
        'total_passed': d.total_passed,
        'needs_manual_check': d.needs_manual_check,
        'error_message': d.error_message,
        'page_results_count': count,
    }

@router.get("/status/{document_id}", response_model=ProcessingStatusResponse)
def get_processing_status(document_id: int, db: Session = Depends(get_db)):
    """Get processing status for a document"""
    document = crud.get_pdf_document(db, document_id=document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found")

    return ProcessingStatusResponse(
        id=document.id,
        status=document.status,
        processing_started=document.processing_started,
        processing_completed=document.processing_completed,
        error_message=document.error_message
    )

@router.get("/download/{document_id}")
def download_processed_pdf(document_id: int, db: Session = Depends(get_db)):
    """Download the processed (tagged) PDF"""
    document = crud.get_pdf_document(db, document_id=document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found")

    if not document.tagged_pdf_path or not os.path.exists(document.tagged_pdf_path):
        raise HTTPException(status_code=404, detail="Processed PDF not found")

    return FileResponse(
        path=document.tagged_pdf_path,
        media_type='application/pdf',
        filename=f"tagged_{document.original_filename}"
    )

@router.get("/documents/{document_id}/pages", response_model=List[PDFPageSummaryResponse])
def get_document_page_summaries(document_id: int, db: Session = Depends(get_db)):
    """Get per-page summary results for a document"""
    document = crud.get_pdf_document(db, document_id=document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found")

    page_results = crud.get_page_results_for_document(db, document_id=document_id)
    return page_results

@router.get("/documents/{document_id}/pages/{page_number}", response_model=PDFPageResultResponse)
def get_document_page_detail(document_id: int, page_number: int, db: Session = Depends(get_db)):
    """Get detailed per-page result for a specific page"""
    document = crud.get_pdf_document(db, document_id=document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found")

    page_result = crud.get_page_result(db, document_id=document_id, page_number=page_number)
    if page_result is None:
        raise HTTPException(status_code=404, detail="Page result not found")
    return page_result

@router.delete("/documents/{document_id}")
def delete_document(document_id: int, db: Session = Depends(get_db)):
    """Delete a document and its files"""
    document = crud.get_pdf_document(db, document_id=document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found")

    # Delete files
    if os.path.exists(document.file_path):
        os.remove(document.file_path)
    if document.tagged_pdf_path and os.path.exists(document.tagged_pdf_path):
        os.remove(document.tagged_pdf_path)

    # Delete database record
    success = crud.delete_pdf_document(db, document_id=document_id)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to delete document")

    return {"message": "Document deleted successfully"}
