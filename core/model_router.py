# # EUNICE - Efficient Unified Neural Intelligence for Communication and Execution
# Copyright 2026 Ronny Koome
# Licensed under the Elastic License 2.0.
# See LICENSE for details.

"""EUNICE Enterprise — model selection and governance router.

The router maps task tiers to ideal models, checks what is actually available
on the configured backend, and returns the best available model with
fallback metadata.
"""
import logging
from dataclasses import dataclass
from typing import Optional

from core.backends.base import InferenceBackend

logger = logging.getLogger("eunice.model_router")


@dataclass
class ModelSelection:
    """Result of a model routing decision."""
    model: str
    ideal_model: str
    fallback: bool
    note: str


class ModelRouter:
    """Selects the best available model for a given task tier."""

    def __init__(
        self,
        backend: InferenceBackend,
        default_model: str,
        tier_map: dict,
        approved_models: Optional[dict] = None,
        fallback_on_missing: bool = True,
    ):
        self.backend = backend
        self.default_model = default_model
        self.tier_map = tier_map
        self.approved_models = approved_models or {}
        self.fallback_on_missing = fallback_on_missing

    async def select(self, task_tier: str) -> ModelSelection:
        """Select a model for the given task tier."""
        ideal = self.tier_map.get(task_tier, self.default_model)
        available = await self.backend.list_models()

        # If only approved models are allowed, filter availability
        if self.approved_models:
            available = [m for m in available if m in self.approved_models]

        if ideal in available:
            return ModelSelection(
                model=ideal,
                ideal_model=ideal,
                fallback=False,
                note="ideal model selected",
            )

        if not self.fallback_on_missing:
            return ModelSelection(
                model=self.default_model,
                ideal_model=ideal,
                fallback=True,
                note=f"ideal model {ideal} not available and fallback is disabled",
            )

        # Fallback: choose the best available model by declared capability.
        # Order available models by their declared VRAM / capability if known.
        candidates = self._ranked_candidates(available)
        for candidate in candidates:
            if candidate in available:
                return ModelSelection(
                    model=candidate,
                    ideal_model=ideal,
                    fallback=True,
                    note=f"fallback: ideal model {ideal} not available; using {candidate}",
                )

        # Last resort: default model
        return ModelSelection(
            model=self.default_model,
            ideal_model=ideal,
            fallback=True,
            note=f"fallback: ideal model {ideal} not available; using default {self.default_model}",
        )

    def _ranked_candidates(self, available: list[str]) -> list[str]:
        """Return candidate models ordered from most to least capable."""
        if not self.approved_models:
            # Simple heuristic: prefer larger parameter counts in the name.
            return sorted(
                available,
                key=lambda m: self._extract_params(m),
                reverse=True,
            )

        # Use approved_models metadata to sort by vram_gb / capability.
        def score(name):
            meta = self.approved_models.get(name, {})
            return meta.get("vram_gb", 0) + self._extract_params(name) * 0.1

        return sorted(available, key=score, reverse=True)

    @staticmethod
    def _extract_params(model_name: str) -> int:
        """Extract parameter count from a model name like 'llama3.1:8b'."""
        import re
        match = re.search(r"(\d+)(b|B)", model_name)
        return int(match.group(1)) if match else 0
