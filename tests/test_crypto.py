# # EUNICE - Efficient Unified Neural Intelligence for Communication and Execution
# Copyright 2026 Ronny Koome
# Licensed under the Elastic License 2.0.
# See LICENSE for details.

"""EUNICE Enterprise Week 6 — Encryption at rest tests."""
import sqlite3
import uuid

import pytest
from fastapi.testclient import TestClient

import config as config_module
import memory.sqlite_store

config_module.API_KEY = "test-api-key"
config_module.JWT_SECRET = "test-secret-32-bytes-long-1234567890"
import memory.sqlite_store
import memory.vector_store
from core.crypto import (
    decrypt,
    derive_org_key,
    encrypt,
    is_encrypted,
)
from memory.manager import MemoryManager


@pytest.fixture
def mm(tmp_path, monkeypatch):
    """MemoryManager with an isolated DB and encryption enabled."""
    db_path = tmp_path / "test_crypto.db"
    chroma_path = tmp_path / "test_crypto_chroma"
    memory.sqlite_store.DB_PATH = db_path
    memory.vector_store.CHROMA_PATH = chroma_path
    monkeypatch.setattr(config_module, "MASTER_KEY", "enterprise-master-key-32bytes!")
    return MemoryManager()


def _unique(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


@pytest.fixture
def client(tmp_path):
    """FastAPI test client (DB path patched for best-effort isolation)."""
    memory.sqlite_store.DB_PATH = tmp_path / "test_crypto_client.db"
    from api.server import app
    return TestClient(app)


# --- core/crypto primitives ---

def test_encrypt_decrypt_roundtrip():
    key = derive_org_key("master-key-32-bytes-long-1234", "default", b"salt" * 4)
    ct = encrypt("hello world", key)
    assert is_encrypted(ct)
    assert decrypt(ct, key) == "hello world"


def test_empty_and_none_pass_through():
    key = derive_org_key("master-key-32-bytes-long-1234", "default", b"salt" * 4)
    assert encrypt("", key) == ""
    assert encrypt(None, key) is None
    assert decrypt("", key) == ""
    assert decrypt(None, key) is None


def test_double_encryption_is_idempotent():
    key = derive_org_key("master-key-32-bytes-long-1234", "default", b"salt" * 4)
    ct = encrypt("secret", key)
    assert encrypt(ct, key) == ct


def test_cross_org_key_separation(mm):
    mm.sqlite.create_organization("org-a", "A Corp")
    mm.sqlite.create_organization("org-b", "B Corp")
    salt_a = mm.sqlite.get_org_crypto_salt("org-a")
    salt_b = mm.sqlite.get_org_crypto_salt("org-b")
    assert salt_a != salt_b

    key_a = derive_org_key(config_module.MASTER_KEY, "org-a", salt_a)
    key_b = derive_org_key(config_module.MASTER_KEY, "org-b", salt_b)
    assert key_a != key_b

    ct = encrypt("corp secret", key_a)
    assert decrypt(ct, key_a) == "corp secret"
    with pytest.raises(Exception):
        decrypt(ct, key_b)


# --- SQLite field encryption ---

def test_message_content_encrypted_at_rest(mm):
    user = _unique("user")
    mm.ensure_user(user)
    mm.save_interaction("sess-1", "hello encryption", "hi there", user_id=user)

    history = mm.get_recent_history("sess-1", n=5, user_id=user)
    assert any(m["content"] == "hello encryption" for m in history)

    with sqlite3.connect(memory.sqlite_store.DB_PATH) as conn:
        c = conn.cursor()
        c.execute("SELECT content FROM messages WHERE user_id = ?", (user,))
        raw = c.fetchone()[0]
    assert is_encrypted(raw)


def test_fact_value_encrypted_at_rest(mm):
    user = _unique("user")
    mm.ensure_user(user)
    mm.store_fact("Lives in Nairobi.", "location", user_id=user)

    facts = mm.get_facts(category="location", user_id=user)
    assert any("Nairobi" in v for v in facts.values())

    with sqlite3.connect(memory.sqlite_store.DB_PATH) as conn:
        c = conn.cursor()
        c.execute("SELECT value FROM facts WHERE user_id = ?", (user,))
        raw = c.fetchone()[0]
    assert is_encrypted(raw)


def test_reasoning_run_encrypted_at_rest(mm):
    user = _unique("user")
    mm.ensure_user(user)
    mm.sqlite.create_role("reasoner", "reasoner", [
        "chat", "memory:read", "memory:write", "reasoning:run"
    ])
    mm.sqlite.assign_user_role(user, role_id="reasoner")

    mm.create_reasoning_run("run-1", user, "sess-r", "trail-r", "solve the secret")
    mm.save_reasoning_step("run-1", 0, "think about secret", "noop", {}, "observed secret")

    run = mm.get_reasoning_run("run-1")
    assert run["goal"] == "solve the secret"
    assert run["steps"][0]["thought"] == "think about secret"
    assert run["steps"][0]["observation"] == "observed secret"

    with sqlite3.connect(memory.sqlite_store.DB_PATH) as conn:
        c = conn.cursor()
        c.execute("SELECT goal FROM reasoning_runs WHERE id = ?", ("run-1",))
        raw_goal = c.fetchone()[0]
        c.execute("SELECT thought, observation FROM reasoning_steps WHERE run_id = ?", ("run-1",))
        raw_thought, raw_obs = c.fetchone()
    assert is_encrypted(raw_goal)
    assert is_encrypted(raw_thought)
    assert is_encrypted(raw_obs)


def test_document_filename_encrypted_at_rest(mm):
    user = _unique("user")
    mm.ensure_user(user)
    mm.sqlite.create_role("doc_user", "doc_user", [
        "chat", "memory:read", "memory:write", "documents:read", "documents:write"
    ])
    mm.sqlite.assign_user_role(user, role_id="doc_user")

    mm.add_document_index("hash-1", user, "classified_plan.pdf", "application/pdf", 3)
    docs = mm.list_documents(user_id=user)
    assert docs[0]["filename"] == "classified_plan.pdf"

    with sqlite3.connect(memory.sqlite_store.DB_PATH) as conn:
        c = conn.cursor()
        c.execute("SELECT filename FROM documents WHERE doc_hash = ?", ("hash-1",))
        raw = c.fetchone()[0]
    assert is_encrypted(raw)


# --- ChromaDB document text encryption ---

def test_vector_document_text_encrypted(mm):
    user = _unique("user")
    mm.ensure_user(user)
    if mm.vector.documents is None:
        pytest.skip("embeddings not available")

    mm.vector.store_document(
        doc_id="doc-secret",
        text="classified research on quantum entanglement",
        metadata={"user_id": user, "org_id": "default"},
    )

    results = mm.vector.search_documents("quantum", user_id=user, org_id="default")
    assert any("classified research" in r["content"] for r in results)

    raw = mm.vector.documents.get(ids=["doc-secret"])["documents"][0]
    assert is_encrypted(raw)


# --- Fallback without master key ---

def test_no_master_key_keeps_plaintext(tmp_path, monkeypatch):
    db_path = tmp_path / "test_plain.db"
    chroma_path = tmp_path / "test_plain_chroma"
    memory.sqlite_store.DB_PATH = db_path
    memory.vector_store.CHROMA_PATH = chroma_path
    monkeypatch.setattr(config_module, "MASTER_KEY", "")

    mm = MemoryManager()
    user = _unique("user")
    mm.ensure_user(user)
    mm.save_interaction("sess-plain", "plain text", "ok", user_id=user)

    with sqlite3.connect(db_path) as conn:
        c = conn.cursor()
        c.execute("SELECT content FROM messages WHERE user_id = ?", (user,))
        raw = c.fetchone()[0]
    assert raw == "plain text"
    assert not is_encrypted(raw)


# --- Admin crypto status endpoint ---

def test_admin_crypto_status_endpoint(client, monkeypatch):
    import api.server

    monkeypatch.setattr(config_module, "MASTER_KEY", "enterprise-master-key-32bytes!")

    device = _unique("dev")
    headers = {"Authorization": "Bearer test-api-key", "X-EUNICE-Device-ID": device}

    r = client.post("/identity/create", headers={"Authorization": "Bearer test-api-key"}, json={
        "display_name": "Crypto Admin",
        "passphrase": "secret123",
        "device_id": device,
    })
    assert r.status_code == 200
    identity_id = r.json()["identity_id"]

    mm = api.server.memory
    mm.ensure_user(identity_id)
    mm.sqlite.assign_user_role(identity_id, role_id="admin")

    r = client.get("/admin/crypto/status", headers=headers)
    assert r.status_code == 200
    data = r.json()
    assert data["encryption_enabled"] is True
    assert data["master_key_configured"] is True
    assert any(o["org_id"] == "default" for o in data["organizations"])


def test_admin_crypto_status_rejects_non_admin(client):
    device = _unique("dev")
    headers = {"Authorization": "Bearer test-api-key", "X-EUNICE-Device-ID": device}
    r = client.get("/admin/crypto/status", headers=headers)
    assert r.status_code == 403
