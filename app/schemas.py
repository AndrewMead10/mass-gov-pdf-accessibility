from __future__ import annotations

from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional, Dict, Any, List
from app.models import ProcessingStatus, PipelineRunStatus

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
    pipeline_runs_count: Optional[int] = None
    pipeline_runs: Optional[List["PipelineRunResponse"]] = None

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


class PipelineIssueResponse(BaseModel):
    id: int
    pipeline_run_id: int
    issue_code: str
    summary: str
    detail: str
    pages: List[int]
    wcag_references: List[str] = Field(default_factory=list)
    extra: Optional[Dict[str, Any]] = None

    class Config:
        from_attributes = True


class PipelineRunResponse(BaseModel):
    id: int
    document_id: int
    pipeline_slug: str
    pipeline_title: Optional[str] = None
    pipeline_description: Optional[str] = None
    attempt_resolve: bool
    status: PipelineRunStatus
    identify_payload: Optional[Dict[str, Any]] = None
    resolve_payload: Optional[Dict[str, Any]] = None
    errors: Optional[List[str]] = None
    created_at: datetime
    completed_at: datetime
    issues: List[PipelineIssueResponse] = Field(default_factory=list)

    class Config:
        from_attributes = True


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
