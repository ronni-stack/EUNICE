# # EUNICE - Efficient Unified Neural Intelligence for Communication and Execution
# Copyright 2026 Ronny Koome
# Licensed under the Elastic License 2.0.
# See LICENSE for details.

"""EUNICE Enterprise — Input sanitization helpers (Week 7)."""
import re
from pathlib import Path
from typing import Optional


def sanitize_text(text: str, max_length: int = 4000) -> str:
    """Strip dangerous control characters and truncate user-provided text."""
    if not isinstance(text, str):
        text = str(text)
    # Keep printable and common whitespace; remove other control chars.
    cleaned = "".join(ch for ch in text if ch == "\n" or ch == "\r" or ch == "\t" or ord(ch) >= 32)
    cleaned = cleaned.strip()
    if max_length and len(cleaned) > max_length:
        cleaned = cleaned[:max_length]
    return cleaned


def sanitize_filename(filename: str, default: str = "upload") -> str:
    """Return a safe filename: basename only, no path traversal, limited length."""
    if not isinstance(filename, str):
        filename = str(filename)
    # Collapse path separators and take basename.
    filename = filename.replace("\\", "/")
    filename = Path(filename).name
    # Remove characters that are not safe.
    filename = re.sub(r"[^\w.\-]", "_", filename)
    if not filename or filename in {".", ".."}:
        filename = default
    max_len = 200
    if len(filename) > max_len:
        name, ext = filename[:max_len], ""
        if "." in filename:
            parts = filename.rsplit(".", 1)
            name = parts[0][: max_len - len(parts[1]) - 1]
            ext = parts[1][:20]
        filename = f"{name}.{ext}" if ext else name
    return filename


# Simple heuristic list of known prompt-injection markers.
_PROMPT_INJECTION_MARKERS = (
    "ignore previous instructions",
    "ignore all previous instructions",
    "ignore the above",
    "disregard previous",
    "system prompt",
    "you are now",
    "developer mode",
    "DAN mode",
    "jailbreak",
    "do anything now",
)


def is_prompt_injection_attempt(text: str) -> bool:
    """Return True if the input looks like a prompt-injection attempt."""
    if not isinstance(text, str):
        return False
    lower = text.lower()
    return any(marker in lower for marker in _PROMPT_INJECTION_MARKERS)


def sanitize_json_input(data: dict, allowed_keys: Optional[set] = None) -> dict:
    """Return a dict with only allowed keys and sanitized string values."""
    if not isinstance(data, dict):
        return {}
    if allowed_keys is None:
        allowed_keys = set(data.keys())
    result = {}
    for key, value in data.items():
        if key not in allowed_keys:
            continue
        if isinstance(value, str):
            result[key] = sanitize_text(value)
        elif isinstance(value, dict):
            result[key] = sanitize_json_input(value)
        elif isinstance(value, list):
            result[key] = [
                sanitize_text(item) if isinstance(item, str) else item for item in value
            ]
        else:
            result[key] = value
    return result
