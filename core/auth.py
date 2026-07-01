# EUNICE - Efficient Unified Neural Intelligence for Communication and Execution
# Copyright 2026 Ronny Koome
# Licensed under the Elastic License 2.0. See LICENSE for details.

"""EUNICE v0.9 — Authentication + Identity Resolution

Supports two auth modes:
1. Static API key (household router password) + X-EUNICE-Device-ID header.
2. Signed session JWT issued by /identity/login.
"""
import secrets
from dataclasses import dataclass
from fastapi import HTTPException, Depends, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from config import API_KEY
from core.identity import IdentityManager, IdentityInfo
from core.audit import get_audit_logger

security = HTTPBearer(auto_error=False)
identity_manager = IdentityManager()
audit = get_audit_logger()


@dataclass
class AuthContext:
    identity_id: str
    device_id: str
    display_name: str
    is_admin: bool
    auth_method: str  # "api_key" | "jwt"


async def verify_token(credentials: HTTPAuthorizationCredentials = Depends(security)) -> str:
    """Validate static API key or session JWT."""
    if not credentials:
        audit.log_auth_event("token_validation", status="failure",
                             details={"reason": "missing_credentials"})
        raise HTTPException(status_code=401, detail="Missing API key or session token. Set it in Settings or log in.")
    token = credentials.credentials
    if token == API_KEY:
        return token
    if identity_manager.verify_session_token(token):
        return token
    audit.log_auth_event("token_validation", status="failure",
                         details={"reason": "invalid_token"})
    raise HTTPException(status_code=401, detail="Wrong API key or session token. Check Settings or log in again.")


def _resolve_device_id(request: Request) -> str:
    """Resolve device_id from header."""
    device_id = request.headers.get("X-EUNICE-Device-ID") or request.headers.get("X-EUNICE-User-ID")
    if device_id:
        return device_id.strip()
    return ""


def _client_ip(request: Request) -> str:
    return request.headers.get("X-Forwarded-For", request.client.host if request.client else "unknown")


async def get_auth_context(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> AuthContext:
    """Resolve identity and device from API key + device header or JWT."""
    ip = _client_ip(request)
    device_id = _resolve_device_id(request)

    if not credentials:
        audit.log_auth_event("auth", status="failure",
                             details={"reason": "missing_credentials"},
                             ip=ip, device_id=device_id)
        raise HTTPException(status_code=401, detail="Missing authorization. Set API key or log in.")

    token = credentials.credentials

    # 1. Try JWT session token first
    identity = identity_manager.verify_session_token(token)
    if identity:
        audit.log_auth_event("auth", user_id=identity.identity_id, status="success",
                             details={"method": "jwt"}, ip=ip, device_id=identity.device_id)
        return AuthContext(
            identity_id=identity.identity_id,
            device_id=identity.device_id,
            display_name=identity.display_name,
            is_admin=identity.is_admin,
            auth_method="jwt",
        )

    # 2. Fall back to static API key + device header
    if token == API_KEY:
        if not device_id:
            audit.log_auth_event("auth", status="failure",
                                 details={"reason": "missing_device_header", "method": "api_key"},
                                 ip=ip)
            raise HTTPException(status_code=401, detail="API key auth requires X-EUNICE-Device-ID header.")

        identity = identity_manager.get_identity_by_device(device_id)
        if identity:
            audit.log_auth_event("auth", user_id=identity.identity_id, status="success",
                                 details={"method": "api_key"}, ip=ip, device_id=device_id)
            return AuthContext(
                identity_id=identity.identity_id,
                device_id=device_id,
                display_name=identity.display_name,
                is_admin=identity.is_admin,
                auth_method="api_key",
            )

        # No identity yet for this device: create a local implicit identity
        # so existing clients keep working without a login flow.
        # The random passphrase prevents cross-device claiming; the device is
        # tied to API-key auth until the user explicitly creates a real identity.
        info = identity_manager.create_identity(
            display_name=device_id,
            passphrase=secrets.token_urlsafe(32),
            device_id=device_id,
            device_name=device_id,
        )
        audit.log_auth_event("auth", user_id=info.identity_id, status="success",
                             details={"method": "api_key", "auto_created_identity": True},
                             ip=ip, device_id=device_id)
        return AuthContext(
            identity_id=info.identity_id,
            device_id=device_id,
            display_name=info.display_name,
            is_admin=info.is_admin,
            auth_method="api_key",
        )

    audit.log_auth_event("auth", status="failure",
                         details={"reason": "invalid_token"}, ip=ip, device_id=device_id)
    raise HTTPException(status_code=401, detail="Invalid API key or session token.")


def get_current_user(request: Request) -> str:
    """Backward-compatible user_id resolver (returns identity_id)."""
    device_id = request.headers.get("X-EUNICE-Device-ID") or request.headers.get("X-EUNICE-User-ID")
    if device_id:
        identity = identity_manager.get_identity_by_device(device_id.strip())
        if identity:
            return identity.identity_id
    return "ronny"
