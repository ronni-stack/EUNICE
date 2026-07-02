# # EUNICE - Efficient Unified Neural Intelligence for Communication and Execution
# Copyright 2026 Ronny Koome
# Licensed under the Elastic License 2.0.
# See LICENSE for details.

"""EUNICE Enterprise — Admin dashboard tests (Week 9)."""
import uuid

import pytest
from fastapi.testclient import TestClient

import config as config_module
import memory.sqlite_store

config_module.API_KEY = "test-api-key"
config_module.JWT_SECRET = "test-secret-32-bytes-long-1234567890"


def _unique(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


@pytest.fixture
def client(tmp_path):
    memory.sqlite_store.DB_PATH = tmp_path / "test_admin_dashboard_client.db"
    from api.server import app
    return TestClient(app)


@pytest.fixture
def admin_headers(client):
    device = _unique("dev")
    headers = {"Authorization": "Bearer test-api-key", "X-EUNICE-Device-ID": device}
    r = client.post("/identity/create", headers={"Authorization": "Bearer test-api-key"}, json={
        "display_name": "Admin",
        "passphrase": "secret123",
        "device_id": device,
    })
    assert r.status_code == 200, r.text
    identity_id = r.json()["identity_id"]
    import api.server
    mm = api.server.memory
    mm.ensure_user(identity_id)
    mm.sqlite.assign_user_role(identity_id, role_id="admin")
    return headers


def test_admin_orgs_crud(client, admin_headers):
    r = client.get("/admin/orgs", headers=admin_headers)
    assert r.status_code == 200
    orgs = r.json()["organizations"]
    assert any(o["id"] == "default" for o in orgs)

    r = client.post("/admin/orgs", headers=admin_headers, json={"org_id": "acme", "name": "Acme Corp"})
    assert r.status_code == 200

    r = client.get("/admin/orgs", headers=admin_headers)
    assert any(o["id"] == "acme" for o in r.json()["organizations"])


def test_admin_departments_crud(client, admin_headers):
    client.post("/admin/orgs", headers=admin_headers, json={"org_id": "globex", "name": "Globex"})
    r = client.post("/admin/orgs/globex/departments", headers=admin_headers, json={
        "dept_id": "engineering", "name": "Engineering"
    })
    assert r.status_code == 200

    r = client.get("/admin/orgs/globex/departments", headers=admin_headers)
    assert r.status_code == 200
    assert any(d["id"] == "engineering" for d in r.json()["departments"])


def test_admin_users_crud(client, admin_headers):
    client.post("/admin/orgs", headers=admin_headers, json={"org_id": "initech", "name": "Initech"})
    r = client.post("/admin/users", headers=admin_headers, json={
        "user_id": "alice",
        "name": "Alice",
        "org_id": "initech",
        "department_id": "engineering",
        "role_id": "user",
    })
    assert r.status_code == 200
    assert r.json()["role_id"] == "user"

    r = client.get("/admin/users?org_id=initech", headers=admin_headers)
    assert any(u["id"] == "alice" for u in r.json()["users"])

    r = client.patch("/admin/users/alice", headers=admin_headers, json={"role_id": "auditor"})
    assert r.status_code == 200
    assert r.json()["role_id"] == "auditor"


def test_tool_approval_toggle(client, admin_headers):
    import api.server
    mm = api.server.memory
    org_id = _unique("tools-org")
    mm.sqlite.create_organization(org_id, "Tools Org")

    r = client.get(f"/admin/tools/approvals?org_id={org_id}", headers=admin_headers)
    assert r.status_code == 200
    notes = next(t for t in r.json()["tools"] if t["tool_name"] == "notes")
    assert notes["approved"] is True

    r = client.post("/admin/tools/approvals", headers=admin_headers, json={
        "org_id": org_id, "tool_name": "notes", "approved": False
    })
    assert r.status_code == 200

    r = client.get(f"/admin/tools/approvals?org_id={org_id}", headers=admin_headers)
    notes = next(t for t in r.json()["tools"] if t["tool_name"] == "notes")
    assert notes["approved"] is False


@pytest.mark.asyncio
async def test_tool_approval_enforced_in_router(client, admin_headers):
    import api.server
    mm = api.server.memory
    org_id = _unique("block-org")
    mm.sqlite.create_organization(org_id, "Block Org")
    mm.sqlite.create_department("dept", org_id, "Dept")
    user_id = _unique("blocked-user")
    mm.sqlite.ensure_user(user_id, org_id=org_id, department_id="dept", role_id="user")
    mm.sqlite.set_tool_approval(org_id, "notes", False)

    router = api.server.tools
    result = await router.execute("notes", {"user_id": user_id, "action": "read"})
    assert "DENIED" in result
    assert "not approved" in result


def test_models_status_endpoint(client, admin_headers):
    r = client.get("/admin/models/status", headers=admin_headers)
    assert r.status_code == 200
    data = r.json()
    assert "active_model" in data
    assert "models" in data
    assert any(m["name"] == data["active_model"] for m in data["models"])


def test_audit_org_filter(client, admin_headers):
    import api.server
    mm = api.server.memory
    org_id = _unique("audit-org")
    mm.sqlite.create_organization(org_id, "Audit Org")
    audit = api.server.audit_logger
    audit.log_memory_access("read", "u1", org_id, "resource")
    audit.log_memory_access("read", "u2", "default", "resource")

    r = client.get(f"/audit?org_id={org_id}", headers=admin_headers)
    assert r.status_code == 200
    entries = r.json()["entries"]
    assert all(e.get("org_id") == org_id for e in entries)
