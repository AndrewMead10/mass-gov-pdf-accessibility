from pydantic import BaseModel
from datetime import datetime
from typing import Optional, Dict, Any, List
from app.models import ProcessingStatus

class PDFDocumentBase(BaseModel):
    filename: str
    original_filename: str

class PDFDocumentCreate(PDFDocumentBase):
    file_path: str

class PDFDocumentResponse(PDFDocumentBase):
    id: int
    status: ProcessingStatus
    upload_timestamp: datetime
    processing_started: Optional[datetime] = None
    processing_completed: Optional[datetime] = None
    total_failed: int = 0
    total_passed: int = 0
    needs_manual_check: int = 0
    error_message: Optional[str] = None
    accessibility_report_json: Optional[Dict[str, Any]] = None
    tagged_pdf_path: Optional[str] = None
    page_results_count: Optional[int] = None

    class Config:
        from_attributes = True

class ProcessingStatusResponse(BaseModel):
    id: int
    status: ProcessingStatus
    processing_started: Optional[datetime] = None
    processing_completed: Optional[datetime] = None
    error_message: Optional[str] = None


class PDFPageResultBase(BaseModel):
    page_number: int
    total_failed: int = 0
    total_passed: int = 0
    needs_manual_check: int = 0


class PDFPageResultResponse(PDFPageResultBase):
    id: int
    document_id: int
    accessibility_report_json: Optional[Dict[str, Any]] = None

    class Config:
        from_attributes = True


class PDFPageSummaryResponse(PDFPageResultBase):
    id: int
    document_id: int

    class Config:
        from_attributes = True
