# # EUNICE - Efficient Unified Neural Intelligence for Communication and Execution
# Copyright 2026 Ronny Koome
# Licensed under the Elastic License 2.0.
# See LICENSE for details.

"""EUNICE Enterprise — Secrets management audit (Week 7)."""
import os
from typing import Any


def _env_set(name: str) -> bool:
    return bool(os.getenv(name, "").strip())


def _is_default(name: str, default: str) -> bool:
    return os.getenv(name, default) == default


def audit_secrets() -> dict[str, Any]:
    """Return a non-sensitive audit report of critical configuration."""
    recommendations = []

    master_key_configured = _env_set("EUNICE_MASTER_KEY")
    if not master_key_configured:
        recommendations.append("Set EUNICE_MASTER_KEY to enable encryption at rest.")

    api_key_is_default = _is_default("EUNICE_API_KEY", "eunice-local-dev-key-2026")
    if api_key_is_default:
        recommendations.append("Change the default EUNICE_API_KEY before production.")

    jwt_secret_from_env = _env_set("EUNICE_JWT_SECRET")
    if not jwt_secret_from_env:
        recommendations.append("Set EUNICE_JWT_SECRET so tokens are not signed with an auto-generated secret.")

    ollama_url = os.getenv("EUNICE_OLLAMA_URL", "default")
    if ollama_url == "default":
        recommendations.append("Review EUNICE_OLLAMA_URL to ensure it points to a trusted inference endpoint.")

    localai_key_is_default = _is_default("EUNICE_LOCALAI_API_KEY", "dummy")
    if localai_key_is_default:
        recommendations.append("Set a real EUNICE_LOCALAI_API_KEY if using the LocalAI backend.")

    return {
        "master_key_configured": master_key_configured,
        "api_key_is_default": api_key_is_default,
        "jwt_secret_from_env": jwt_secret_from_env,
        "ollama_url_source": "env" if ollama_url != "default" else "default",
        "localai_key_is_default": localai_key_is_default,
        "recommendations": recommendations,
    }
