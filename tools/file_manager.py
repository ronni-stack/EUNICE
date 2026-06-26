# # EUNICE - Efficient Unified Neural Intelligence for Communication and Execution
# Copyright 2026 Ronny Koome
# Licensed under the Elastic License 2.0.
# See LICENSE for details.

"""EUNICE v0.9 — File Manager Tool

Sandboxed file operations. Runs as a subprocess via ToolRouter.

Params:
  action:  info | list | read | write | append | mkdir | delete | search
  path:    relative path inside user's workspace
  content: text content for write/append
  confirmed: True required for delete
  limit:   max chars for read (default 100000)
  pattern: glob pattern for search
"""
import json
import os
import sys
from pathlib import Path

# Allow importing from project root
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.file_manager import FileManager, FileManagerError


def main():
    try:
        params = json.load(sys.stdin)
    except json.JSONDecodeError:
        print(json.dumps({"error": "Invalid JSON params"}))
        return

    user_id = params.get("user_id") or os.environ.get("EUNICE_USER_ID") or "default"
    action = params.get("action", "info")
    path = params.get("path", "")
    content = params.get("content", "")
    confirmed = bool(params.get("confirmed", False))
    limit = int(params.get("limit", 100000))
    pattern = params.get("pattern", "")

    try:
        fm = FileManager(user_id)
        result = fm.execute(
            action=action,
            path=path,
            content=content,
            confirmed=confirmed,
            limit=limit,
            pattern=pattern,
        )
        print(json.dumps(result))
    except FileManagerError as e:
        print(json.dumps({"error": str(e)}))
    except Exception as e:
        print(json.dumps({"error": f"Unexpected error: {e}"}))


if __name__ == "__main__":
    main()
