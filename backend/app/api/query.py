import json
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session
from app.db.database import get_db
from app.models.document import Document
from app.services.embedder import embed_text
from app.services.vector_store import hybrid_search
from app.services.llm import stream_answer, should_abstain


router = APIRouter()


class QueryRequest(BaseModel):
    question: str
    document_id: str = None
    k: int = 5


@router.post("/query")
def query_documents(req: QueryRequest, db: Session = Depends(get_db)):
    if not req.question.strip():
        raise HTTPException(status_code=400, detail="Question cannot be empty")

    if req.document_id:
        doc = db.query(Document).filter(Document.id == req.document_id).first()
        if not doc:
            raise HTTPException(status_code=404, detail="Document not found")
        if doc.status != "completed":
            raise HTTPException(status_code=400, detail=f"Document is not ready (status: {doc.status})")

    embedding = embed_text(req.question)
    chunks = hybrid_search(db, embedding, req.question, document_id=req.document_id, k=req.k)

    citations = [
        {"page_number": c["page_number"], "score": round(c["score"], 4)}
        for c in chunks
    ]
    abstaining = should_abstain(chunks)

    def event_stream():
        # send citations metadata first
        meta = {"type": "meta", "citations": citations, "abstaining": abstaining}
        yield f"data: {json.dumps(meta)}\n\n"

        for token in stream_answer(req.question, chunks):
            payload = {"type": "token", "text": token}
            yield f"data: {json.dumps(payload)}\n\n"

        yield "data: {\"type\": \"done\"}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.post("/query/benchmark")
def query_benchmark(req: QueryRequest, db: Session = Depends(get_db)):
    """Non-streaming endpoint for load testing — returns full answer as JSON."""
    if not req.question.strip():
        raise HTTPException(status_code=400, detail="Question cannot be empty")

    if req.document_id:
        doc = db.query(Document).filter(Document.id == req.document_id).first()
        if not doc:
            raise HTTPException(status_code=404, detail="Document not found")
        if doc.status != "completed":
            raise HTTPException(status_code=400, detail=f"Document is not ready (status: {doc.status})")

    embedding = embed_text(req.question)
    chunks = hybrid_search(db, embedding, req.question, document_id=req.document_id, k=req.k)

    citations = [
        {"page_number": c["page_number"], "score": round(c["score"], 4)}
        for c in chunks
    ]
    abstaining = should_abstain(chunks)
    answer = "".join(stream_answer(req.question, chunks))

    return {"answer": answer, "citations": citations, "abstaining": abstaining}


@router.post("/query/retrieval-benchmark")
def retrieval_benchmark(req: QueryRequest, db: Session = Depends(get_db)):
    """Measures embed + hybrid retrieval latency only — no LLM generation call."""
    import time
    if not req.question.strip():
        raise HTTPException(status_code=400, detail="Question cannot be empty")

    t0 = time.perf_counter()
    embedding = embed_text(req.question)
    embed_ms = round((time.perf_counter() - t0) * 1000, 1)

    t1 = time.perf_counter()
    chunks = hybrid_search(db, embedding, req.question, document_id=req.document_id, k=req.k)
    search_ms = round((time.perf_counter() - t1) * 1000, 1)

    return {
        "embed_ms": embed_ms,
        "search_ms": search_ms,
        "total_ms": round(embed_ms + search_ms, 1),
        "chunks_returned": len(chunks),
        "top_score": round(chunks[0]["score"], 6) if chunks else 0,
    }
