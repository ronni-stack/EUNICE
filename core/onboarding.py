"""EUNICE v0.8 — Autonomous Onboarding Engine
Manages progressive profiling through natural conversation.
"""
import re
from datetime import datetime
from typing import Optional
from memory.manager import MemoryManager

DEFAULT_USER_ID = "ronny"

class OnboardingEngine:
    """Manages autonomous user discovery without hardcoded scripts."""

    # Topic triggers for natural probe embedding
    PROBES = {
        "name": {
            "triggers": ["hey", "hi", "hello", "what's up"],
            "questions": [
                "By the way, what should I call you?",
                "What name do you go by?"
            ]
        },
        "work": {
            "triggers": ["tired", "busy", "meeting", "office", "deadline", "job", "work"],
            "questions": [
                "What do you do for work?",
                "What field are you in?"
            ]
        },
        "family": {
            "triggers": ["mom", "dad", "wife", "husband", "kids", "home", "family", "sister", "brother"],
            "questions": [
                "Do you have family nearby?",
                "Anyone else I should know about?"
            ]
        },
        "location": {
            "triggers": ["weather", "traffic", "commute", "city", "live", "based"],
            "questions": [
                "Where are you based?",
                "What city do you live in?"
            ]
        },
        "preferences": {
            "triggers": ["like", "love", "hate", "prefer", "favorite", "favourite"],
            "questions": [
                "What are you into?",
                "Any preferences I should keep in mind?"
            ]
        }
    }

    def __init__(self, user_id: str, memory: MemoryManager = None):
        self.user_id = user_id
        self.memory = memory or MemoryManager()
        self.memory.ensure_user(user_id)
        self.gaps = self._load_gaps()
        self.user = self.memory.get_user(user_id) or {}
        self.rapport = self.user.get("rapport_level", 0)

    def _load_gaps(self) -> list:
        gaps = self.memory.get_profile_gaps(self.user_id)
        if not gaps:
            # Should have been created by ensure_user, but guard anyway
            self.memory.ensure_user(self.user_id)
            gaps = self.memory.get_profile_gaps(self.user_id)
        return gaps

    def is_first_interaction(self) -> bool:
        """True if this user has no message history yet."""
        user = self.memory.get_user(self.user_id)
        if not user:
            return True
        # If onboarding_complete is explicitly true, not first interaction
        if user.get("onboarding_complete"):
            return False
        # Otherwise, check if any facts or messages exist
        facts = self.memory.sqlite.get_facts(user_id=self.user_id)
        return len(facts) == 0

    def get_greeting(self) -> str:
        """Initial onboarding greeting."""
        return "Hi, I'm EUNICE. I'm your personal assistant. What should I call you?"

    def process_message(self, user_msg: str, assistant_msg: str) -> Optional[str]:
        """
        Called after every exchange during onboarding.
        Extracts implicit facts, updates rapport, and optionally returns a probe.
        """
        # Update rapport
        rapport_gain = self._calculate_rapport_gain(user_msg)
        self.rapport = min(10.0, self.rapport + rapport_gain)
        self.memory.update_user(self.user_id, rapport_level=self.rapport)

        # Extract simple facts locally for onboarding gaps
        self._update_gaps_from_message(user_msg)

        # Mark onboarding complete if name is known
        if self._is_name_known() and not self.user.get("onboarding_complete"):
            self.memory.update_user(self.user_id, onboarding_complete=True)

        # Generate a natural probe if appropriate
        return self._generate_natural_probe(user_msg)

    def _calculate_rapport_gain(self, user_msg: str) -> float:
        """Estimate rapport gain from a user message."""
        msg_len = len(user_msg.strip())
        if msg_len < 5:
            return 0.05
        if msg_len < 30:
            return 0.15
        return 0.25

    def _update_gaps_from_message(self, user_msg: str):
        """Simple rule-based updates to profile gaps from a user message."""
        text_lower = user_msg.lower()

        # Name detection: "I'm John", "Call me Alex", "My name is Sam"
        name_patterns = [
            r"(?:i am|i'm|call me|my name is|name is)\s+([a-z]+)",
            r"^([a-z]{2,20})$"  # Single-word name answer
        ]
        for pattern in name_patterns:
            match = re.search(pattern, text_lower)
            if match:
                name = match.group(1).strip().capitalize()
                if len(name) >= 2:
                    self.memory.update_user(self.user_id, name=name, preferred_name=name)
                    self.memory.sqlite.save_fact("name", f"My name is {name}.", "personal", 1.0, user_id=self.user_id, source="onboarding")
                    self.memory.update_profile_gap(self.user_id, "name", known=True, confidence=1.0)
                    break

        # Work detection
        if any(t in text_lower for t in ["i work", "my job", "i'm a ", "i am a ", "i do "]):
            self.memory.update_profile_gap(self.user_id, "work", known=True, confidence=0.8)

        # Location detection
        if any(t in text_lower for t in ["i live in", "i'm in ", "based in", "from "]):
            self.memory.update_profile_gap(self.user_id, "location", known=True, confidence=0.8)

        # Family detection
        if any(t in text_lower for t in ["my wife", "my husband", "my sister", "my brother", "my mom", "my dad", "my kids"]):
            self.memory.update_profile_gap(self.user_id, "family", known=True, confidence=0.7)

    def _is_name_known(self) -> bool:
        user = self.memory.get_user(self.user_id)
        return bool(user and user.get("name"))

    def should_probe(self, topic: str) -> bool:
        """Check if we're allowed to probe a topic now."""
        gap = next((g for g in self.gaps if g["topic"] == topic), None)
        if not gap:
            return False
        if gap.get("known"):
            return False
        # Need enough rapport for the priority
        if self.rapport < gap["priority"] * 3:
            return False
        # Cooldown: don't probe same topic too often
        if gap.get("probe_count", 0) >= 2:
            return False
        return True

    def _generate_natural_probe(self, context: str) -> Optional[str]:
        """Find a high-priority gap and embed it naturally in conversation."""
        # Sort gaps by priority * (1 - confidence), descending
        urgent = sorted(
            [g for g in self.gaps if not g.get("known")],
            key=lambda g: g["priority"] * (1 - (g.get("confidence") or 0)),
            reverse=True
        )

        for gap in urgent:
            if self.should_probe(gap["topic"]):
                probe = self._craft_probe(gap["topic"], context)
                if probe:
                    self.memory.update_profile_gap(
                        self.user_id, gap["topic"],
                        last_probed=datetime.now().isoformat(),
                        probe_count=gap.get("probe_count", 0) + 1
                    )
                    return probe

        return None

    def _craft_probe(self, topic: str, context: str) -> Optional[str]:
        """Make the question feel like a natural follow-up."""
        context_lower = context.lower()
        probes = self.PROBES.get(topic)
        if not probes:
            return None

        for trigger in probes["triggers"]:
            if trigger in context_lower:
                return probes["questions"][0]

        # Fallback: return first question if no trigger matched
        return probes["questions"][0]
