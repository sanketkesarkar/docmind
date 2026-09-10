import os
import uuid
from pathlib import Path
from fastapi import APIRouter, UploadFile, File, HTTPException, Depends
from sqlalchemy.orm import Session
from app.db.database import get_db
from app.models.document import Document
from app.workers.ingestion import ingestion_queue, process_document
from app.config import settings

router = APIRouter()


@router.post("/upload")
async def upload_document(file: UploadFile = File(...), db: Session = Depends(get_db)):
    if not file.filename.endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported")

    document_id = str(uuid.uuid4())
    storage_path = Path(settings.STORAGE_PATH)
    storage_path.mkdir(parents=True, exist_ok=True)
    file_path = str(storage_path / f"{document_id}.pdf")

    contents = await file.read()
    with open(file_path, "wb") as f:
        f.write(contents)

    doc = Document(id=document_id, filename=file.filename, status="pending")
    db.add(doc)
    db.commit()

    ingestion_queue.enqueue(process_document, document_id, file_path)

    return {"document_id": document_id, "filename": file.filename, "status": "pending"}


@router.get("/documents/{document_id}")
def get_document_status(document_id: str, db: Session = Depends(get_db)):
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    return {
        "document_id": str(doc.id),
        "filename": doc.filename,
        "status": doc.status,
        "total_pages": doc.total_pages,
        "total_chunks": doc.total_chunks,
        "error": doc.error,
    }


@router.get("/documents")
def list_documents(db: Session = Depends(get_db)):
    docs = db.query(Document).order_by(Document.created_at.desc()).all()
    return [
        {
            "document_id": str(d.id),
            "filename": d.filename,
            "status": d.status,
            "total_pages": d.total_pages,
            "total_chunks": d.total_chunks,
        }
        for d in docs
    ]
