import uuid
from datetime import datetime
from sqlalchemy import Column, String, Integer, Float, DateTime, Text, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from pgvector.sqlalchemy import Vector
from app.db.database import Base


class Document(Base):
    __tablename__ = "documents"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    filename = Column(String, nullable=False)
    status = Column(String, default="pending")  # pending | processing | completed | failed
    total_pages = Column(Integer, default=0)
    total_chunks = Column(Integer, default=0)
    error = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Chunk(Base):
    __tablename__ = "chunks"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id = Column(UUID(as_uuid=True), ForeignKey("documents.id"), nullable=False)
    page_number = Column(Integer, nullable=False)
    chunk_index = Column(Integer, nullable=False)
    content = Column(Text, nullable=False)
    embedding = Column(Vector(3072), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
