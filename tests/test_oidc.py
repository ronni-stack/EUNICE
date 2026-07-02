# # EUNICE - Efficient Unified Neural Intelligence for Communication and Execution
# Copyright 2026 Ronny Koome
# Licensed under the Elastic License 2.0.
# See LICENSE for details.

"""EUNICE Enterprise — OIDC SSO tests."""
import json
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest
import memory.sqlite_store
import memory.vector_store
import core.audit
import config as config_module

from core.oidc import OIDCManager, OIDCError, OIDCProvider
from core.audit import AuditLogger
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
def oidc(mm):
    return OIDCManager(store=mm.sqlite)


@pytest.fixture
def client(tmp_path):
    memory.sqlite_store.DB_PATH = tmp_path / "test_oidc_client.db"
    return TestClient(app)


def _mock_oidc_http(mock_class, issuer, subject, email, groups, role="user"):
    """Configure an AsyncMock httpx client to respond like a minimal OIDC provider."""
    from unittest.mock import MagicMock

    def make_response(status_code, json_data=None, text=""):
        r = MagicMock()
        r.status_code = status_code
        r.json.return_value = json_data or {}
        r.text = text
        # raise_for_status is sync on httpx.Response
        r.raise_for_status.return_value = r
        return r

    async def get(url, **kwargs):
        if url.endswith("/.well-known/openid-configuration"):
            return make_response(200, {
                "authorization_endpoint": f"{issuer}/auth",
                "token_endpoint": f"{issuer}/token",
                "userinfo_endpoint": f"{issuer}/userinfo",
            })
        if url.endswith("/userinfo"):
            return make_response(200, {
                "sub": subject,
                "email": email,
                "name": email.split("@")[0],
                "groups": groups,
            })
        return make_response(404)

    async def post(url, **kwargs):
        if url.endswith("/token"):
            return make_response(200, {
                "access_token": "test-access-token",
                "token_type": "Bearer",
            })
        return make_response(404)

    mock_class.return_value.get = get
    mock_class.return_value.post = post


# --- Provider config & login URL ---

def test_list_providers_empty(oidc):
    assert oidc.list_providers("default") == []


def test_create_and_list_provider(oidc):
    oidc.create_provider(
        admin_user_id="admin", provider_id="okta", org_id="default", name="Okta",
        issuer="https://example.okta.com", client_id="cid", client_secret="secret",
        redirect_uri="http://localhost/callback",
    )
    providers = oidc.list_providers("default")
    assert len(providers) == 1
    assert providers[0]["id"] == "okta"
    assert "client_secret" not in providers[0]


def test_generate_login_url(oidc):
    oidc.create_provider(
        admin_user_id="admin", provider_id="okta", org_id="default", name="Okta",
        issuer="https://example.okta.com", client_id="cid", client_secret="secret",
        redirect_uri="http://localhost/callback",
    )
    result = oidc.generate_login_url("okta")
    assert "authorization_url" in result
    assert "state=" in result["authorization_url"]


# --- Callback & identity linking ---

@pytest.mark.asyncio
async def test_callback_creates_identity_and_link(oidc):
    oidc.create_provider(
        admin_user_id="admin", provider_id="okta", org_id="default", name="Okta",
        issuer="https://example.okta.com", client_id="cid", client_secret="secret",
        redirect_uri="http://localhost/callback",
        role_mapping={"legal": "legal"},
    )

    with patch("core.oidc.httpx.AsyncClient") as mock_class:
        _mock_oidc_http(mock_class, "https://example.okta.com", "sub-123",
                        "alice@example.com", ["legal"])

        login = oidc.generate_login_url("okta")
        result = await oidc.handle_callback("okta", "auth-code", login["state"])

    assert "token" in result
    assert result["display_name"] == "alice"
    identity_id = result["identity_id"]

    # Link created
    link = oidc.store.get_oidc_link("okta", "sub-123")
    assert link["identity_id"] == identity_id

    # User row has role from mapping (legal group maps to legal role which exists by default)
    user = oidc.store.get_user(identity_id)
    assert user["role_id"] == "legal"


@pytest.mark.asyncio
async def test_callback_returns_existing_identity_on_second_login(oidc):
    oidc.create_provider(
        admin_user_id="admin", provider_id="okta", org_id="default", name="Okta",
        issuer="https://example.okta.com", client_id="cid", client_secret="secret",
        redirect_uri="http://localhost/callback",
    )

    with patch("core.oidc.httpx.AsyncClient") as mock_class:
        _mock_oidc_http(mock_class, "https://example.okta.com", "sub-123",
                        "alice@example.com", ["user"])

        login = oidc.generate_login_url("okta")
        first = await oidc.handle_callback("okta", "auth-code", login["state"])

    with patch("core.oidc.httpx.AsyncClient") as mock_class:
        _mock_oidc_http(mock_class, "https://example.okta.com", "sub-123",
                        "alice@example.com", ["user"])

        login = oidc.generate_login_url("okta")
        second = await oidc.handle_callback("okta", "auth-code", login["state"])

    assert first["identity_id"] == second["identity_id"]


@pytest.mark.asyncio
async def test_role_mapping_falls_back_to_user(oidc):
    oidc.create_provider(
        admin_user_id="admin", provider_id="okta", org_id="default", name="Okta",
        issuer="https://example.okta.com", client_id="cid", client_secret="secret",
        redirect_uri="http://localhost/callback",
        role_mapping={"admins": "admin"},
    )

    with patch("core.oidc.httpx.AsyncClient") as mock_class:
        _mock_oidc_http(mock_class, "https://example.okta.com", "sub-999",
                        "bob@example.com", ["unknown_group"])

        login = oidc.generate_login_url("okta")
        result = await oidc.handle_callback("okta", "auth-code", login["state"])

    user = oidc.store.get_user(result["identity_id"])
    assert user["role_id"] == "user"


@pytest.mark.asyncio
async def test_invalid_state_rejected(oidc):
    oidc.create_provider(
        admin_user_id="admin", provider_id="okta", org_id="default", name="Okta",
        issuer="https://example.okta.com", client_id="cid", client_secret="secret",
        redirect_uri="http://localhost/callback",
    )
    with pytest.raises(OIDCError):
        await oidc.handle_callback("okta", "code", "invalid-state")


@pytest.mark.asyncio
async def test_expired_state_rejected(oidc):
    oidc.create_provider(
        admin_user_id="admin", provider_id="okta", org_id="default", name="Okta",
        issuer="https://example.okta.com", client_id="cid", client_secret="secret",
        redirect_uri="http://localhost/callback",
    )
    state = "expired-state"
    past = datetime.now(timezone.utc) - timedelta(seconds=10)
    oidc.store.create_oidc_state(state, "okta", "nonce", past.isoformat())
    with pytest.raises(OIDCError):
        await oidc.handle_callback("okta", "code", state)


# --- API endpoints ---

def test_oidc_providers_endpoint_lists_providers(client, audit_log):
    import api.server
    device = f"admin-{uuid.uuid4().hex[:8]}"
    provider_id = f"okta-{uuid.uuid4().hex[:8]}"
    headers = {"Authorization": "Bearer test-api-key", "X-EUNICE-Device-ID": device}

    r = client.post("/identity/create", headers={"Authorization": "Bearer test-api-key"}, json={
        "display_name": "Admin",
        "passphrase": "secret123",
        "device_id": device,
    })
    assert r.status_code == 200
    identity_id = r.json()["identity_id"]
    api.server.memory.ensure_user(identity_id)
    api.server.memory.sqlite.assign_user_role(identity_id, role_id="admin")

    r = client.post("/auth/oidc/providers", headers=headers, json={
        "provider_id": provider_id,
        "org_id": "default",
        "name": "Okta",
        "issuer": "https://example.okta.com",
        "client_id": "cid",
        "client_secret": "secret",
        "redirect_uri": "http://localhost/callback",
    })
    assert r.status_code == 200

    r = client.get("/auth/oidc/providers?org_id=default")
    assert r.status_code == 200
    data = r.json()
    assert any(p["id"] == provider_id for p in data["providers"])


def test_oidc_providers_endpoint_rejects_non_admin(client, audit_log):
    device = f"user-{uuid.uuid4().hex[:8]}"
    headers = {"Authorization": "Bearer test-api-key", "X-EUNICE-Device-ID": device}

    r = client.post("/identity/create", headers={"Authorization": "Bearer test-api-key"}, json={
        "display_name": "User",
        "passphrase": "secret123",
        "device_id": device,
    })
    assert r.status_code == 200

    r = client.post("/auth/oidc/providers", headers=headers, json={
        "provider_id": "okta",
        "org_id": "default",
        "name": "Okta",
        "issuer": "https://example.okta.com",
        "client_id": "cid",
        "client_secret": "secret",
        "redirect_uri": "http://localhost/callback",
    })
    assert r.status_code == 403


def test_oidc_login_endpoint_returns_url(client, audit_log):
    import api.server
    device = f"admin-{uuid.uuid4().hex[:8]}"
    provider_id = f"okta-{uuid.uuid4().hex[:8]}"
    headers = {"Authorization": "Bearer test-api-key", "X-EUNICE-Device-ID": device}

    r = client.post("/identity/create", headers={"Authorization": "Bearer test-api-key"}, json={
        "display_name": "Admin",
        "passphrase": "secret123",
        "device_id": device,
    })
    identity_id = r.json()["identity_id"]
    api.server.memory.ensure_user(identity_id)
    api.server.memory.sqlite.assign_user_role(identity_id, role_id="admin")

    r = client.post("/auth/oidc/providers", headers=headers, json={
        "provider_id": provider_id,
        "org_id": "default",
        "name": "Okta",
        "issuer": "https://example.okta.com",
        "client_id": "cid",
        "client_secret": "secret",
        "redirect_uri": "http://localhost/callback",
    })
    assert r.status_code == 200

    r = client.get(f"/auth/oidc/{provider_id}/login")
    assert r.status_code == 200
    assert "authorization_url" in r.json()


@pytest.mark.asyncio
async def test_oidc_callback_endpoint_issues_token(client, audit_log):
    import api.server
    device = f"admin-{uuid.uuid4().hex[:8]}"
    provider_id = f"okta-{uuid.uuid4().hex[:8]}"
    headers = {"Authorization": "Bearer test-api-key", "X-EUNICE-Device-ID": device}

    r = client.post("/identity/create", headers={"Authorization": "Bearer test-api-key"}, json={
        "display_name": "Admin",
        "passphrase": "secret123",
        "device_id": device,
    })
    identity_id = r.json()["identity_id"]
    api.server.memory.ensure_user(identity_id)
    api.server.memory.sqlite.assign_user_role(identity_id, role_id="admin")

    r = client.post("/auth/oidc/providers", headers=headers, json={
        "provider_id": provider_id,
        "org_id": "default",
        "name": "Okta",
        "issuer": "https://example.okta.com",
        "client_id": "cid",
        "client_secret": "secret",
        "redirect_uri": "http://localhost/callback",
    })
    assert r.status_code == 200

    # Patch the global OIDC manager's http client behavior via httpx patch
    with patch("core.oidc.httpx.AsyncClient") as mock_class:
        _mock_oidc_http(mock_class, "https://example.okta.com", "sub-api",
                        "carol@example.com", ["user"])

        r = client.get(f"/auth/oidc/{provider_id}/login")
        state = r.json()["state"]

        r = client.get(f"/auth/oidc/{provider_id}/callback?code=authcode&state={state}")
        assert r.status_code == 200
        data = r.json()
        assert "token" in data
        assert data["display_name"] == "carol"
