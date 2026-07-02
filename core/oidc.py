# # EUNICE - Efficient Unified Neural Intelligence for Communication and Execution
# Copyright 2026 Ronny Koome
# Licensed under the Elastic License 2.0.
# See LICENSE for details.

"""EUNICE Enterprise — OpenID Connect (OIDC) SSO integration.

Implements a lightweight manual OIDC flow using httpx. Supports discovery,
authorization URL generation, code exchange, userinfo fetch, and identity
linking with claim-to-role mapping.
"""
import json
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional
from urllib.parse import urlencode

import httpx

from core.audit import get_audit_logger
from core.identity import IdentityManager
from memory.sqlite_store import SQLiteStore

DEFAULT_SCOPES = ["openid", "email", "profile"]
DEFAULT_CLAIM_MAPPINGS = {"email": "email", "name": "name", "groups": "groups"}
STATE_TTL_SECONDS = 300


class OIDCError(Exception):
    """Raised when an OIDC operation fails."""


class OIDCProvider:
    """Wraps a single OIDC provider configuration and protocol flow."""

    def __init__(self, config: Dict[str, Any], http_client: httpx.AsyncClient = None):
        self.config = config
        self._client = http_client
        self._discovery: Optional[Dict[str, Any]] = None

    def _http(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=30.0, follow_redirects=True)
        return self._client

    async def discover(self) -> Dict[str, Any]:
        """Fetch and cache OpenID provider discovery document."""
        if self._discovery:
            return self._discovery
        issuer = self.config["issuer"].rstrip("/")
        url = f"{issuer}/.well-known/openid-configuration"
        try:
            resp = await self._http().get(url)
            resp.raise_for_status()
            self._discovery = resp.json()
            return self._discovery
        except Exception as exc:
            raise OIDCError(f"OIDC discovery failed for {issuer}: {exc}") from exc

    def build_authorization_url(self, state: str, nonce: str, redirect_uri: str) -> str:
        """Build the authorization URL for the login redirect."""
        # Use discovery endpoint if available; fall back to issuer-derived URL
        issuer = self.config["issuer"].rstrip("/")
        auth_endpoint = self._discovery.get("authorization_endpoint") if self._discovery else None
        auth_endpoint = auth_endpoint or f"{issuer}/oauth2/authorize"

        scopes = self.config.get("scopes", DEFAULT_SCOPES)
        params = {
            "client_id": self.config["client_id"],
            "response_type": "code",
            "scope": " ".join(scopes),
            "redirect_uri": redirect_uri or self.config["redirect_uri"],
            "state": state,
            "nonce": nonce,
        }
        return f"{auth_endpoint}?{urlencode(params)}"

    async def exchange_code(self, code: str, redirect_uri: str) -> Dict[str, Any]:
        """Exchange an authorization code for tokens."""
        discovery = await self.discover()
        token_endpoint = discovery.get("token_endpoint")
        if not token_endpoint:
            raise OIDCError("OIDC discovery did not return a token_endpoint")

        data = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri or self.config["redirect_uri"],
            "client_id": self.config["client_id"],
            "client_secret": self.config["client_secret"],
        }
        try:
            resp = await self._http().post(token_endpoint, data=data)
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:
            raise OIDCError(f"OIDC token exchange failed: {exc}") from exc

    async def fetch_userinfo(self, access_token: str) -> Dict[str, Any]:
        """Fetch user information from the OIDC userinfo endpoint."""
        discovery = await self.discover()
        userinfo_endpoint = discovery.get("userinfo_endpoint")
        if not userinfo_endpoint:
            raise OIDCError("OIDC discovery did not return a userinfo_endpoint")

        try:
            resp = await self._http().get(
                userinfo_endpoint,
                headers={"Authorization": f"Bearer {access_token}"}
            )
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:
            raise OIDCError(f"OIDC userinfo fetch failed: {exc}") from exc


class OIDCManager:
    """High-level OIDC manager: providers, linking, role mapping, tokens."""

    def __init__(self, store: SQLiteStore = None, identity_manager: IdentityManager = None,
                 audit=None):
        self.store = store or SQLiteStore()
        self.identity_manager = identity_manager or IdentityManager(self.store)
        self.audit = audit or get_audit_logger()

    def list_providers(self, org_id: str = None) -> list:
        """Return enabled OIDC providers, optionally filtered by org."""
        providers = self.store.list_oidc_providers(org_id)
        # Don't leak client_secret
        for p in providers:
            p.pop("client_secret", None)
            try:
                p["scopes"] = json.loads(p["scopes"])
                p["claim_mappings"] = json.loads(p["claim_mappings"])
                p["role_mapping"] = json.loads(p["role_mapping"])
            except (json.JSONDecodeError, KeyError):
                pass
        return providers

    def get_provider(self, provider_id: str) -> Optional[OIDCProvider]:
        config = self.store.get_oidc_provider(provider_id)
        if not config:
            return None
        try:
            config["scopes"] = json.loads(config["scopes"])
            config["claim_mappings"] = json.loads(config["claim_mappings"])
            config["role_mapping"] = json.loads(config["role_mapping"])
        except (json.JSONDecodeError, KeyError):
            pass
        return OIDCProvider(config)

    def create_provider(self, admin_user_id: str, provider_id: str, org_id: str, name: str,
                        issuer: str, client_id: str, client_secret: str, redirect_uri: str,
                        scopes: list = None, claim_mappings: dict = None,
                        role_mapping: dict = None, enabled: bool = True):
        """Create a new OIDC provider configuration."""
        self.store.create_oidc_provider(
            provider_id=provider_id,
            org_id=org_id,
            name=name,
            issuer=issuer,
            client_id=client_id,
            client_secret=client_secret,
            redirect_uri=redirect_uri,
            scopes=scopes,
            claim_mappings=claim_mappings,
            role_mapping=role_mapping,
            enabled=enabled,
        )
        self.audit.log_auth_event(
            "oidc_provider_created",
            user_id=admin_user_id,
            org_id=org_id,
            details={"provider_id": provider_id, "issuer": issuer},
            status="success",
        )

    def delete_provider(self, admin_user_id: str, provider_id: str):
        """Disable (soft-delete) an OIDC provider."""
        provider = self.store.get_oidc_provider(provider_id)
        org_id = provider.get("org_id") if provider else None
        self.store.delete_oidc_provider(provider_id)
        self.audit.log_auth_event(
            "oidc_provider_deleted",
            user_id=admin_user_id,
            org_id=org_id,
            details={"provider_id": provider_id},
            status="success",
        )

    def generate_login_url(self, provider_id: str, redirect_uri: str = None) -> Dict[str, str]:
        """Generate a state + nonce and return the OIDC authorization URL."""
        provider = self.get_provider(provider_id)
        if not provider:
            raise OIDCError("Unknown or disabled OIDC provider")

        state = secrets.token_urlsafe(32)
        nonce = secrets.token_urlsafe(32)
        expires = datetime.now(timezone.utc) + timedelta(seconds=STATE_TTL_SECONDS)
        self.store.create_oidc_state(state, provider_id, nonce, expires.isoformat())

        url = provider.build_authorization_url(state, nonce, redirect_uri)
        return {"authorization_url": url, "state": state}

    async def handle_callback(self, provider_id: str, code: str, state: str,
                              redirect_uri: str = None) -> Dict[str, Any]:
        """Handle OIDC callback: validate state, exchange code, link identity, issue token."""
        # Validate state
        state_record = self.store.get_oidc_state(state)
        if not state_record:
            self.audit.log_auth_event("oidc_callback", status="failure",
                                      details={"reason": "invalid_state", "provider_id": provider_id})
            raise OIDCError("Invalid or expired state parameter")

        if datetime.fromisoformat(state_record["expires_at"]) < datetime.now(timezone.utc):
            self.store.delete_oidc_state(state)
            self.audit.log_auth_event("oidc_callback", status="failure",
                                      details={"reason": "expired_state", "provider_id": provider_id})
            raise OIDCError("Expired state parameter")

        if state_record["provider_id"] != provider_id:
            self.audit.log_auth_event("oidc_callback", status="failure",
                                      details={"reason": "provider_mismatch", "provider_id": provider_id})
            raise OIDCError("State/provider mismatch")

        # One-time use
        self.store.delete_oidc_state(state)

        provider = self.get_provider(provider_id)
        if not provider:
            raise OIDCError("Unknown or disabled OIDC provider")

        tokens = await provider.exchange_code(code, redirect_uri)
        access_token = tokens.get("access_token", "")
        if not access_token:
            raise OIDCError("OIDC token response did not include access_token")

        userinfo = await provider.fetch_userinfo(access_token)
        return await self._resolve_identity(provider_id, provider.config, userinfo)

    async def _resolve_identity(self, provider_id: str, config: Dict[str, Any],
                                claims: Dict[str, Any]) -> Dict[str, Any]:
        """Map OIDC claims to an EUNICE identity, creating/linking as needed."""
        mappings = config.get("claim_mappings", DEFAULT_CLAIM_MAPPINGS)
        subject = claims.get("sub")
        if not subject:
            raise OIDCError("OIDC userinfo missing 'sub' claim")

        email = claims.get(mappings.get("email", "email"), "")
        display_name = claims.get(mappings.get("name", "name"), email or subject)
        groups = claims.get(mappings.get("groups", "groups"), [])
        if isinstance(groups, str):
            groups = [groups]

        # Existing link?
        link = self.store.get_oidc_link(provider_id, subject)
        if link:
            identity = self.store.get_identity(link["identity_id"])
            if identity:
                self.audit.log_auth_event(
                    "oidc_login", user_id=identity["id"], status="success",
                    details={"provider_id": provider_id, "linked": True}
                )
                return self._issue_session(identity)

        # New OIDC user: create identity
        identity_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        role_id = self._resolve_role(config.get("role_mapping", {}), groups)

        self.store.create_identity(
            identity_id=identity_id,
            display_name=display_name,
            email=email,
            passphrase_hash="",  # OIDC users don't have local passwords
            is_admin=(role_id == "admin"),
            created_at=now,
            updated_at=now,
        )
        # Create a pseudo-device for the SSO session
        device_id = f"oidc:{provider_id}:{subject}"
        self.store.create_device(
            device_id=device_id,
            identity_id=identity_id,
            name="OIDC Session",
            device_type="oidc",
            trusted=True,
            created_at=now,
            last_seen=now,
        )
        self.store.ensure_user(identity_id, name=display_name, org_id=config.get("org_id"),
                               role_id=role_id)
        self.store.create_oidc_link(provider_id, subject, identity_id)

        self.audit.log_auth_event(
            "oidc_login", user_id=identity_id, status="success",
            details={"provider_id": provider_id, "linked": False, "role_id": role_id}
        )
        return self._issue_session(self.store.get_identity(identity_id))

    def _resolve_role(self, role_mapping: Dict[str, str], groups: list) -> str:
        """Map OIDC groups/roles to EUNICE role IDs."""
        for group in groups or []:
            if group in role_mapping:
                role_id = role_mapping[group]
                # Validate role exists
                if self.store.get_role_permissions(role_id):
                    return role_id
        return "user"

    def _issue_session(self, identity: Dict[str, Any]) -> Dict[str, Any]:
        """Issue a EUNICE session token for the resolved identity."""
        identity_id = identity["id"]
        device_id = f"oidc:{identity_id}"
        token = self.identity_manager.create_session_token(identity_id, device_id)
        return {
            "token": token,
            "identity_id": identity_id,
            "display_name": identity.get("display_name", ""),
            "is_admin": bool(identity.get("is_admin", 0)),
        }
