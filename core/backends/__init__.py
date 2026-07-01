# # EUNICE - Efficient Unified Neural Intelligence for Communication and Execution
# Copyright 2026 Ronny Koome
# Licensed under the Elastic License 2.0.
# See LICENSE for details.

"""EUNICE Enterprise — inference backends."""
from core.backends.base import InferenceBackend
from core.backends.ollama import OllamaBackend
from core.backends.localai import LocalAIBackend

__all__ = ["InferenceBackend", "OllamaBackend", "LocalAIBackend"]
