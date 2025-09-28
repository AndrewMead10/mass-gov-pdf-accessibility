from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from typing import Any, Dict, List
import os

from app.database import get_db
from app import crud
from app.schemas import (
    PDFDocumentResponse,
    ProcessingStatusResponse,
    PDFPageResultResponse,
    PDFPageSummaryResponse,
    PipelineRunResponse,
)
from app.pipelines import get_pipeline

router = APIRouter()


def _serialize_pipeline_runs(runs) -> List[Dict[str, Any]]:
    payload: List[Dict[str, Any]] = []
    for run in runs:
        issues = sorted(run.issues, key=lambda issue: issue.id)
        try:
            pipeline = get_pipeline(run.pipeline_slug)
            pipeline_title = pipeline.title
            pipeline_description = pipeline.description
        except KeyError:
            slug = run.pipeline_slug or ""
            normalized_slug = slug.replace("-", " ").replace("_", " ")
            pipeline_title = normalized_slug.title() or slug
            pipeline_description = ""
        payload.append({
            'id': run.id,
            'document_id': run.document_id,
            'pipeline_slug': run.pipeline_slug,
            'pipeline_title': pipeline_title,
            'pipeline_description': pipeline_description,
            'attempt_resolve': run.attempt_resolve,
            'status': run.status,
            'identify_payload': run.identify_payload,
            'resolve_payload': run.resolve_payload,
            'errors': run.errors,
            'created_at': run.created_at,
            'completed_at': run.completed_at,
            'issues': [
                {
                    'id': issue.id,
                    'pipeline_run_id': issue.pipeline_run_id,
                    'issue_code': issue.issue_code,
                    'summary': issue.summary,
                    'detail': issue.detail,
                    'pages': issue.pages or [],
                    'wcag_references': issue.wcag_references or [],
                    'extra': issue.extra,
                }
                for issue in issues
            ],
        })
    return payload

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
            'pipeline_runs_count': crud.count_pipeline_runs_for_document(db, d.id),
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
    pipeline_runs = crud.get_pipeline_runs_for_document(db, document_id)
    pipeline_runs_payload = _serialize_pipeline_runs(pipeline_runs)
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
        'pipeline_runs_count': len(pipeline_runs_payload),
        'pipeline_runs': pipeline_runs_payload,
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

    download_name = document.filename or document.original_filename or os.path.basename(document.tagged_pdf_path)
    download_name = os.path.basename(download_name) if download_name else "document.pdf"

    return FileResponse(
        path=document.tagged_pdf_path,
        media_type='application/pdf',
        filename=download_name
    )

@router.get("/documents/{document_id}/pages", response_model=List[PDFPageSummaryResponse])
def get_document_page_summaries(document_id: int, db: Session = Depends(get_db)):
    """Get per-page summary results for a document"""
    document = crud.get_pdf_document(db, document_id=document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found")

    page_results = crud.get_page_results_for_document(db, document_id=document_id)
    return page_results

@router.get("/documents/{document_id}/pages/detailed", response_model=List[PDFPageResultResponse])
def get_document_page_details_all(document_id: int, db: Session = Depends(get_db)):
    """Get detailed per-page results for all pages of a document at once"""
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


@router.get("/documents/{document_id}/pipelines", response_model=List[PipelineRunResponse])
def get_document_pipeline_runs(document_id: int, db: Session = Depends(get_db)):
    """Return detailed pipeline runs for a document."""
    document = crud.get_pdf_document(db, document_id=document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found")

    runs = crud.get_pipeline_runs_for_document(db, document_id=document_id)
    return runs

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
