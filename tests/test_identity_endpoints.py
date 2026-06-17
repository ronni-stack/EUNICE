"""EUNICE v0.9 — Identity Endpoint Tests

Note: these tests use unique device IDs to avoid collisions because the app
singleton stores point to the real DB path.
"""
import uuid
import pytest
import memory.sqlite_store
import config as config_module

config_module.JWT_SECRET = "test-secret-32-bytes-long-1234567890"
config_module.API_KEY = "test-api-key"

from fastapi.testclient import TestClient
from api.server import app


@pytest.fixture
def client(tmp_path):
    # Patch is best-effort; app singletons were already created with real DB path.
    # Device UUIDs keep tests isolated from each other.
    memory.sqlite_store.DB_PATH = tmp_path / "test_identity_endpoints.db"
    return TestClient(app)


def _unique(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


def test_create_and_me(client):
    device = _unique("dev-phone")
    r = client.post("/identity/create", headers={"Authorization": "Bearer test-api-key"}, json={
        "display_name": "Alex",
        "passphrase": "secret123",
        "device_id": device,
        "device_name": "Phone",
    })
    assert r.status_code == 200
    data = r.json()
    token = data["token"]

    r = client.get("/identity/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    me = r.json()
    assert me["display_name"] == "Alex"
    assert me["auth_method"] == "jwt"


def test_claim_device(client):
    device1 = _unique("dev-phone")
    device2 = _unique("dev-laptop")
    r = client.post("/identity/create", headers={"Authorization": "Bearer test-api-key"}, json={
        "display_name": "Alex",
        "passphrase": "secret123",
        "device_id": device1,
    })
    identity_id = r.json()["identity_id"]

    r = client.post("/identity/claim", headers={"Authorization": "Bearer test-api-key"}, json={
        "identity_id": identity_id,
        "passphrase": "secret123",
        "device_id": device2,
        "device_name": "Laptop",
    })
    assert r.status_code == 200
    data = r.json()
    assert data["device_id"] == device2


def test_chat_with_session_token(client):
    device = _unique("dev-phone")
    r = client.post("/identity/create", headers={"Authorization": "Bearer test-api-key"}, json={
        "display_name": "Alex",
        "passphrase": "secret123",
        "device_id": device,
    })
    token = r.json()["token"]

    r = client.post("/chat/stream", headers={"Authorization": f"Bearer {token}"}, json={
        "message": "what is my name",
        "session": "test",
    })
    assert r.status_code == 200
    assert "Alex" in r.text


def test_logout_revokes_token(client):
    device = _unique("dev-phone")
    r = client.post("/identity/create", headers={"Authorization": "Bearer test-api-key"}, json={
        "display_name": "Alex",
        "passphrase": "secret123",
        "device_id": device,
    })
    token = r.json()["token"]

    r = client.post("/identity/logout", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200

    r = client.get("/identity/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 401
