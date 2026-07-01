# # EUNICE - Efficient Unified Neural Intelligence for Communication and Execution
# Copyright 2026 Ronny Koome
# Licensed under the Elastic License 2.0.
# See LICENSE for details.

"""EUNICE Enterprise — Multi-tenancy tests."""
import pytest
import memory.sqlite_store
import memory.vector_store
from memory.manager import MemoryManager


@pytest.fixture
def mm(tmp_path):
    db_path = tmp_path / "test.db"
    chroma_path = tmp_path / "chroma"
    memory.sqlite_store.DB_PATH = db_path
    memory.vector_store.CHROMA_PATH = chroma_path
    return MemoryManager()


def test_default_org_created_on_user_ensure(mm):
    mm.ensure_user("u1")
    user = mm.get_user("u1")
    assert user["org_id"] == "default"
    assert user["department_id"] == "default"
    assert user["role_id"] == "user"


def test_org_isolation_for_facts(mm):
    mm.ensure_user("u1", org_id="org_a")
    mm.ensure_user("u2", org_id="org_b")

    mm.sqlite.save_fact("name", "Alice", user_id="u1", org_id="org_a")
    mm.sqlite.save_fact("name", "Bob", user_id="u2", org_id="org_b")

    u1_facts = mm.sqlite.get_facts(user_id="u1", org_id="org_a")
    u2_facts = mm.sqlite.get_facts(user_id="u2", org_id="org_b")

    assert u1_facts.get("name") == "Alice"
    assert u2_facts.get("name") == "Bob"


def test_org_isolation_for_messages(mm):
    mm.ensure_user("u1", org_id="org_a")
    mm.ensure_user("u2", org_id="org_b")

    mm.sqlite.save_message("user", "hello from a", session="s1", user_id="u1", org_id="org_a")
    mm.sqlite.save_message("user", "hello from b", session="s1", user_id="u2", org_id="org_b")

    a_history = mm.sqlite.get_recent(session="s1", user_id="u1", org_id="org_a")
    b_history = mm.sqlite.get_recent(session="s1", user_id="u2", org_id="org_b")

    assert len(a_history) == 1
    assert len(b_history) == 1
    assert "from a" in a_history[0]["content"]
    assert "from b" in b_history[0]["content"]


def test_role_permissions(mm):
    mm.sqlite.create_role("test_legal", "Test Legal", ["memory:read", "legal:review"])
    perms = mm.sqlite.get_role_permissions("test_legal")
    assert "memory:read" in perms
    assert "legal:review" in perms


def test_assign_user_role(mm):
    mm.ensure_user("u1")
    mm.sqlite.create_role("admin", "Admin", ["*"])
    mm.sqlite.assign_user_role("u1", role_id="admin")
    user = mm.sqlite.get_user("u1")
    assert user["role_id"] == "admin"
