# # EUNICE - Efficient Unified Neural Intelligence for Communication and Execution
# Copyright 2026 Ronny Koome
# Licensed under the Elastic License 2.0.
# See LICENSE for details.

"""EUNICE Enterprise — Immutable append-only audit logger.

All security-relevant events are written as JSON Lines to data/audit.log.
The logger only appends; there is no API to modify or delete entries.
"""
import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from config import DATA_DIR

DEFAULT_AUDIT_PATH = DATA_DIR / "audit.log"


class AuditLogger:
    """Thread-safe, append-only audit logger."""

    def __init__(self, log_path: Optional[Path] = None):
        self.log_path = log_path or DEFAULT_AUDIT_PATH
        self._lock = threading.Lock()
        os.makedirs(self.log_path.parent, exist_ok=True)

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def _write(self, entry: Dict[str, Any]):
        """Append a single JSON line to the audit log."""
        with self._lock:
            with open(self.log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, default=str, ensure_ascii=False) + "\n")
            # Best-effort immutability hint: owner read/write only.
            try:
                os.chmod(self.log_path, 0o600)
            except Exception:
                pass

    def _base_entry(
        self,
        event_type: str,
        actor: str = "anonymous",
        org_id: Optional[str] = None,
        action: str = "",
        resource: str = "",
        status: str = "",
        details: Optional[Dict[str, Any]] = None,
        session: Optional[str] = None,
        trail_id: Optional[str] = None,
        run_id: Optional[str] = None,
        ip: Optional[str] = None,
        device_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        entry = {
            "timestamp": self._now(),
            "event_type": event_type,
            "actor": actor,
            "action": action,
            "resource": resource,
            "status": status,
            "details": details or {},
        }
        for key, value in [
            ("org_id", org_id),
            ("session", session),
            ("trail_id", trail_id),
            ("run_id", run_id),
            ("ip", ip),
            ("device_id", device_id),
        ]:
            if value is not None:
                entry[key] = value
        return entry

    def log_tool_call(
        self,
        tool_name: str,
        user_id: str,
        org_id: Optional[str] = None,
        params: Optional[Dict[str, Any]] = None,
        result: str = "",
        status: str = "success",
        risk: str = "unknown",
        session: Optional[str] = None,
        ip: Optional[str] = None,
        device_id: Optional[str] = None,
    ):
        """Log a subprocess tool execution attempt."""
        details = {"risk": risk}
        if params:
            # Avoid logging secrets or huge payloads
            details["params"] = {k: v for k, v in params.items() if k != "content"}
        if result:
            details["result_preview"] = result[:500]
        entry = self._base_entry(
            event_type="tool_call",
            actor=user_id,
            org_id=org_id,
            action="execute",
            resource=f"tool:{tool_name}",
            status=status,
            details=details,
            session=session,
            ip=ip,
            device_id=device_id,
        )
        self._write(entry)

    def log_memory_access(
        self,
        action: str,
        user_id: str,
        org_id: Optional[str] = None,
        resource: str = "",
        details: Optional[Dict[str, Any]] = None,
        session: Optional[str] = None,
        ip: Optional[str] = None,
        device_id: Optional[str] = None,
    ):
        """Log a memory read/write event."""
        entry = self._base_entry(
            event_type="memory_access",
            actor=user_id,
            org_id=org_id,
            action=action,
            resource=resource,
            status="success",
            details=details or {},
            session=session,
            ip=ip,
            device_id=device_id,
        )
        self._write(entry)

    def log_reasoning_step(
        self,
        run_id: str,
        user_id: str,
        step_index: int,
        thought: str = "",
        action: str = "",
        observation: str = "",
        status: str = "success",
        org_id: Optional[str] = None,
        session: Optional[str] = None,
        ip: Optional[str] = None,
        device_id: Optional[str] = None,
    ):
        """Log a single ReAct step."""
        entry = self._base_entry(
            event_type="reasoning_step",
            actor=user_id,
            org_id=org_id,
            action="step",
            resource=f"run:{run_id}",
            status=status,
            details={
                "step_index": step_index,
                "thought": thought[:500],
                "action": action,
                "observation": observation[:500],
            },
            run_id=run_id,
            session=session,
            ip=ip,
            device_id=device_id,
        )
        self._write(entry)

    def log_reasoning_run(
        self,
        run_id: str,
        user_id: str,
        goal: str = "",
        status: str = "started",
        org_id: Optional[str] = None,
        session: Optional[str] = None,
        ip: Optional[str] = None,
        device_id: Optional[str] = None,
    ):
        """Log ReAct run lifecycle events (started, completed, max_steps, pending_approval)."""
        entry = self._base_entry(
            event_type="reasoning_run",
            actor=user_id,
            org_id=org_id,
            action="run",
            resource=f"run:{run_id}",
            status=status,
            details={"goal": goal[:500]},
            run_id=run_id,
            session=session,
            ip=ip,
            device_id=device_id,
        )
        self._write(entry)

    def log_auth_event(
        self,
        event: str,
        user_id: str = "anonymous",
        org_id: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        status: str = "success",
        ip: Optional[str] = None,
        device_id: Optional[str] = None,
    ):
        """Log authentication/authorization events."""
        entry = self._base_entry(
            event_type="auth_event",
            actor=user_id,
            org_id=org_id,
            action=event,
            resource="auth",
            status=status,
            details=details or {},
            ip=ip,
            device_id=device_id,
        )
        self._write(entry)

    def log_permission_denied(
        self,
        user_id: str,
        permission: str,
        resource: str = "",
        details: Optional[Dict[str, Any]] = None,
        org_id: Optional[str] = None,
        ip: Optional[str] = None,
        device_id: Optional[str] = None,
    ):
        """Log a permission denial."""
        entry = self._base_entry(
            event_type="permission_denied",
            actor=user_id,
            org_id=org_id,
            action="denied",
            resource=resource,
            status="denied",
            details={"permission": permission, **(details or {})},
            ip=ip,
            device_id=device_id,
        )
        self._write(entry)

    def read(self, limit: int = 100, offset: int = 0, since: Optional[str] = None,
             event_type: Optional[str] = None, user_id: Optional[str] = None) -> list:
        """Read audit entries. Does not modify the log."""
        entries = []
        if not self.log_path.exists():
            return entries

        with self._lock:
            with open(self.log_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entry = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if since and entry.get("timestamp", "") < since:
                        continue
                    if event_type and entry.get("event_type") != event_type:
                        continue
                    if user_id and entry.get("actor") != user_id:
                        continue
                    entries.append(entry)

        # Apply offset/limit after filtering
        return entries[offset:offset + limit]


# Module-level singleton for convenience
_default_logger: Optional[AuditLogger] = None


def get_audit_logger() -> AuditLogger:
    global _default_logger
    if _default_logger is None:
        _default_logger = AuditLogger()
    return _default_logger
