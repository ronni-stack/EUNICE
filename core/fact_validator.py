# # EUNICE - Efficient Unified Neural Intelligence for Communication and Execution
# Copyright 2026 Ronny Koome
# Licensed under the Elastic License 2.0.
# See LICENSE for details.

"""EUNICE v0.8 — Fact Validation Layer
Prevents hallucinated, contradictory, and garbage facts from entering memory.
"""
import re
from difflib import SequenceMatcher
from typing import Optional

class FactValidator:
    """Validates facts before storage and during retrieval."""

    # Known false patterns from observed hallucinations
    FALSE_PATTERNS = {
        "italy", "pasta", "spaghetti", "originally from",
        "did you say i was from", "favorite meal is pasta",
        "did you say", "originally said", "as far as i can tell",
        "i see that you", "i recall that", "checking database",
        "upon re-checking", "it seems i was mistaken",
    }

    # Vague words that indicate low-confidence guesses
    VAGUE_WORDS = {"maybe", "perhaps", "probably", "i think", "guess", "assume"}

    def validate_before_storage(self, key: str, value: str, existing_facts: dict) -> tuple[bool, float, str]:
        """
        Validate a fact before storing.
        Returns: (should_store, confidence, reason)
        """
        value_lower = value.lower().strip()
        key_lower = key.lower().strip()

        # 1. Check against known false/hallucination patterns
        for false_pattern in self.FALSE_PATTERNS:
            if false_pattern in value_lower or false_pattern in key_lower:
                return False, 0.0, f"Matches known hallucination pattern: {false_pattern}"

        # 2. Check for self-referential meta-text (model quoting itself)
        if self._is_meta_text(value_lower):
            return False, 0.1, "Self-referential meta-text, not a fact about the user"

        # 3. Check for question-like values
        if value.strip().endswith("?") and len(value) < 80:
            return False, 0.2, "Value is a question, not a factual statement"

        # 4. Check for contradictions with existing facts
        contradiction = self._find_contradiction(key, value, existing_facts)
        if contradiction:
            return False, 0.3, f"Contradicts existing fact: {contradiction}"

        # 5. Check for near-duplicate keys
        duplicate = self._find_duplicate(key, value, existing_facts)
        if duplicate:
            return False, 0.4, f"Near-duplicate of existing fact: {duplicate}"

        # 6. Calculate confidence
        confidence = self._calculate_confidence(value)

        # 7. Reject very low confidence
        if confidence < 0.3:
            return False, confidence, "Confidence too low — likely a guess"

        return True, confidence, "Passed validation"

    def _is_meta_text(self, text: str) -> bool:
        """Detect if text is the model talking about itself or the conversation."""
        meta_markers = [
            "i see that", "i recall", "i remember", "checking",
            "database", "my records", "i don't see", "i'm not finding",
            "as far as i can tell", "it seems", "i was mistaken",
            "retracting", "upon re-checking", "i made an incorrect",
        ]
        return any(marker in text for marker in meta_markers)

    def _find_contradiction(self, new_key: str, new_value: str, existing: dict) -> Optional[str]:
        """Find if new fact contradicts an existing one."""
        new_val_lower = new_value.lower()

        for old_key, old_value in existing.items():
            # Same/similar key, different value
            if SequenceMatcher(None, new_key.lower(), old_key.lower()).ratio() > 0.85:
                old_val_lower = old_value.lower()
                if SequenceMatcher(None, new_val_lower, old_val_lower).ratio() < 0.5:
                    return f"{old_key} = {old_value}"

            # Semantic contradiction: new says "not X" and old says "X"
            if f"not {old_value.lower()}" in new_val_lower or f"no longer {old_value.lower()}" in new_val_lower:
                return f"{old_key} = {old_value}"

        return None

    def _find_duplicate(self, key: str, value: str, existing: dict) -> Optional[str]:
        """Find if this is a near-duplicate of an existing fact."""
        val_lower = value.lower()
        for old_key, old_value in existing.items():
            if SequenceMatcher(None, val_lower, old_value.lower()).ratio() > 0.9:
                return f"{old_key} = {old_value}"
        return None

    def _calculate_confidence(self, value: str) -> float:
        """Heuristic confidence score for a fact."""
        score = 0.5

        # Length: very short = vague, very long = rambling
        if 10 <= len(value) <= 200:
            score += 0.1

        # Contains proper nouns (capitalized words not at start)
        if re.search(r'\b[A-Z][a-z]+\b', value):
            score += 0.1

        # Contains specific numbers (dates, quantities)
        if re.search(r'\b\d{1,4}\b', value):
            score += 0.1

        # Starts with first-person or user's perspective
        if value.lower().startswith(("i ", "my ", "he ", "she ", "we ", "they ")):
            score += 0.1

        # Penalize vague language
        vague_count = sum(1 for w in self.VAGUE_WORDS if w in value.lower())
        score -= vague_count * 0.15

        # Penalize excessive punctuation (emotional/unstable)
        if value.count("!") > 2 or value.count("?") > 1:
            score -= 0.1

        return min(max(score, 0.0), 1.0)

    def validate_retrieved_facts(self, facts: list) -> list:
        """Filter and deduplicate retrieved facts before sending to model."""
        if not facts:
            return []

        seen = set()
        unique = []
        for f in facts:
            content = f.get("content", "").strip().lower()
            if content and content not in seen and len(content) > 5:
                seen.add(content)
                unique.append(f)

        return unique[:5]  # Limit to top 5

    def is_explicit_memory_command(self, text: str) -> bool:
        """Detect if user is explicitly telling EUNICE to remember something."""
        patterns = [
            r"remember that",
            r"remember i",
            r"remember my",
            r"save this",
            r"store this",
            r"note that",
            r"don't forget",
            r"add to my",
            r"my (birthday|address|phone|email|name) is",
        ]
        text_lower = text.lower()
        return any(re.search(p, text_lower) for p in patterns)
