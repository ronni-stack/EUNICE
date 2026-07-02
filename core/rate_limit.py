# # EUNICE - Efficient Unified Neural Intelligence for Communication and Execution
# Copyright 2026 Ronny Koome
# Licensed under the Elastic License 2.0.
# See LICENSE for details.

"""EUNICE Enterprise — Sliding-window rate limiter (Week 7)."""
import threading
import time
from collections import deque
from typing import Optional


class SlidingWindowLimiter:
    """Thread-safe sliding-window rate limiter."""

    def __init__(self, max_requests: int, window_seconds: int):
        self.max_requests = max_requests
        self.window = window_seconds
        self._hits: dict[str, deque] = {}
        self._lock = threading.Lock()

    def is_allowed(self, key: str) -> bool:
        """Return True if the key is within its limit and record the hit."""
        now = time.time()
        with self._lock:
            dq = self._hits.setdefault(key, deque())
            while dq and dq[0] < now - self.window:
                dq.popleft()
            if len(dq) >= self.max_requests:
                return False
            dq.append(now)
            return True


class RateLimiter:
    """Per-user and per-org rate limiter."""

    def __init__(self, user_max: int = 60, user_window: int = 60,
                 org_max: int = 300, org_window: int = 60):
        self.user_limiter = SlidingWindowLimiter(user_max, user_window)
        self.org_limiter = SlidingWindowLimiter(org_max, org_window)

    def check(self, user_id: str, org_id: Optional[str]) -> tuple[bool, str]:
        """Return (allowed, scope). scope is 'user' or 'org' if denied."""
        if not self.user_limiter.is_allowed(user_id):
            return False, "user"
        org_id = org_id or "default"
        if not self.org_limiter.is_allowed(org_id):
            return False, "org"
        return True, ""
