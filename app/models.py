from sqlalchemy import Column, Integer, String, DateTime, JSON, Enum as SQLEnum, ForeignKey, UniqueConstraint
from sqlalchemy.orm import relationship
from datetime import datetime
import enum
from app.database import Base

class ProcessingStatus(enum.Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"

class PDFDocument(Base):
    __tablename__ = "pdf_documents"

    id = Column(Integer, primary_key=True, index=True)
    filename = Column(String, nullable=False)
    original_filename = Column(String, nullable=False)
    file_path = Column(String, nullable=False)
    status = Column(SQLEnum(ProcessingStatus), default=ProcessingStatus.PENDING)
    upload_timestamp = Column(DateTime, default=datetime.utcnow)
    processing_started = Column(DateTime, nullable=True)
    processing_completed = Column(DateTime, nullable=True)

    # Store complete accessibility report JSON
    accessibility_report_json = Column(JSON, nullable=True)
    tagged_pdf_path = Column(String, nullable=True)

    # Summary stats extracted from JSON for quick access
    total_failed = Column(Integer, default=0)
    total_passed = Column(Integer, default=0)
    needs_manual_check = Column(Integer, default=0)
    error_message = Column(String, nullable=True)

    # Relationship to per-page results
    page_results = relationship(
        "PDFPageResult",
        back_populates="document",
        cascade="all, delete-orphan"
    )


class PDFPageResult(Base):
    __tablename__ = "pdf_page_results"

    id = Column(Integer, primary_key=True, index=True)
    document_id = Column(Integer, ForeignKey("pdf_documents.id"), nullable=False, index=True)
    page_number = Column(Integer, nullable=False)

    # Store page-specific accessibility report JSON
    accessibility_report_json = Column(JSON, nullable=True)

    # Summary stats for this page
    total_failed = Column(Integer, default=0)
    total_passed = Column(Integer, default=0)
    needs_manual_check = Column(Integer, default=0)

    document = relationship("PDFDocument", back_populates="page_results")

    __table_args__ = (
        UniqueConstraint('document_id', 'page_number', name='uix_document_page'),
    )
