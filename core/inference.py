# # EUNICE - Efficient Unified Neural Intelligence for Communication and Execution
# Copyright 2026 Ronny Koome
# Licensed under the Elastic License 2.0.
# See LICENSE for details.

"""EUNICE Enterprise — Inference facade.

This module exposes the familiar `stream_chat` and `generate_non_stream`
functions used throughout EUNICE. Under the hood it routes through a
configurable backend (Ollama or LocalAI) and an optional model router.
"""
import json
import logging
from typing import AsyncGenerator, Optional

from config import (
    INFERENCE_BACKEND,
    OLLAMA_URL,
    LOCALAI_URL,
    LOCALAI_API_KEY,
    OLLAMA_TIMEOUT,
    MODEL_NAME,
    MODEL_POLICY,
    MODEL_TIER_MAP,
    APPROVED_MODELS,
)
from core.backends import OllamaBackend, LocalAIBackend
from core.model_router import ModelRouter

logger = logging.getLogger("eunice.inference")


def _create_backend():
    """Create the configured inference backend."""
    if INFERENCE_BACKEND.lower() == "localai":
        return LocalAIBackend(base_url=LOCALAI_URL, timeout=OLLAMA_TIMEOUT, api_key=LOCALAI_API_KEY)
    return OllamaBackend(base_url=OLLAMA_URL, timeout=OLLAMA_TIMEOUT)


def _create_router(backend=None):
    """Create the default model router for the configured backend."""
    backend = backend or _create_backend()
    return ModelRouter(
        backend=backend,
        default_model=MODEL_POLICY.get("default_model", MODEL_NAME),
        tier_map=MODEL_TIER_MAP,
        approved_models=APPROVED_MODELS if MODEL_POLICY.get("approved_models_only") else None,
        fallback_on_missing=MODEL_POLICY.get("fallback_on_missing", True),
    )


# Default backend and router instances. These are lazy-created at import time.
_default_backend = None
_default_router = None


def get_backend():
    """Return the default inference backend, creating it if necessary."""
    global _default_backend
    if _default_backend is None:
        _default_backend = _create_backend()
    return _default_backend


def get_router():
    """Return the default model router, creating it if necessary."""
    global _default_router
    if _default_router is None:
        _default_router = _create_router(get_backend())
    return _default_router


async def stream_chat(
    messages: list,
    tools: list = None,
    model: Optional[str] = None,
    task_tier: str = "chat",
) -> AsyncGenerator[str, None]:
    """Stream chat completion. Optionally selects model by task tier."""
    backend = get_backend()
    selected_model = model

    if selected_model is None and task_tier:
        try:
            selection = await get_router().select(task_tier)
            selected_model = selection.model
            if selection.fallback:
                logger.warning(f"[INFERENCE] {selection.note}")
        except Exception as e:
            logger.warning(f"[INFERENCE] model router failed: {e}; using default model")
            selected_model = MODEL_NAME

    logger.info(f"[INFERENCE] stream_chat backend={backend.name} model={selected_model} tier={task_tier}")
    async for event in backend.stream_chat(messages=messages, model=selected_model, tools=tools):
        yield event


async def generate_non_stream(
    messages: list = None,
    prompt: str = None,
    format_json: bool = False,
    model: Optional[str] = None,
    task_tier: str = "chat",
) -> str:
    """Non-streaming generation for background tasks and dynamic denials."""
    backend = get_backend()
    selected_model = model

    if selected_model is None and task_tier:
        try:
            selection = await get_router().select(task_tier)
            selected_model = selection.model
            if selection.fallback:
                logger.warning(f"[INFERENCE] {selection.note}")
        except Exception as e:
            logger.warning(f"[INFERENCE] model router failed: {e}; using default model")
            selected_model = MODEL_NAME

    logger.info(f"[INFERENCE] generate_non_stream backend={backend.name} model={selected_model} tier={task_tier}")
    return await backend.generate(
        prompt=prompt,
        messages=messages,
        model=selected_model,
        format_json=format_json,
    )
