#!/usr/bin/env python3
"""
EUNICE Tool: Notes
Appends notes to the user's personal markdown file.
Reads JSON from stdin, writes result to stdout.
"""

import json
import sys
import os
from datetime import datetime
from pathlib import Path

DEFAULT_NOTES_PATH = os.environ.get("EUNICE_NOTES_PATH", "/tmp/eunice_notes.md")

def main():
    try:
        params = json.load(sys.stdin) if sys.stdin else {}
    except json.JSONDecodeError:
        params = {}

    action = params.get("action", "append")
    content = params.get("content", "").strip()
    tag = params.get("tag", "note")
    user_id = params.get("user_id", os.environ.get("EUNICE_USER_ID", "default"))

    notes_path = Path(os.environ.get("EUNICE_NOTES_PATH", DEFAULT_NOTES_PATH))
    # If path contains {user_id}, format it
    if "{user_id}" in str(notes_path):
        notes_path = Path(str(notes_path).format(user_id=user_id))
    notes_path.parent.mkdir(parents=True, exist_ok=True)

    if action == "append":
        if not content:
            print("[Error: No content provided for note]")
            return

        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
        entry = f"### {tag} — {timestamp}\n{content}\n"

        with open(notes_path, "a", encoding="utf-8") as f:
            f.write(entry)

        print(f"[Note saved to {notes_path}]")

    elif action == "read":
        if not os.path.exists(notes_path):
            print("[No notes found]")
            return
        with open(notes_path, "r", encoding="utf-8") as f:
            print(f.read())

    elif action == "search":
        query = params.get("query", "").lower()
        if not os.path.exists(notes_path):
            print("[No notes found]")
            return
        with open(notes_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
        matches = [l for l in lines if query in l.lower()]
        if matches:
            print("".join(matches))
        else:
            print(f"[No notes matching '{query}']")

    else:
        print(f"[Unknown action: {action}]")

if __name__ == "__main__":
    main()
