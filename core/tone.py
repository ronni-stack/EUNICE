"""EUNICE v0.9 — Dynamic Tone Adaptation

Heuristic tone extraction from user messages.
Each tone dimension is a 0-1 score:
  formality:    0 = casual, 1 = formal
  verbosity:    0 = terse,  1 = detailed
  humor:        0 = dry,    1 = playful
  proactivity:  0 = reactive, 1 = anticipatory

These scores are updated incrementally so tone drifts slowly with user behavior.
"""
import re
from typing import Dict

# Keywords mapped to dimension and direction (0 = decrease, 1 = increase)
TONE_SIGNALS = {
    "formality": {
        0: ["hey", "yo", "sup", "lol", "haha", "yeah", "nah", "wanna", "gonna", "dude", "mate"],
        1: ["please", "would", "could", "thank you", "appreciate", "kindly", "dear", "sir", "madam"]
    },
    "verbosity": {
        0: ["short", "brief", "quick", "just", "tl;dr", "sum it up"],
        1: ["explain", "elaborate", "details", "in depth", "thoroughly", "walk me through"]
    },
    "humor": {
        0: ["serious", "formally", "strictly", "no jokes"],
        1: ["lol", "haha", "lmao", "funny", "joke", "humor", "😂", "🤣", "😄"]
    },
    "proactivity": {
        0: ["just tell me", "only", "don't do anything", "wait for me", "i'll ask"],
        1: ["remind me", "schedule", "plan", "check", "monitor", "track", "notify me", "keep an eye"]
    }
}


def _score_message(text: str, dimension: str) -> float:
    """Return a directional delta for one dimension based on keyword signals."""
    text_lower = text.lower()
    decrease_hits = sum(1 for kw in TONE_SIGNALS[dimension][0] if kw in text_lower)
    increase_hits = sum(1 for kw in TONE_SIGNALS[dimension][1] if kw in text_lower)

    # Also use message length as a verbosity signal
    if dimension == "verbosity":
        word_count = len(re.findall(r"\b\w+\b", text))
        if word_count < 10:
            decrease_hits += 1
        elif word_count > 30:
            increase_hits += 1

    if increase_hits == decrease_hits:
        return 0.0
    return 0.05 * (increase_hits - decrease_hits)


def analyze_message(text: str) -> Dict[str, float]:
    """Analyze a single user message and return tone deltas."""
    return {
        "tone_formality": _score_message(text, "formality"),
        "tone_verbosity": _score_message(text, "verbosity"),
        "tone_humor": _score_message(text, "humor"),
        "tone_proactivity": _score_message(text, "proactivity"),
    }


def tone_label(score: float) -> str:
    """Convert a 0-1 score to a human-readable label."""
    if score < 0.33:
        return "low"
    if score > 0.66:
        return "high"
    return "medium"


def format_tone_instruction(tone: Dict[str, float]) -> str:
    """Format a tone profile into a system-prompt instruction."""
    return f"""Adapt your tone to match this user profile:
- Formality: {tone_label(tone['formality'])} ({tone['formality']:.2f}) — 0=casual, 1=formal
- Verbosity: {tone_label(tone['verbosity'])} ({tone['verbosity']:.2f}) — 0=terse, 1=detailed
- Humor: {tone_label(tone['humor'])} ({tone['humor']:.2f}) — 0=dry, 1=playful
- Proactivity: {tone_label(tone['proactivity'])} ({tone['proactivity']:.2f}) — 0=reactive, 1=anticipatory

Do not mention these scores. Just mirror the user's style naturally."""
