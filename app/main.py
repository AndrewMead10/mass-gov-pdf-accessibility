from fastapi import FastAPI, Request, Depends
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.database import init_db, get_db
from app.api import upload, documents, processing
from app import crud

app = FastAPI(title="PDF Accessibility Checker", version="1.0.0")

# Initialize database
init_db()

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")

# Templates
templates = Jinja2Templates(directory="templates")

# Include API routers
app.include_router(upload.router, prefix="/api", tags=["upload"])
app.include_router(documents.router, prefix="/api", tags=["documents"])
app.include_router(processing.router, prefix="/api", tags=["processing"])

@app.get("/")
async def home(request: Request):
    """Home page with upload interface"""
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/dashboard")
async def dashboard(request: Request, db: Session = Depends(get_db)):
    """Dashboard page showing all documents"""
    documents = crud.get_pdf_documents(db)
    return templates.TemplateResponse(
        "dashboard.html",
        {"request": request, "documents": documents}
    )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
