from fastapi import APIRouter, Depends, UploadFile, File, HTTPException
from sqlalchemy.orm import Session
from typing import List
import os
import shutil
import uuid
from datetime import datetime

from app.database import get_db
from app import crud
from app.schemas import PDFDocumentCreate, PDFDocumentResponse

router = APIRouter()

@router.post("/upload", response_model=List[PDFDocumentResponse])
async def upload_pdfs(
    files: List[UploadFile] = File(...),
    db: Session = Depends(get_db)
):
    """Upload one or more PDF files"""

    uploaded_files = []
    upload_dir = "input_pdfs"
    os.makedirs(upload_dir, exist_ok=True)

    for file in files:
        if not file.filename.lower().endswith('.pdf'):
            raise HTTPException(status_code=400, detail=f"File {file.filename} is not a PDF")

        file_id = str(uuid.uuid4())
        original_filename = os.path.basename(file.filename) or file.filename
        if not original_filename:
            original_filename = f"{file_id}.pdf"

        # Generate unique filename for storage to avoid collisions
        file_extension = os.path.splitext(original_filename)[1] or ".pdf"
        unique_filename = f"{file_id}{file_extension}"
        file_path = os.path.join(upload_dir, unique_filename)

        # Save uploaded file
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        # Create database record
        pdf_document = PDFDocumentCreate(
            filename=original_filename,
            original_filename=original_filename,
            file_path=file_path
        )

        db_document = crud.create_pdf_document(db=db, pdf_document=pdf_document)
        uploaded_files.append(db_document)

    return uploaded_files
