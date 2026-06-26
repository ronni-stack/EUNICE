# # EUNICE - Efficient Unified Neural Intelligence for Communication and Execution
# Copyright 2026 Ronny Koome
# Licensed under the Elastic License 2.0.
# See LICENSE for details.

"""EUNICE v0.9 — Document Ingestion Tests"""
import pytest
import memory.sqlite_store
import memory.vector_store
import config as config_module
from core.ingestion import IngestionPipeline, chunk_text, clean_text, compute_hash
from memory.manager import MemoryManager

config_module.JWT_SECRET = "test-secret-32-bytes-long-1234567890"


@pytest.fixture
def pipeline(tmp_path):
    db_path = tmp_path / "test_ingestion.db"
    chroma_path = tmp_path / "chroma"
    memory.sqlite_store.DB_PATH = db_path
    memory.vector_store.CHROMA_PATH = chroma_path
    return IngestionPipeline(MemoryManager())


def test_compute_hash():
    h1 = compute_hash(b"hello")
    h2 = compute_hash(b"hello")
    h3 = compute_hash(b"world")
    assert h1 == h2
    assert h1 != h3
    assert len(h1) == 64


def test_clean_text():
    raw = "Hello\r\n\n\n\nWorld   spaces"
    cleaned = clean_text(raw)
    assert "\r" not in cleaned
    assert "   " not in cleaned
    assert "Hello" in cleaned
    assert "World" in cleaned


def test_chunk_text_basic():
    text = "\n\n".join([f"Paragraph {i} with some content here." for i in range(20)])
    chunks = chunk_text(text, chunk_size=100, overlap=20)
    assert len(chunks) > 1
    total = sum(len(c) for c in chunks)
    assert total >= len(text) * 0.8  # chunks cover most text


def test_chunk_text_overlap():
    text = "First paragraph.\n\nSecond paragraph.\n\nThird paragraph."
    chunks = chunk_text(text, chunk_size=50, overlap=10)
    joined = " ".join(chunks)
    assert "First paragraph" in joined
    assert "Second paragraph" in joined
    assert "Third paragraph" in joined


@pytest.mark.asyncio
async def test_ingest_text_file(pipeline):
    content = b"This is a test document. It has multiple sentences. " * 20
    result = await pipeline.ingest("test.txt", content, "user_1", chunk_size=100, overlap=20)

    assert result["status"] == "ingested"
    assert result["chunks"] > 0
    assert result["content_type"] == "txt"
    assert pipeline.memory.has_document(result["doc_hash"], "user_1")


@pytest.mark.asyncio
async def test_ingest_deduplication(pipeline):
    content = b"Unique content for deduplication test."
    result1 = await pipeline.ingest("doc.txt", content, "user_1")
    assert result1["status"] == "ingested"

    result2 = await pipeline.ingest("doc_copy.txt", content, "user_1")
    assert result2["status"] == "already_exists"
    assert result2["doc_hash"] == result1["doc_hash"]


@pytest.mark.asyncio
async def test_retrieve_relevant_chunks(pipeline):
    content = b"The capital of France is Paris. The Eiffel Tower is in Paris."
    await pipeline.ingest("france.txt", content, "user_1", chunk_size=50, overlap=10)

    chunks = pipeline.retrieve_relevant_chunks("What is the capital of France?", "user_1", n_results=2)
    assert len(chunks) > 0
    text = " ".join(c["content"] for c in chunks).lower()
    assert "paris" in text


@pytest.mark.asyncio
async def test_ingest_unsupported_type(pipeline):
    with pytest.raises(ValueError):
        await pipeline.ingest("image.png", b"not a doc", "user_1")
