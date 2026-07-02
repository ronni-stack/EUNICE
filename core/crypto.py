# # EUNICE - Efficient Unified Neural Intelligence for Communication and Execution
# Copyright 2026 Ronny Koome
# Licensed under the Elastic License 2.0.
# See LICENSE for details.

"""EUNICE Enterprise — Org-level field encryption at rest.

Uses AES-256-GCM via the cryptography library. Each org has a unique salt;
the actual encryption key is derived from the EUNICE_MASTER_KEY env var and
that salt with PBKDF2-HMAC-SHA256.

If EUNICE_MASTER_KEY is not configured, encryption is disabled and data is
stored in plaintext for backwards compatibility.
"""
import base64
import os
from typing import Optional

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes

ENCRYPTION_PREFIX = "$eunice$"
SALT_BYTES = 16
NONCE_BYTES = 12
ITERATIONS = 100_000
KEY_LEN = 32


def derive_org_key(master_key: str, org_id: str, salt: bytes) -> bytes:
    """Derive a 32-byte AES key for an org from the master key and salt."""
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=KEY_LEN,
        salt=salt + org_id.encode("utf-8"),
        iterations=ITERATIONS,
    )
    return kdf.derive(master_key.encode("utf-8"))


def _encode(payload: bytes, nonce: bytes, salt: bytes) -> str:
    combined = salt + nonce + payload
    return f"{ENCRYPTION_PREFIX}{base64.urlsafe_b64encode(combined).decode('ascii')}"


def _decode(ciphertext: str) -> tuple:
    raw = base64.urlsafe_b64decode(ciphertext[len(ENCRYPTION_PREFIX):].encode("ascii"))
    salt = raw[:SALT_BYTES]
    nonce = raw[SALT_BYTES:SALT_BYTES + NONCE_BYTES]
    payload = raw[SALT_BYTES + NONCE_BYTES:]
    return salt, nonce, payload


def encrypt(plaintext: str, key: bytes) -> str:
    """Encrypt plaintext with AES-256-GCM and return a marked base64 string."""
    if plaintext is None:
        return None
    if plaintext == "":
        return ""
    if is_encrypted(plaintext):
        return plaintext
    nonce = os.urandom(NONCE_BYTES)
    salt = os.urandom(SALT_BYTES)
    # Use a per-value random salt and key derived from the org key
    # Actually we already have the org key; we use it directly. Include random
    # salt in ciphertext for future key rotation / separation.
    aesgcm = AESGCM(key)
    ciphertext = aesgcm.encrypt(nonce, plaintext.encode("utf-8"), None)
    return _encode(ciphertext, nonce, salt)


def decrypt(ciphertext: str, key: bytes) -> str:
    """Decrypt a marked ciphertext string. Pass-through plaintext values."""
    if ciphertext is None:
        return None
    if ciphertext == "":
        return ""
    if not is_encrypted(ciphertext):
        return ciphertext
    _, nonce, payload = _decode(ciphertext)
    aesgcm = AESGCM(key)
    return aesgcm.decrypt(nonce, payload, None).decode("utf-8")


def is_encrypted(value: str) -> bool:
    """Return True if the value appears to be an EUNICE-encrypted payload."""
    return isinstance(value, str) and value.startswith(ENCRYPTION_PREFIX)


def encrypt_optional(plaintext: str, key: Optional[bytes]) -> str:
    """Encrypt if a key is provided, otherwise return plaintext unchanged."""
    if key is None:
        return plaintext
    return encrypt(plaintext, key)


def decrypt_optional(ciphertext: str, key: Optional[bytes]) -> str:
    """Decrypt if a key is provided, otherwise return the value unchanged."""
    if key is None:
        return ciphertext
    return decrypt(ciphertext, key)
