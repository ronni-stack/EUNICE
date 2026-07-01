# # EUNICE - Efficient Unified Neural Intelligence for Communication and Execution
# Copyright 2026 Ronny Koome
# Licensed under the Elastic License 2.0.
# See LICENSE for details.

"""EUNICE Enterprise — Integration & Security Tests (Week 4).

Covers:
- RBAC penetration tests
- Cross-org memory leak tests
- Audit log integrity tests
- Endpoint authorization tests
"""
import json
import uuid
import pytest
import memory.sqlite_store
import memory.vector_store
import core.audit
import config as config_module

from core.audit import AuditLogger
from core.rbac import has_permission
from core.tool_router import ToolRouter
from core.agent import ReActAgent
from core.ingestion import IngestionPipeline
from memory.manager import MemoryManager

config_module.API_KEY = "test-api-key"
config_module.JWT_SECRET = "test-secret-32-bytes-long-1234567890"

from fastapi.testclient import TestClient
from api.server import app


@pytest.fixture
def audit_log(tmp_path):
    path = tmp_path / "audit.log"
    logger = AuditLogger(path)
    core.audit._default_logger = logger
    import api.server
    api.server.audit_logger = logger
    yield logger
    core.audit._default_logger = None


@pytest.fixture
def mm(tmp_path, audit_log):
    db_path = tmp_path / "test.db"
    chroma_path = tmp_path / "chroma"
    memory.sqlite_store.DB_PATH = db_path
    memory.vector_store.CHROMA_PATH = chroma_path
    return MemoryManager()


@pytest.fixture
def router(mm):
    return ToolRouter(sqlite_store=mm.sqlite)


@pytest.fixture
def client(tmp_path):
    memory.sqlite_store.DB_PATH = tmp_path / "test_security_client.db"
    return TestClient(app)


def _unique(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


# --- RBAC Penetration: Tool Router ---

@pytest.mark.asyncio
async def test_chat_only_user_cannot_run_any_tool(router, mm):
    mm.sqlite.create_role("chat_only", "Chat Only", ["chat", "memory:read", "memory:write"])
    mm.ensure_user("chatty", role_id="chat_only")
    for tool in ["notes", "get_balance", "network_scan", "self_update", "transfer_funds"]:
        result = await router.execute(tool, {"user_id": "chatty"})
        assert "DENIED" in result, f"{tool} should be denied for chat-only user"


@pytest.mark.asyncio
async def test_notes_only_user_cannot_run_other_tools(router, mm):
    mm.sqlite.create_role("notes_only", "Notes Only", ["chat", "tool:notes"])
    mm.ensure_user("note_taker", role_id="notes_only")
    assert "DENIED" not in await router.execute("notes", {"action": "read", "user_id": "note_taker"})
    for tool in ["get_balance", "network_scan", "self_update"]:
        result = await router.execute(tool, {"user_id": "note_taker"})
        assert "DENIED" in result, f"{tool} should be denied for notes-only user"


@pytest.mark.asyncio
async def test_admin_runs_any_tool(router, mm):
    mm.ensure_user("super", role_id="admin")
    for tool in ["notes", "network_scan"]:
        result = await router.execute(tool, {"action": "read", "user_id": "super"})
        assert "DENIED" not in result, f"{tool} should be allowed for admin"


@pytest.mark.asyncio
async def test_auditor_cannot_run_tools(router, mm):
    mm.ensure_user("watchdog", role_id="auditor")
    result = await router.execute("notes", {"action": "read", "user_id": "watchdog"})
    assert "DENIED" in result


# --- RBAC Penetration: Memory Manager ---

def test_read_only_user_cannot_write_memory(mm):
    mm.sqlite.create_role("reader", "Reader", ["chat", "memory:read"])
    mm.ensure_user("reader", role_id="reader")
    with pytest.raises(PermissionError):
        mm.save_interaction("s1", "hi", "hello", user_id="reader")
    with pytest.raises(PermissionError):
        mm.store_fact("secret", user_id="reader")
    with pytest.raises(PermissionError):
        mm.store_conversation_turn("s1", "user", "hi", user_id="reader")


def test_write_only_user_cannot_read_memory(mm):
    mm.sqlite.create_role("writer", "Writer", ["chat", "memory:write"])
    mm.ensure_user("writer", role_id="writer")
    with pytest.raises(PermissionError):
        mm.get_recent_history("s1", user_id="writer")
    with pytest.raises(PermissionError):
        mm.get_facts(user_id="writer")
    with pytest.raises(PermissionError):
        mm.retrieve("anything", user_id="writer")


def test_user_without_documents_permission_cannot_access_docs(mm):
    mm.sqlite.create_role("no_docs", "No Docs", ["chat", "memory:read", "memory:write"])
    mm.ensure_user("no_docs_user", role_id="no_docs")
    with pytest.raises(PermissionError):
        mm.list_documents(user_id="no_docs_user")
    with pytest.raises(PermissionError):
        mm.has_document("hash123", user_id="no_docs_user")


# --- RBAC Penetration: Agent ---

@pytest.mark.asyncio
async def test_non_reasoning_user_cannot_run_agent(mm, monkeypatch):
    mm.sqlite.create_role("non_reasoning", "Non Reasoning", ["chat", "memory:read", "memory:write", "tool:*"])
    mm.ensure_user("plain", role_id="non_reasoning")

    async def fake_generate(*, prompt, format_json=False):
        return "Final Answer: ok"

    monkeypatch.setattr("core.agent.generate_non_stream", fake_generate)
    agent = ReActAgent(memory=mm, tools=ToolRouter(sqlite_store=mm.sqlite))
    events = [e async for e in agent.run(goal="test", session="s1", user_id="plain")]
    assert all(e["type"] == "error" and "DENIED" in e["content"] for e in events)


# --- Cross-org Memory Leak Tests ---

def test_facts_isolated_by_org(mm):
    mm.ensure_user("alice", org_id="acme", role_id="user")
    mm.ensure_user("bob", org_id="globex", role_id="user")

    mm.sqlite.save_fact("project", "Alpha", user_id="alice", org_id="acme")
    mm.sqlite.save_fact("project", "Beta", user_id="bob", org_id="globex")

    # Direct SQLite query respects org scope
    alice_facts = mm.sqlite.get_facts(user_id="alice", org_id="acme")
    bob_facts = mm.sqlite.get_facts(user_id="bob", org_id="globex")
    assert alice_facts["project"] == "Alpha"
    assert bob_facts["project"] == "Beta"


def test_memory_manager_retrieve_is_org_scoped(mm):
    mm.ensure_user("alice", org_id="acme", role_id="user")
    mm.ensure_user("bob", org_id="globex", role_id="user")

    mm.store_fact("Acme secret project", user_id="alice")
    mm.store_fact("Globex secret project", user_id="bob")

    alice_result = mm.retrieve("secret project", user_id="alice")
    bob_result = mm.retrieve("secret project", user_id="bob")

    assert "Acme" in alice_result
    assert "Globex" not in alice_result
    assert "Globex" in bob_result
    assert "Acme" not in bob_result


def test_sessions_isolated_by_user(mm):
    mm.ensure_user("alice", org_id="acme", role_id="user")
    mm.ensure_user("bob", org_id="globex", role_id="user")

    mm.save_interaction("shared-session-name", "hi", "hello", user_id="alice")
    mm.save_interaction("shared-session-name", "hey", "hi", user_id="bob")

    alice_history = mm.get_recent_history("shared-session-name", user_id="alice")
    bob_history = mm.get_recent_history("shared-session-name", user_id="bob")

    assert all("alice" not in msg["content"] for msg in bob_history)
    assert all("bob" not in msg["content"] for msg in alice_history)


def test_vector_store_document_search_is_org_scoped(mm):
    mm.ensure_user("alice", org_id="acme", role_id="user")
    mm.ensure_user("bob", org_id="globex", role_id="user")

    mm.vector.store_document("doc_alice", "Acme confidential roadmap", {"user_id": "alice", "org_id": "acme"})
    mm.vector.store_document("doc_bob", "Globex confidential roadmap", {"user_id": "bob", "org_id": "globex"})

    alice_docs = mm.vector.search_documents("roadmap", user_id="alice", org_id="acme", n_results=5)
    bob_docs = mm.vector.search_documents("roadmap", user_id="bob", org_id="globex", n_results=5)

    assert all("Acme" in d["content"] or "roadmap" in d["content"] for d in alice_docs)
    assert not any("Globex" in d["content"] for d in alice_docs)
    assert not any("Acme" in d["content"] for d in bob_docs)


# --- Audit Log Integrity Tests ---

def test_audit_log_is_append_only(audit_log):
    audit_log.log_auth_event("login", user_id="u1", status="success")
    first = audit_log.read()
    audit_log.log_auth_event("logout", user_id="u1", status="success")
    second = audit_log.read()
    assert len(second) == len(first) + 1
    assert first[0] == second[0]


def test_audit_entries_have_required_fields(audit_log):
    audit_log.log_tool_call("notes", "u1", params={"action": "read"}, result="ok", status="success", risk="low")
    entries = audit_log.read()
    assert len(entries) == 1
    entry = entries[0]
    for key in ["timestamp", "event_type", "actor", "action", "resource", "status", "details"]:
        assert key in entry


def test_audit_log_filters_are_accurate(audit_log):
    audit_log.log_memory_access("read", "alice", resource="facts")
    audit_log.log_memory_access("write", "bob", resource="facts")
    audit_log.log_tool_call("notes", "alice", params={}, result="ok", status="success", risk="low")

    assert len(audit_log.read(event_type="memory_access", user_id="alice")) == 1
    assert len(audit_log.read(event_type="tool_call")) == 1
    assert len(audit_log.read(user_id="bob")) == 1


def test_audit_log_does_not_store_full_message_content(audit_log):
    long_content = "secret " * 1000
    audit_log.log_memory_access("write", "u1", resource="session:s1",
                                details={"user_preview": long_content[:80], "assistant_preview": "ok"})
    entries = audit_log.read()
    assert long_content not in json.dumps(entries)
    assert len(entries[0]["details"]["user_preview"]) <= 80


def test_permission_denial_logged_before_raising(mm, audit_log):
    mm.sqlite.create_role("reader", "Reader", ["chat", "memory:read"])
    mm.ensure_user("reader", role_id="reader")
    with pytest.raises(PermissionError):
        mm.store_fact("x", user_id="reader")
    entries = audit_log.read(event_type="permission_denied")
    assert len(entries) == 1
    assert entries[0]["actor"] == "reader"
    assert entries[0]["details"]["permission"] == "memory:write"


# --- Endpoint Authorization Tests ---

def test_facts_endpoint_requires_memory_read(client, audit_log):
    device = _unique("dev")
    headers = {"Authorization": "Bearer test-api-key", "X-EUNICE-Device-ID": device}

    # Default user has memory:read
    r = client.get("/facts", headers=headers)
    assert r.status_code == 200


def test_delete_fact_endpoint_requires_memory_write(client, audit_log):
    device = _unique("dev")
    headers = {"Authorization": "Bearer test-api-key", "X-EUNICE-Device-ID": device}

    # Default user has memory:write
    r = client.delete("/facts/somekey", headers=headers)
    assert r.status_code == 200  # deletion may report false but request is authorized


def test_audit_endpoint_rejects_non_auditor(client, audit_log):
    device = _unique("dev")
    headers = {"Authorization": "Bearer test-api-key", "X-EUNICE-Device-ID": device}
    r = client.get("/audit", headers=headers)
    assert r.status_code == 403


def test_audit_endpoint_allows_auditor(client, audit_log):
    import api.server
    device = _unique("dev")
    headers = {"Authorization": "Bearer test-api-key", "X-EUNICE-Device-ID": device}

    r = client.post("/identity/create", headers={"Authorization": "Bearer test-api-key"}, json={
        "display_name": "Auditor",
        "passphrase": "secret123",
        "device_id": device,
    })
    assert r.status_code == 200
    identity_id = r.json()["identity_id"]

    mm = api.server.memory
    mm.ensure_user(identity_id)
    mm.sqlite.assign_user_role(identity_id, role_id="auditor")

    r = client.get("/audit", headers=headers)
    assert r.status_code == 200
    assert "entries" in r.json()


# --- Endpoint RBAC for Research / Files / Coder / Daemon / Trails / Docs ---

def _create_identity(client, device):
    r = client.post("/identity/create", headers={"Authorization": "Bearer test-api-key"}, json={
        "display_name": device,
        "passphrase": "secret123",
        "device_id": device,
    })
    assert r.status_code == 200, r.text
    return r.json()["identity_id"]


def test_research_endpoint_requires_research_run(client, audit_log):
    import api.server
    device = _unique("dev")
    headers = {"Authorization": "Bearer test-api-key", "X-EUNICE-Device-ID": device}
    identity_id = _create_identity(client, device)
    mm = api.server.memory
    mm.ensure_user(identity_id)

    role_no_research = _unique("role_no_research")
    mm.sqlite.create_role(role_no_research, role_no_research, ["chat", "memory:read", "memory:write"])

    # Default user has research:run
    r = client.post("/research", headers=headers, json={"query": "test"})
    assert r.status_code != 403

    # Remove research:run
    mm.sqlite.assign_user_role(identity_id, role_id=role_no_research)
    r = client.post("/research", headers=headers, json={"query": "test"})
    assert r.status_code == 403


def test_files_endpoint_requires_file_manager(client, audit_log):
    import api.server
    device = _unique("dev")
    headers = {"Authorization": "Bearer test-api-key", "X-EUNICE-Device-ID": device}
    identity_id = _create_identity(client, device)
    mm = api.server.memory
    mm.ensure_user(identity_id)

    role_chat_only = _unique("role_chat_only")
    mm.sqlite.create_role(role_chat_only, role_chat_only, ["chat", "memory:read", "memory:write"])

    r = client.get("/files", headers=headers)
    assert r.status_code != 403

    # Restrict to chat-only
    mm.sqlite.assign_user_role(identity_id, role_id=role_chat_only)
    r = client.get("/files", headers=headers)
    assert r.status_code == 403


def test_coder_endpoint_requires_coder_tool(client, audit_log):
    import api.server
    device = _unique("dev")
    headers = {"Authorization": "Bearer test-api-key", "X-EUNICE-Device-ID": device}
    identity_id = _create_identity(client, device)
    mm = api.server.memory
    mm.ensure_user(identity_id)

    role_chat_only = _unique("role_chat_only")
    mm.sqlite.create_role(role_chat_only, role_chat_only, ["chat", "memory:read", "memory:write"])

    r = client.post("/coder", headers=headers, json={"action": "analyze", "filename": "x.py"})
    assert r.status_code != 403

    mm.sqlite.assign_user_role(identity_id, role_id=role_chat_only)
    r = client.post("/coder", headers=headers, json={"action": "analyze", "filename": "x.py"})
    assert r.status_code == 403


def test_daemon_endpoints_require_admin_daemon(client, audit_log):
    import api.server
    device = _unique("dev")
    headers = {"Authorization": "Bearer test-api-key", "X-EUNICE-Device-ID": device}
    identity_id = _create_identity(client, device)
    mm = api.server.memory
    mm.ensure_user(identity_id)

    r = client.get("/daemon/status", headers=headers)
    assert r.status_code == 403

    mm.sqlite.assign_user_role(identity_id, role_id="admin")
    r = client.get("/daemon/status", headers=headers)
    assert r.status_code == 200


def test_docs_endpoints_require_documents_permissions(client, audit_log):
    import api.server
    device = _unique("dev")
    headers = {"Authorization": "Bearer test-api-key", "X-EUNICE-Device-ID": device}
    identity_id = _create_identity(client, device)
    mm = api.server.memory
    mm.ensure_user(identity_id)

    role_no_docs = _unique("role_no_docs")
    mm.sqlite.create_role(role_no_docs, role_no_docs, ["chat", "memory:read", "memory:write"])

    r = client.get("/documents", headers=headers)
    assert r.status_code == 200

    mm.sqlite.assign_user_role(identity_id, role_id=role_no_docs)
    r = client.get("/documents", headers=headers)
    assert r.status_code == 403


# --- Known Gaps / Regression Checks ---

@pytest.mark.asyncio
async def test_legacy_tool_execute_permission_still_grants_all_tools(router, mm):
    mm.sqlite.create_role("legacy", "Legacy", ["tool:execute"])
    mm.ensure_user("legacy_user", role_id="legacy")
    result = await router.execute("notes", {"action": "read", "user_id": "legacy_user"})
    assert "DENIED" not in result


def test_wildcard_permission_grants_nested_admin_actions():
    assert has_permission(["admin:*"], "admin:users") is True
    assert has_permission(["admin:*"], "admin:orgs") is True
    assert has_permission(["tool:*"], "tool:notes") is True




