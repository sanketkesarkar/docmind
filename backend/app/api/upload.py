import uuid
from fastapi import APIRouter, UploadFile, File, HTTPException, Depends
from sqlalchemy.orm import Session
from app.db.database import get_db
from app.models.document import Document
from app.workers.ingestion import ingestion_queue, process_document
from app.services.storage import save_pdf
from rq import Retry

router = APIRouter()


@router.post("/upload")
async def upload_document(file: UploadFile = File(...), db: Session = Depends(get_db)):
    if not file.filename.endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported")

    document_id = str(uuid.uuid4())
    contents = await file.read()
    storage_key = save_pdf(document_id, contents)

    doc = Document(id=document_id, filename=file.filename, status="pending")
    db.add(doc)
    db.commit()

    ingestion_queue.enqueue(
        process_document,
        document_id,
        storage_key,
        job_timeout=1800,
        retry=Retry(max=3, interval=[10, 30, 60]),
    )

    return {"document_id": document_id, "filename": file.filename, "status": "pending"}


@router.get("/documents/{document_id}")
def get_document_status(document_id: uuid.UUID, db: Session = Depends(get_db)):
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
