# # EUNICE - Efficient Unified Neural Intelligence for Communication and Execution
# Copyright 2026 Ronny Koome
# Licensed under the Elastic License 2.0.
# See LICENSE for details.

"""EUNICE Enterprise — Role-Based Access Control (RBAC) engine.

Permission format:
- "*"                     grants every permission.
- "chat"                  grants the chat capability.
- "memory:read"           grants reading own memory.
- "memory:write"          grants writing own memory.
- "memory:org_read"       grants reading organization-wide memory.
- "tool:*"                grants all subprocess tools.
- "tool:notes"            grants only the notes tool.
- "reasoning:run"         grants the ReAct agent.
- "documents:read"        grants reading uploaded documents.
- "documents:write"       grants uploading documents.
- "admin:*"               grants all admin operations.
- "audit:read"            grants audit log access.

Wildcards match a colon-separated prefix: "tool:*" satisfies "tool:notes".
"""
from typing import Iterable, List


DEFAULT_ROLE_PERMISSIONS = {
    "admin": ["*"],
    "user": [
        "chat",
        "memory:read",
        "memory:write",
        "tool:*",
        "reasoning:run",
        "documents:read",
        "documents:write",
    ],
    "auditor": ["audit:read", "memory:org_read"],
    "legal": [
        "chat",
        "memory:read",
        "memory:write",
        "tool:notes",
        "tool:legal:review",
        "reasoning:run",
        "documents:read",
    ],
}


def has_permission(permissions: Iterable[str], required: str) -> bool:
    """Return True if `required` is satisfied by any permission in `permissions`.

    Supports exact matches, the global wildcard "*", and prefix wildcards such
    as "tool:*" matching "tool:notes".
    """
    if not required:
        return True

    perms = set(permissions or [])
    if "*" in perms:
        return True
    if required in perms:
        return True

    # Legacy support: "tool:execute" granted all tools
    if required.startswith("tool:") and "tool:execute" in perms:
        return True

    # Support wildcard prefix segments, e.g. tool:* -> tool:notes
    if ":" in required:
        segments = required.split(":")
        for i in range(1, len(segments)):
            wildcard = ":".join(segments[:i]) + ":*"
            if wildcard in perms:
                return True
    return False


def get_user_permissions(sqlite_store, user_id: str) -> List[str]:
    """Resolve a user's effective permissions from their assigned role."""
    user = sqlite_store.get_user(user_id)
    role_id = user.get("role_id") if user else None

    if role_id:
        stored = sqlite_store.get_role_permissions(role_id)
        if stored:
            return list(stored)

    return list(DEFAULT_ROLE_PERMISSIONS.get("user", []))


def require_permission(sqlite_store, user_id: str, required: str):
    """Raise PermissionError if the user lacks the required permission."""
    perms = get_user_permissions(sqlite_store, user_id)
    if not has_permission(perms, required):
        raise PermissionError(
            f"Access denied: user '{user_id}' lacks permission '{required}'."
        )
