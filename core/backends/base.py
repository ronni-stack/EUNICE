# # EUNICE - Efficient Unified Neural Intelligence for Communication and Execution
# Copyright 2026 Ronny Koome
# Licensed under the Elastic License 2.0.
# See LICENSE for details.

"""EUNICE Enterprise — Inference backend abstraction.

This module defines the interface that all inference backends must implement.
Backends are responsible for talking to a concrete local LLM server
(Ollama, LocalAI, vLLM, llama.cpp, etc.) and returning responses in a
backend-agnostic format.
"""
from abc import ABC, abstractmethod
from typing import AsyncGenerator, Optional


class InferenceBackend(ABC):
    """Abstract inference backend for EUNICE."""

    name: str = "abstract"

    @abstractmethod
    async def stream_chat(
        self,
        messages: list,
        model: Optional[str] = None,
        tools: Optional[list] = None,
        temperature: float = 0.7,
        num_predict: int = 512,
        **kwargs
    ) -> AsyncGenerator[str, None]:
        """Stream a chat completion.

        Yields JSON strings of the form:
        - {"token": "...", "done": False}
        - {"done": True, "full": "..."}
        - {"error": "..."}
        - {"tool_call": True, "tool": "...", "params": {...}}
        """
        ...

    @abstractmethod
    async def generate(
        self,
        prompt: Optional[str] = None,
        messages: Optional[list] = None,
        model: Optional[str] = None,
        format_json: bool = False,
        temperature: float = 0.1,
        num_predict: int = 256,
        **kwargs
    ) -> str:
        """Non-streaming generation.

        Accepts either a raw prompt string or a messages list. Returns the
        generated text, or an empty string on failure.
        """
        ...

    @abstractmethod
    async def list_models(self) -> list[str]:
        """Return a list of model names available on this backend."""
        ...
