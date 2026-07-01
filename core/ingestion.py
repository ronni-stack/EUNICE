# # EUNICE - Efficient Unified Neural Intelligence for Communication and Execution
# Copyright 2026 Ronny Koome
# Licensed under the Elastic License 2.0.
# See LICENSE for details.

"""EUNICE v0.9 — Document Ingestion (RAG Pipeline)

Extracts text from PDF/TXT/MD files, chunks it, embeds it, and stores it in
ChromaDB for retrieval during chat.
"""
import hashlib
import re
from pathlib import Path
from typing import List, Tuple

from memory.manager import MemoryManager

# Try to import PyMuPDF; fail gracefully if unavailable
PDF_AVAILABLE = False
try:
    import fitz  # PyMuPDF
    PDF_AVAILABLE = True
except ImportError:
    fitz = None


DEFAULT_CHUNK_SIZE = 512
DEFAULT_CHUNK_OVERLAP = 64


def compute_hash(content: bytes) -> str:
    """Compute SHA-256 hash of file content."""
    return hashlib.sha256(content).hexdigest()


def extract_text(filename: str, content: bytes) -> str:
    """Extract plain text from PDF, TXT, or MD files."""
    lower_name = filename.lower()

    if lower_name.endswith(".pdf"):
        if not PDF_AVAILABLE:
            raise RuntimeError("PDF support requires PyMuPDF. Run: pip install pymupdf")
        return _extract_pdf(content)

    if lower_name.endswith(".txt") or lower_name.endswith(".md"):
        # Try utf-8, fall back to latin-1
        try:
            return content.decode("utf-8")
        except UnicodeDecodeError:
            return content.decode("latin-1")

    raise ValueError(f"Unsupported file type: {filename}")


def _extract_pdf(content: bytes) -> str:
    """Extract text from PDF bytes using PyMuPDF."""
    text_parts = []
    with fitz.open(stream=content, filetype="pdf") as doc:
        for page in doc:
            text_parts.append(page.get_text())
    return "\n\n".join(text_parts)


def clean_text(text: str) -> str:
    """Normalize whitespace and strip noise."""
    text = re.sub(r"\r\n?", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]+", " ", text)
    return text.strip()


def chunk_text(text: str, chunk_size: int = DEFAULT_CHUNK_SIZE,
               overlap: int = DEFAULT_CHUNK_OVERLAP) -> List[str]:
    """
    Split text into overlapping chunks at paragraph boundaries when possible.
    Falls back to word boundaries if a paragraph is too long.
    """
    if not text:
        return []

    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    chunks = []
    current_chunk = []
    current_len = 0

    for para in paragraphs:
        para_len = len(para)

        # If a single paragraph exceeds chunk size, split it by sentences/words
        if para_len > chunk_size:
            if current_chunk:
                chunks.append(_join_chunk(current_chunk))
                current_chunk, current_len = _start_with_overlap(current_chunk, overlap)
            sub_chunks = _split_long_paragraph(para, chunk_size, overlap)
            chunks.extend(sub_chunks)
            continue

        # If adding this paragraph exceeds chunk size, finalize current chunk
        if current_len + para_len + 1 > chunk_size and current_chunk:
            chunks.append(_join_chunk(current_chunk))
            current_chunk, current_len = _start_with_overlap(current_chunk, overlap)

        current_chunk.append(para)
        current_len += para_len + 1

    if current_chunk:
        chunks.append(_join_chunk(current_chunk))

    return [c for c in chunks if c.strip()]


def _join_chunk(parts: List[str]) -> str:
    return "\n\n".join(parts)


def _start_with_overlap(parts: List[str], overlap: int) -> Tuple[List[str], int]:
    """Start a new chunk by carrying over the last paragraph(s) for overlap."""
    overlap_parts = []
    overlap_len = 0
    for part in reversed(parts):
        if overlap_len + len(part) + 1 > overlap and overlap_parts:
            break
        overlap_parts.insert(0, part)
        overlap_len += len(part) + 1
    return overlap_parts, overlap_len


def _split_long_paragraph(para: str, chunk_size: int, overlap: int) -> List[str]:
    """Split a long paragraph into sentence-aware chunks."""
    # Simple sentence splitting
    sentences = re.split(r'(?<=[.!?])\s+', para)
    chunks = []
    current = []
    current_len = 0

    for sent in sentences:
        sent_len = len(sent)
        if current_len + sent_len + 1 > chunk_size and current:
            chunks.append(" ".join(current))
            carry = []
            carry_len = 0
            for part in reversed(current):
                if carry_len + len(part) + 1 > overlap and carry:
                    break
                carry.insert(0, part)
                carry_len += len(part) + 1
            current = carry
            current_len = carry_len
        current.append(sent)
        current_len += sent_len + 1

    if current:
        chunks.append(" ".join(current))
    return chunks


class IngestionPipeline:
    """End-to-end document ingestion into vector memory."""

    def __init__(self, memory: MemoryManager = None):
        self.memory = memory or MemoryManager()

    async def ingest(self, filename: str, content: bytes, user_id: str,
                     chunk_size: int = DEFAULT_CHUNK_SIZE,
                     overlap: int = DEFAULT_CHUNK_OVERLAP) -> dict:
        """Ingest a document. Returns summary or raises on failure."""
        doc_hash = compute_hash(content)

        # Deduplication
        if self.memory.has_document(doc_hash, user_id):
            return {
                "status": "already_exists",
                "doc_hash": doc_hash,
                "filename": filename,
            }

        # Extract and chunk
        raw_text = extract_text(filename, content)
        text = clean_text(raw_text)
        chunks = chunk_text(text, chunk_size=chunk_size, overlap=overlap)

        if not chunks:
            return {
                "status": "empty",
                "doc_hash": doc_hash,
                "filename": filename,
                "chunks": 0,
            }

        # Store chunks in ChromaDB
        content_type = Path(filename).suffix.lower().lstrip(".") or "unknown"
        for idx, chunk in enumerate(chunks):
            chunk_id = f"doc_{user_id}_{doc_hash}_{idx}"
            org_id = self.memory._get_org_id(user_id)
            self.memory.vector.store_document(
                doc_id=chunk_id,
                text=chunk,
                metadata={
                    "user_id": user_id,
                    "org_id": org_id,
                    "doc_hash": doc_hash,
                    "filename": filename,
                    "chunk_index": idx,
                    "source": "upload",
                    "content_type": content_type,
                }
            )

        # Index in SQLite
        self.memory.add_document_index(doc_hash, user_id, filename, content_type, len(chunks))

        return {
            "status": "ingested",
            "doc_hash": doc_hash,
            "filename": filename,
            "chunks": len(chunks),
            "content_type": content_type,
        }

    def retrieve_relevant_chunks(self, query: str, user_id: str, n_results: int = 3) -> List[dict]:
        """Retrieve top-k document chunks relevant to the query."""
        org_id = self.memory._get_org_id(user_id)
        results = self.memory.vector.search_documents(query, n_results=n_results, user_id=user_id, org_id=org_id)
        return [
            {
                "content": r["content"],
                "filename": r["meta"].get("filename", "unknown"),
                "chunk_index": r["meta"].get("chunk_index", 0),
            }
            for r in results
        ]
