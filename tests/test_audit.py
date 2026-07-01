# # EUNICE - Efficient Unified Neural Intelligence for Communication and Execution
# Copyright 2026 Ronny Koome
# Licensed under the Elastic License 2.0.
# See LICENSE for details.

"""EUNICE Enterprise — Audit logging tests."""
import json
import pytest
import memory.sqlite_store
import memory.vector_store
import core.audit
import config as config_module
from core.audit import AuditLogger
from core.tool_router import ToolRouter
from core.agent import ReActAgent
from memory.manager import MemoryManager

config_module.API_KEY = "test-api-key"
config_module.JWT_SECRET = "test-secret-32-bytes-long-1234567890"

from fastapi.testclient import TestClient
from api.server import app, audit_logger as server_audit_logger


@pytest.fixture
def audit_log(tmp_path):
    """Provide a fresh audit logger pointing at a temp file."""
    path = tmp_path / "audit.log"
    logger = AuditLogger(path)
    # Patch the global singleton so production code writes here too
    core.audit._default_logger = logger
    # Patch the server module's reference
    import api.server
    api.server.audit_logger = logger
    yield logger
    core.audit._default_logger = None
    api.server.audit_logger = server_audit_logger


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
    memory.sqlite_store.DB_PATH = tmp_path / "test_audit_client.db"
    return TestClient(app)


def test_audit_logger_appends_entries(audit_log):
    audit_log.log_auth_event("login", user_id="u1", status="success")
    audit_log.log_auth_event("logout", user_id="u1", status="success")
    entries = audit_log.read()
    assert len(entries) == 2
    assert entries[0]["event_type"] == "auth_event"
    assert entries[0]["actor"] == "u1"


def test_audit_logger_filters(audit_log):
    audit_log.log_memory_access("read", user_id="u1", resource="facts")
    audit_log.log_memory_access("write", user_id="u2", resource="facts")
    entries = audit_log.read(event_type="memory_access", user_id="u1")
    assert len(entries) == 1
    assert entries[0]["actor"] == "u1"


def test_audit_log_is_append_only(audit_log):
    audit_log.log_auth_event("login", user_id="u1", status="success")
    first = audit_log.read()
    audit_log.log_auth_event("logout", user_id="u1", status="success")
    second = audit_log.read()
    assert len(second) == len(first) + 1
    assert first[0] == second[0]


@pytest.mark.asyncio
async def test_tool_call_is_audited(router, mm, audit_log):
    mm.ensure_user("tool_user")
    await router.execute("notes", {"action": "read", "user_id": "tool_user"})
    entries = audit_log.read(event_type="tool_call")
    assert len(entries) == 1
    assert entries[0]["resource"] == "tool:notes"
    assert entries[0]["actor"] == "tool_user"
    assert entries[0]["status"] == "success"


@pytest.mark.asyncio
async def test_tool_denial_is_audited(router, mm, audit_log):
    mm.sqlite.create_role("notes_only", "Notes Only", ["chat", "tool:notes"])
    mm.ensure_user("restricted_user", role_id="notes_only")
    await router.execute("get_balance", {"user_id": "restricted_user"})
    entries = audit_log.read(event_type="tool_call")
    assert len(entries) == 1
    assert entries[0]["resource"] == "tool:get_balance"
    assert entries[0]["status"] == "denied"


def test_memory_write_is_audited(mm, audit_log):
    mm.ensure_user("mem_user")
    mm.store_fact("I audit things", user_id="mem_user")
    entries = audit_log.read(event_type="memory_access")
    assert any(e["action"] == "write" and e["actor"] == "mem_user" for e in entries)


def test_memory_read_is_audited(mm, audit_log):
    mm.ensure_user("mem_user")
    mm.store_fact("I audit things", user_id="mem_user")
    audit_log.read()  # clear previous entries from fixture? No, just read all
    mm.retrieve("audit", user_id="mem_user")
    entries = audit_log.read(event_type="memory_access")
    read_entries = [e for e in entries if e["action"] == "read" and e["actor"] == "mem_user"]
    assert len(read_entries) >= 1


def test_permission_denied_is_audited(mm, audit_log):
    mm.sqlite.create_role("reader", "Reader", ["chat", "memory:read"])
    mm.ensure_user("reader_user", role_id="reader")
    with pytest.raises(PermissionError):
        mm.store_fact("secret", user_id="reader_user")
    entries = audit_log.read(event_type="permission_denied")
    assert len(entries) == 1
    assert entries[0]["actor"] == "reader_user"
    assert entries[0]["details"]["permission"] == "memory:write"


@pytest.mark.asyncio
async def test_agent_denial_is_audited(mm, audit_log, monkeypatch):
    mm.sqlite.create_role("no_agent", "No Agent", ["chat", "memory:read", "memory:write", "tool:*"])
    mm.ensure_user("no_agent_user", role_id="no_agent")

    async def fake_generate(*, prompt, format_json=False):
        return "Final Answer: 42"

    monkeypatch.setattr("core.agent.generate_non_stream", fake_generate)
    agent = ReActAgent(memory=mm, tools=ToolRouter(sqlite_store=mm.sqlite))

    events = []
    async for e in agent.run(goal="test", session="s1", user_id="no_agent_user"):
        events.append(e)

    entries = audit_log.read(event_type="permission_denied")
    assert any(e["actor"] == "no_agent_user" and e["details"]["permission"] == "reasoning:run" for e in entries)


@pytest.mark.asyncio
async def test_agent_step_is_audited(mm, audit_log, monkeypatch):
    mm.ensure_user("agent_user")

    async def fake_generate(*, prompt, format_json=False):
        return "Thought: I think\nAction: get_balance({})"

    monkeypatch.setattr("core.agent.generate_non_stream", fake_generate)

    # Patch ToolRouter.execute to avoid real subprocess and permission issues
    async def fake_execute(self, tool_name, params, permissions=None):
        return "balance: 100"

    monkeypatch.setattr(ToolRouter, "execute", fake_execute)

    agent = ReActAgent(memory=mm, tools=ToolRouter(sqlite_store=mm.sqlite))

    events = []
    async for e in agent.run(goal="test", session="s1", user_id="agent_user", max_steps=1):
        events.append(e)

    entries = audit_log.read(event_type="reasoning_step")
    assert len(entries) == 1
    assert entries[0]["actor"] == "agent_user"
    assert entries[0]["details"]["action"] == "get_balance"


# --- /audit endpoint ---

def test_audit_endpoint_requires_audit_read_permission(client, audit_log):
    import uuid
    device = f"no-audit-device-{uuid.uuid4().hex[:8]}"
    headers = {"Authorization": "Bearer test-api-key", "X-EUNICE-Device-ID": device}
    r = client.get("/audit", headers=headers)
    assert r.status_code == 403


def test_audit_endpoint_returns_entries_for_auditor(client, audit_log):
    import uuid
    import api.server

    device = f"auditor-device-{uuid.uuid4().hex[:8]}"
    headers = {"Authorization": "Bearer test-api-key", "X-EUNICE-Device-ID": device}

    # Create a real identity for this device
    r = client.post("/identity/create", headers={"Authorization": "Bearer test-api-key"}, json={
        "display_name": "Auditor",
        "passphrase": "secret123",
        "device_id": device,
        "device_name": "Audit Workstation",
    })
    assert r.status_code == 200
    identity_id = r.json()["identity_id"]

    # Assign auditor role
    mm = api.server.memory
    mm.ensure_user(identity_id)
    mm.sqlite.assign_user_role(identity_id, role_id="auditor")

    # Add a known audit entry
    audit_log.log_auth_event("login", user_id="tester", status="success")

    r = client.get("/audit", headers=headers)
    assert r.status_code == 200
    data = r.json()
    assert "entries" in data
    assert any(e["actor"] == "tester" for e in data["entries"])
