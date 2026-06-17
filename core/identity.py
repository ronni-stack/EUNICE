"""EUNICE v0.9 — Identity & Device Management

Manages identities, device linking, and session tokens.
An identity is a person; a device is a client instance.
The existing `users` table in SQLite acts as the identity record;
this module adds a `devices` table to map device fingerprints to identities.
"""
import uuid
import jwt
import bcrypt
from datetime import datetime, timedelta, timezone
from typing import Optional
from dataclasses import dataclass

from config import JWT_SECRET, JWT_ALGORITHM, JWT_EXPIRATION_HOURS
from memory.sqlite_store import SQLiteStore


@dataclass
class IdentityInfo:
    identity_id: str
    device_id: str
    display_name: str
    is_admin: bool


class IdentityManager:
    """Create, claim, and authenticate identities on devices."""

    def __init__(self, store: SQLiteStore = None):
        self.store = store or SQLiteStore()

    # --- Passphrase helpers ---

    def _hash_passphrase(self, passphrase: str) -> str:
        return bcrypt.hashpw(passphrase.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

    def _verify_passphrase(self, passphrase: str, hashed: str) -> bool:
        if not hashed:
            return False
        return bcrypt.checkpw(passphrase.encode("utf-8"), hashed.encode("utf-8"))

    # --- Identity lifecycle ---

    def create_identity(self, display_name: str, passphrase: str,
                        device_id: str, device_name: str = None,
                        device_type: str = None, is_admin: bool = False) -> IdentityInfo:
        """Create a new identity and link the first trusted device."""
        identity_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()

        self.store.create_identity(
            identity_id=identity_id,
            display_name=display_name,
            passphrase_hash=self._hash_passphrase(passphrase),
            is_admin=is_admin,
            created_at=now,
            updated_at=now,
        )
        self.store.create_device(
            device_id=device_id,
            identity_id=identity_id,
            name=device_name or device_id,
            device_type=device_type or "unknown",
            trusted=True,
            created_at=now,
            last_seen=now,
        )
        # Ensure the legacy users row exists so existing memory code works
        self.store.ensure_user(identity_id, name=display_name)
        return IdentityInfo(
            identity_id=identity_id,
            device_id=device_id,
            display_name=display_name,
            is_admin=is_admin,
        )

    def claim_identity(self, identity_id: str, passphrase: str,
                       device_id: str, device_name: str = None,
                       device_type: str = None) -> Optional[IdentityInfo]:
        """Link a new device to an existing identity."""
        identity = self.store.get_identity(identity_id)
        if not identity:
            return None
        if not self._verify_passphrase(passphrase, identity.get("passphrase_hash", "")):
            return None

        now = datetime.now(timezone.utc).isoformat()
        existing_device = self.store.get_device(device_id)
        if existing_device:
            # Re-linking an already-known device to the same identity is allowed
            if existing_device["identity_id"] != identity_id:
                return None
            self.store.update_device(device_id, last_seen=now)
        else:
            self.store.create_device(
                device_id=device_id,
                identity_id=identity_id,
                name=device_name or device_id,
                device_type=device_type or "unknown",
                trusted=True,
                created_at=now,
                last_seen=now,
            )

        return IdentityInfo(
            identity_id=identity_id,
            device_id=device_id,
            display_name=identity.get("display_name", ""),
            is_admin=bool(identity.get("is_admin", 0)),
        )

    def switch_device_identity(self, device_id: str, identity_id: str,
                               passphrase: str) -> Optional[IdentityInfo]:
        """Move an existing device to a different identity."""
        return self.claim_identity(
            identity_id=identity_id,
            passphrase=passphrase,
            device_id=device_id,
        )

    def get_identity_by_device(self, device_id: str) -> Optional[IdentityInfo]:
        """Resolve a device to its identity."""
        device = self.store.get_device(device_id)
        if not device:
            return None
        identity = self.store.get_identity(device["identity_id"])
        if not identity:
            return None
        return IdentityInfo(
            identity_id=identity["id"],
            device_id=device_id,
            display_name=identity.get("display_name", ""),
            is_admin=bool(identity.get("is_admin", 0)),
        )

    # --- Session tokens ---

    def create_session_token(self, identity_id: str, device_id: str) -> str:
        """Issue a signed JWT session token."""
        jti = str(uuid.uuid4())
        now = datetime.now(timezone.utc)
        expires = now + timedelta(hours=JWT_EXPIRATION_HOURS)

        self.store.create_token(
            jti=jti,
            identity_id=identity_id,
            device_id=device_id,
            expires_at=expires.isoformat(),
            created_at=now.isoformat(),
        )

        payload = {
            "sub": identity_id,
            "did": device_id,
            "jti": jti,
            "iat": now,
            "exp": expires,
        }
        return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)

    def verify_session_token(self, token: str) -> Optional[IdentityInfo]:
        """Verify a JWT and return identity info, or None if invalid/revoked."""
        try:
            payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        except jwt.PyJWTError:
            return None

        jti = payload.get("jti")
        identity_id = payload.get("sub")
        device_id = payload.get("did")

        if not jti or not identity_id or not device_id:
            return None

        if self.store.is_token_revoked(jti):
            return None

        identity = self.store.get_identity(identity_id)
        if not identity:
            return None

        return IdentityInfo(
            identity_id=identity_id,
            device_id=device_id,
            display_name=identity.get("display_name", ""),
            is_admin=bool(identity.get("is_admin", 0)),
        )

    def revoke_session_token(self, token: str) -> bool:
        """Revoke a session token by its JTI."""
        try:
            payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        except jwt.PyJWTError:
            return False
        jti = payload.get("jti")
        if not jti:
            return False
        self.store.revoke_token(jti)
        return True

    def list_devices(self, identity_id: str) -> list:
        return self.store.list_devices(identity_id)
