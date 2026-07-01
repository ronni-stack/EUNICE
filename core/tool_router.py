# # EUNICE - Efficient Unified Neural Intelligence for Communication and Execution
# Copyright 2026 Ronny Koome
# Licensed under the Elastic License 2.0.
# See LICENSE for details.

"""EUNICE v0.8 — Risk-Tiered Tool Router (multi-user)
Fixes: High-risk auto-execution, missing confirmation flow, poor error messages.
"""
import json
import os
import subprocess
from typing import Any
from datetime import datetime
from config import TOOLS_DIR, DATA_DIR, get_notes_path, RISK_LOW, RISK_MEDIUM, RISK_HIGH, RISK_CRITICAL
from core.rbac import has_permission, get_user_permissions
from memory.sqlite_store import SQLiteStore

class ToolRouter:
    """Routes tool calls with safety enforcement and audit logging."""

    TOOL_DESCRIPTIONS = {
        "network_scan": "Scan the local network for connected devices. Params: {'subnet': '192.168.1.0/24'}",
        "notes": "Append to, read, or search the user's notes. Params: {'action': 'append|read|search', 'content': '...', 'tag': 'note'}",
        "get_balance": "Check the user's bank balance from the local ledger. Requires confirmation.",
        "self_update": "Check for EUNICE software updates and create backups.",
        "transfer_funds": "Transfer money between accounts. Always denied (requires biometric confirmation).",
        "coder": "Generate, edit, analyze, or run code in the user's sandboxed workspace. Params: {'action': 'generate|edit|analyze|run', 'request': '...', 'filename': '...', 'language': 'python'}",
        "file_manager": "Read, write, list, or delete files in the user's sandboxed workspace. Params: {'action': 'read|write|list|delete', 'path': '...', 'content': '...'}",
    }

    def __init__(self, sqlite_store=None):
        self.risk_map = {}
        for t in RISK_LOW: self.risk_map[t] = "low"
        for t in RISK_MEDIUM: self.risk_map[t] = "medium"
        for t in RISK_HIGH: self.risk_map[t] = "high"
        for t in RISK_CRITICAL: self.risk_map[t] = "critical"

        # Audit log for all tool executions
        self.audit_log_path = DATA_DIR / "tool_audit.log"
        os.makedirs(DATA_DIR, exist_ok=True)

        # RBAC lookup; shared SQLiteStore avoids per-call re-instantiation
        self.sqlite_store = sqlite_store or SQLiteStore()

    def get_available_tools(self) -> list:
        """Scan tools/ directory and return tool metadata with risk tiers and descriptions."""
        tools = []
        if not TOOLS_DIR.exists():
            return tools
        for filename in sorted(os.listdir(TOOLS_DIR)):
            if filename.endswith(".py") and not filename.startswith("_"):
                tool_name = filename[:-3]
                tools.append({
                    "name": tool_name,
                    "description": self.TOOL_DESCRIPTIONS.get(tool_name, f"Execute the {tool_name} tool."),
                    "risk": self.risk_map.get(tool_name, "unknown")
                })
        return tools

    def _log_audit(self, tool_name: str, risk: str, params: dict, result: str, approved: bool = False):
        """Log every tool execution attempt."""
        timestamp = datetime.now().isoformat()
        status = "APPROVED" if approved else "DENIED"
        entry = f"[{timestamp}] {status} | {risk.upper()} | {tool_name} | params={json.dumps(params)} | result={result[:100]}\n"
        try:
            with open(self.audit_log_path, "a", encoding="utf-8") as f:
                f.write(entry)
        except Exception:
            pass

    async def execute(self, tool_name: str, params: dict, permissions: list = None) -> str:
        """Execute a tool with RBAC, risk-tier checks, and confirmation requirements."""
        user_id = params.get("user_id")
        if user_id:
            perms = permissions if permissions is not None else get_user_permissions(self.sqlite_store, user_id)
            if not has_permission(perms, f"tool:{tool_name}") and not has_permission(perms, "tool:execute"):
                risk = self.risk_map.get(tool_name, "unknown")
                msg = f"[DENIED: you do not have permission to use '{tool_name}']"
                self._log_audit(tool_name, risk, params, msg, approved=False)
                return msg

        risk = self.risk_map.get(tool_name, "unknown")

        # CRITICAL: Always deny
        if risk == "critical":
            msg = f"[DENIED: `{tool_name}` requires explicit biometric confirmation. Not yet implemented.]"
            self._log_audit(tool_name, risk, params, msg, approved=False)
            return msg

        # HIGH: Require explicit confirmation parameter
        if risk == "high":
            if not params.get("confirmed", False):
                msg = f"[PENDING: `{tool_name}` requires approval. Say 'confirm {tool_name}' to execute.]"
                self._log_audit(tool_name, risk, params, msg, approved=False)
                return msg
            # If confirmed, proceed but log heavily
            print(f"[HIGH RISK] Executing {tool_name} with CONFIRMED status")

        # MEDIUM: Execute + log
        if risk == "medium":
            print(f"[MEDIUM RISK] Executing {tool_name}")

        # LOW: Execute silently
        result = self._run_subprocess(tool_name, params)
        self._log_audit(tool_name, risk, params, result, approved=True)
        return result

    def _run_subprocess(self, tool_name: str, params: dict) -> str:
        """Run tool via subprocess with timeout and env isolation."""
        tool_path = TOOLS_DIR / f"{tool_name}.py"
        if not tool_path.exists():
            return f"[Tool '{tool_name}' not found in {TOOLS_DIR}]"

        try:
            env = os.environ.copy()
            env["EUNICE_DATA_DIR"] = str(DATA_DIR)
            env["EUNICE_NOTES_PATH"] = str(get_notes_path(params.get("user_id", "ronny")))
            env["EUNICE_USER_ID"] = str(params.get("user_id", "ronny"))
            env["EUNICE_TOOL_NAME"] = tool_name

            result = subprocess.run(
                ["python3", str(tool_path)],
                input=json.dumps(params),
                capture_output=True,
                text=True,
                timeout=30,
                env=env
            )
            if result.returncode == 0:
                return result.stdout.strip()
            return f"[Tool error (exit {result.returncode}): {result.stderr.strip()[:200]}]"
        except subprocess.TimeoutExpired:
            return f"[Tool '{tool_name}' timed out after 30s]"
        except Exception as e:
            return f"[Tool execution failed: {str(e)}]"
