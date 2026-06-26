# # EUNICE - Efficient Unified Neural Intelligence for Communication and Execution
# Copyright 2026 Ronny Koome
# Licensed under the Elastic License 2.0.
# See LICENSE for details.

"""EUNICE v0.9 — Identity & Access Tests"""
import pytest
import memory.sqlite_store
import config as config_module
from core.identity import IdentityManager

config_module.JWT_SECRET = "test-secret-32-bytes-long-1234567890"


@pytest.fixture
def im(tmp_path):
    db_path = tmp_path / "test_identity.db"
    memory.sqlite_store.DB_PATH = db_path
    manager = IdentityManager()
    return manager


def test_create_identity(im):
    info = im.create_identity(
        display_name="Alex",
        passphrase="secret123",
        device_id="dev-alex-phone",
        device_name="Alex's Phone",
    )
    assert info.identity_id
    assert info.device_id == "dev-alex-phone"
    assert info.display_name == "Alex"
    assert not info.is_admin

    identity = im.store.get_identity(info.identity_id)
    assert identity["display_name"] == "Alex"
    assert identity["passphrase_hash"]

    device = im.store.get_device("dev-alex-phone")
    assert device["identity_id"] == info.identity_id
    assert device["name"] == "Alex's Phone"


def test_claim_identity(im):
    creator = im.create_identity(
        display_name="Alex",
        passphrase="secret123",
        device_id="dev-alex-phone",
        device_name="Alex's Phone",
    )

    # Simulate a second device claiming the same identity
    claimed = im.claim_identity(
        identity_id=creator.identity_id,
        passphrase="secret123",
        device_id="dev-alex-laptop",
        device_name="Alex's Laptop",
    )
    assert claimed.identity_id == creator.identity_id
    assert claimed.device_id == "dev-alex-laptop"

    devices = im.list_devices(creator.identity_id)
    assert len(devices) == 2


def test_claim_identity_wrong_passphrase(im):
    creator = im.create_identity(
        display_name="Alex",
        passphrase="secret123",
        device_id="dev-alex-phone",
    )
    result = im.claim_identity(
        identity_id=creator.identity_id,
        passphrase="wrong",
        device_id="dev-alex-laptop",
    )
    assert result is None


def test_session_token_round_trip(im):
    info = im.create_identity(
        display_name="Alex",
        passphrase="secret123",
        device_id="dev-alex-phone",
    )
    token = im.create_session_token(info.identity_id, info.device_id)
    assert token

    verified = im.verify_session_token(token)
    assert verified.identity_id == info.identity_id
    assert verified.device_id == info.device_id


def test_revoked_token_fails(im):
    info = im.create_identity(
        display_name="Alex",
        passphrase="secret123",
        device_id="dev-alex-phone",
    )
    token = im.create_session_token(info.identity_id, info.device_id)
    im.revoke_session_token(token)
    assert im.verify_session_token(token) is None


def test_invalid_token_fails(im):
    assert im.verify_session_token("not.a.token") is None
