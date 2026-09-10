from sqlalchemy.orm import Session
from sqlalchemy import text
from rank_bm25 import BM25Okapi

RRF_K = 60  # standard RRF constant


def _fetch_all_chunks(db: Session, document_id: str = None) -> list[dict]:
    doc_filter = f"AND document_id = '{document_id}'" if document_id else ""
    sql = f"""
        SELECT id, document_id, page_number, chunk_index, content
        FROM chunks
        WHERE embedding IS NOT NULL
        {doc_filter}
        ORDER BY document_id, page_number, chunk_index
    """
    rows = db.execute(text(sql)).fetchall()
    return [
        {
            "chunk_id": str(row.id),
            "document_id": str(row.document_id),
            "page_number": row.page_number,
            "chunk_index": row.chunk_index,
            "content": row.content,
        }
        for row in rows
    ]


def similarity_search(db: Session, embedding: list[float], document_id: str = None, k: int = 5) -> list[dict]:
    embedding_literal = "[" + ",".join(str(x) for x in embedding) + "]"
    doc_filter = f"AND document_id = '{document_id}'" if document_id else ""

    sql = f"""
        SELECT
            id, document_id, page_number, chunk_index, content,
            1 - (embedding <=> '{embedding_literal}'::vector) AS score
        FROM chunks
        WHERE embedding IS NOT NULL
        {doc_filter}
        ORDER BY embedding <=> '{embedding_literal}'::vector
        LIMIT {k}
    """
    rows = db.execute(text(sql)).fetchall()
    return [
        {
            "chunk_id": str(row.id),
            "document_id": str(row.document_id),
            "page_number": row.page_number,
            "chunk_index": row.chunk_index,
            "content": row.content,
            "score": float(row.score),
        }
        for row in rows
    ]


def bm25_search(chunks: list[dict], query: str, k: int = 5) -> list[dict]:
    if not chunks:
        return []
    tokenized_corpus = [c["content"].lower().split() for c in chunks]
    bm25 = BM25Okapi(tokenized_corpus)
    scores = bm25.get_scores(query.lower().split())
    ranked = sorted(zip(chunks, scores), key=lambda x: x[1], reverse=True)
    return [
        {**chunk, "score": float(score)}
        for chunk, score in ranked[:k]
        if score > 0
    ]


def hybrid_search(db: Session, embedding: list[float], query: str, document_id: str = None, k: int = 5) -> list[dict]:
    vector_results = similarity_search(db, embedding, document_id=document_id, k=k * 2)
    all_chunks = _fetch_all_chunks(db, document_id=document_id)
    bm25_results = bm25_search(all_chunks, query, k=k * 2)

    # RRF fusion: score = sum of 1/(rank + K) across both result lists
    rrf_scores: dict[str, float] = {}
    chunk_map: dict[str, dict] = {}

    for rank, chunk in enumerate(vector_results):
        cid = chunk["chunk_id"]
        rrf_scores[cid] = rrf_scores.get(cid, 0) + 1 / (rank + 1 + RRF_K)
        chunk_map[cid] = chunk

    for rank, chunk in enumerate(bm25_results):
        cid = chunk["chunk_id"]
        rrf_scores[cid] = rrf_scores.get(cid, 0) + 1 / (rank + 1 + RRF_K)
        chunk_map[cid] = chunk

    ranked = sorted(rrf_scores.items(), key=lambda x: x[1], reverse=True)[:k]
    return [
        {**chunk_map[cid], "score": round(score, 6)}
        for cid, score in ranked
    ]
