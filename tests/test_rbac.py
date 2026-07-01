# # EUNICE - Efficient Unified Neural Intelligence for Communication and Execution
# Copyright 2026 Ronny Koome
# Licensed under the Elastic License 2.0.
# See LICENSE for details.

"""EUNICE Enterprise — Role-Based Access Control tests."""
import pytest
import memory.sqlite_store
import memory.vector_store
from core.rbac import has_permission, get_user_permissions, DEFAULT_ROLE_PERMISSIONS
from core.tool_router import ToolRouter
from core.agent import ReActAgent
from memory.manager import MemoryManager


@pytest.fixture
def mm(tmp_path):
    db_path = tmp_path / "test.db"
    chroma_path = tmp_path / "chroma"
    memory.sqlite_store.DB_PATH = db_path
    memory.vector_store.CHROMA_PATH = chroma_path
    return MemoryManager()


@pytest.fixture
def router(mm):
    return ToolRouter(sqlite_store=mm.sqlite)


# --- has_permission ---

def test_has_permission_exact_match():
    assert has_permission(["chat", "memory:read"], "chat") is True


def test_has_permission_global_wildcard():
    assert has_permission(["*"], "anything:goes") is True


def test_has_permission_prefix_wildcard():
    assert has_permission(["tool:*"], "tool:notes") is True
    assert has_permission(["tool:*"], "tool:get_balance") is True


def test_has_permission_nested_wildcard():
    assert has_permission(["admin:*"], "admin:users") is True
    assert has_permission(["admin:*"], "admin:orgs") is True


def test_has_permission_no_match():
    assert has_permission(["tool:notes"], "tool:get_balance") is False
    assert has_permission(["memory:read"], "memory:write") is False


def test_has_permission_legacy_tool_execute():
    assert has_permission(["tool:execute"], "tool:anything") is True


# --- get_user_permissions ---

def test_default_user_permissions(mm):
    mm.ensure_user("u1")
    perms = get_user_permissions(mm.sqlite, "u1")
    assert "chat" in perms
    assert "memory:read" in perms
    assert "memory:write" in perms
    assert "tool:*" in perms
    assert "reasoning:run" in perms


def test_admin_user_permissions(mm):
    mm.ensure_user("admin1", role_id="admin")
    perms = get_user_permissions(mm.sqlite, "admin1")
    assert has_permission(perms, "chat") is True
    assert has_permission(perms, "tool:anything") is True
    assert has_permission(perms, "admin:users") is True


def test_custom_role_permissions(mm):
    mm.sqlite.create_role("limited", "Limited", ["chat", "tool:notes"])
    mm.ensure_user("u2", role_id="limited")
    perms = get_user_permissions(mm.sqlite, "u2")
    assert "chat" in perms
    assert has_permission(perms, "tool:notes") is True
    assert has_permission(perms, "tool:get_balance") is False


# --- ToolRouter RBAC ---

@pytest.mark.asyncio
async def test_tool_router_allows_with_wildcard(router, mm):
    mm.ensure_user("allowed_user")
    result = await router.execute("notes", {"action": "read", "user_id": "allowed_user"})
    assert "DENIED" not in result


@pytest.mark.asyncio
async def test_tool_router_denies_unauthorized_tool(router, mm):
    mm.sqlite.create_role("notes_only", "Notes Only", ["chat", "tool:notes"])
    mm.ensure_user("restricted_user", role_id="notes_only")
    result = await router.execute("get_balance", {"user_id": "restricted_user"})
    assert "DENIED" in result
    assert "get_balance" in result


@pytest.mark.asyncio
async def test_tool_router_legacy_execute_permission(router, mm):
    mm.sqlite.create_role("legacy", "Legacy", ["tool:execute"])
    mm.ensure_user("legacy_user", role_id="legacy")
    result = await router.execute("notes", {"action": "read", "user_id": "legacy_user"})
    assert "DENIED" not in result


# --- MemoryManager RBAC ---

def test_memory_manager_denies_write_without_permission(mm):
    mm.sqlite.create_role("reader", "Reader", ["chat", "memory:read"])
    mm.ensure_user("reader_user", role_id="reader")
    with pytest.raises(PermissionError):
        mm.store_fact("I like tea", user_id="reader_user")


def test_memory_manager_denies_read_without_permission(mm):
    mm.sqlite.create_role("writer", "Writer", ["chat", "memory:write"])
    mm.ensure_user("writer_user", role_id="writer")
    with pytest.raises(PermissionError):
        mm.retrieve("tea", user_id="writer_user")


def test_memory_manager_allows_default_user(mm):
    mm.ensure_user("normal_user")
    mm.store_fact("I like coffee", user_id="normal_user")
    facts = mm.retrieve("coffee", user_id="normal_user")
    assert "coffee" in facts.lower()


# --- ReActAgent RBAC ---

@pytest.mark.asyncio
async def test_agent_denies_without_reasoning_run(mm, monkeypatch):
    mm.sqlite.create_role("no_agent", "No Agent", ["chat", "memory:read", "memory:write", "tool:*"])
    mm.ensure_user("no_agent_user", role_id="no_agent")

    async def fake_generate(*, prompt, format_json=False):
        return "Final Answer: 42"

    monkeypatch.setattr("core.agent.generate_non_stream", fake_generate)
    agent = ReActAgent(memory=mm, tools=ToolRouter(sqlite_store=mm.sqlite))

    events = []
    async for e in agent.run(goal="test", session="s1", user_id="no_agent_user"):
        events.append(e)

    assert len(events) == 1
    assert events[0]["type"] == "error"
    assert "DENIED" in events[0]["content"]


@pytest.mark.asyncio
async def test_agent_allows_with_reasoning_run(mm, monkeypatch):
    mm.ensure_user("agent_user")

    async def fake_generate(*, prompt, format_json=False):
        return "Final Answer: 42"

    monkeypatch.setattr("core.agent.generate_non_stream", fake_generate)
    agent = ReActAgent(memory=mm, tools=ToolRouter(sqlite_store=mm.sqlite))

    events = []
    async for e in agent.run(goal="test", session="s1", user_id="agent_user"):
        events.append(e)

    assert any(e["type"] == "final" for e in events)


# --- Default role constants ---

def test_default_roles_include_expected_permissions():
    assert "*" in DEFAULT_ROLE_PERMISSIONS["admin"]
    assert "chat" in DEFAULT_ROLE_PERMISSIONS["user"]
    assert "tool:*" in DEFAULT_ROLE_PERMISSIONS["user"]
    assert "reasoning:run" in DEFAULT_ROLE_PERMISSIONS["user"]
    assert "audit:read" in DEFAULT_ROLE_PERMISSIONS["auditor"]
    assert "memory:org_read" in DEFAULT_ROLE_PERMISSIONS["auditor"]
