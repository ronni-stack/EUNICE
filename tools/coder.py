"""EUNICE v0.9 — Coder Tool

Subprocess wrapper for the coding assistant.

Params:
  action: generate | edit | analyze | run
  request: natural language request (for generate/edit)
  filename: target file path (relative to user's coding workspace)
  language: python (default)
  timeout: execution timeout in seconds (default 10)
"""
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.coder import CoderAgent, CoderError


def main():
    try:
        params = json.load(sys.stdin)
    except json.JSONDecodeError:
        print(json.dumps({"error": "Invalid JSON params"}))
        return

    user_id = params.get("user_id") or os.environ.get("EUNICE_USER_ID") or "default"
    action = params.get("action", "generate")
    request = params.get("request", "")
    filename = params.get("filename", "")
    language = params.get("language", "python")
    timeout = int(params.get("timeout", 10))

    try:
        agent = CoderAgent(user_id)
        result = agent.execute(action, request=request, filename=filename,
                               language=language, timeout=timeout)
        print(json.dumps(result))
    except CoderError as e:
        print(json.dumps({"error": str(e)}))
    except Exception as e:
        print(json.dumps({"error": f"Unexpected error: {e}"}))


if __name__ == "__main__":
    main()
