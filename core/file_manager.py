# # EUNICE - Efficient Unified Neural Intelligence for Communication and Execution
# Copyright 2026 Ronny Koome
# Licensed under the Elastic License 2.0.
# See LICENSE for details.

"""EUNICE v0.9 — File Manager (Local Sandbox)

Provides sandboxed file operations per user. All paths are resolved inside
`data/files/{user_id}/` to prevent traversal outside the workspace.

Actions:
  read, write, append, list, delete, mkdir, search, info

Destructive operations (delete, overwrite) require explicit confirmation.
Online/cloud providers can be added later as additional backends.
"""
import os
import re
import shutil
from pathlib import Path
from typing import Optional

from config import FILES_DIR


class FileManagerError(Exception):
    pass


class FileManager:
    """Sandboxed file operations for a single user."""

    def __init__(self, user_id: str):
        self.user_id = user_id
        self.workspace = FILES_DIR / user_id
        self.workspace.mkdir(parents=True, exist_ok=True)

    def _resolve_path(self, relative_path: str, must_exist: bool = False) -> Path:
        """Resolve a relative path inside the user's workspace."""
        if not relative_path:
            relative_path = "."

        # Reject absolute paths and traversal attempts
        if Path(relative_path).is_absolute():
            raise FileManagerError("Absolute paths are not allowed")
        if ".." in Path(relative_path).parts:
            raise FileManagerError("Path traversal is not allowed")

        resolved = (self.workspace / relative_path).resolve()
        # Ensure the resolved path is still inside the workspace
        try:
            resolved.relative_to(self.workspace.resolve())
        except ValueError:
            raise FileManagerError("Path is outside the allowed workspace")

        if must_exist and not resolved.exists():
            raise FileManagerError(f"Path does not exist: {relative_path}")

        return resolved

    def info(self, path: str = "") -> dict:
        """Return workspace info."""
        target = self._resolve_path(path)
        return {
            "workspace": str(self.workspace),
            "path": str(target),
            "exists": target.exists(),
            "is_file": target.is_file(),
            "is_dir": target.is_dir(),
            "size": target.stat().st_size if target.exists() and target.is_file() else 0,
        }

    def list(self, path: str = "") -> list:
        """List files and directories under the given relative path."""
        target = self._resolve_path(path)
        if not target.exists():
            raise FileManagerError(f"Path does not exist: {path}")
        if target.is_file():
            return [self._entry_info(target, path)]

        entries = []
        for entry in sorted(target.iterdir()):
            rel = str(Path(path) / entry.name) if path else entry.name
            entries.append(self._entry_info(entry, rel))
        return entries

    def _entry_info(self, path: Path, relative: str) -> dict:
        stat = path.stat()
        return {
            "name": path.name,
            "path": relative,
            "type": "file" if path.is_file() else "directory",
            "size": stat.st_size if path.is_file() else 0,
            "modified": stat.st_mtime,
        }

    def read(self, path: str, limit: int = 100_000) -> str:
        """Read text from a file."""
        target = self._resolve_path(path, must_exist=True)
        if not target.is_file():
            raise FileManagerError(f"Not a file: {path}")
        try:
            text = target.read_text(encoding="utf-8", errors="replace")
            if len(text) > limit:
                text = text[:limit] + f"\n\n[truncated: file is {target.stat().st_size} bytes]"
            return text
        except Exception as e:
            raise FileManagerError(f"Failed to read file: {e}")

    def write(self, path: str, content: str, mode: str = "write") -> dict:
        """Write or append content to a file."""
        target = self._resolve_path(path)
        target.parent.mkdir(parents=True, exist_ok=True)

        try:
            if mode == "append":
                with open(target, "a", encoding="utf-8") as f:
                    f.write(content)
            else:
                target.write_text(content, encoding="utf-8")
        except Exception as e:
            raise FileManagerError(f"Failed to write file: {e}")

        return self._entry_info(target, path)

    def mkdir(self, path: str) -> dict:
        """Create a directory."""
        target = self._resolve_path(path)
        target.mkdir(parents=True, exist_ok=True)
        return self._entry_info(target, path)

    def delete(self, path: str, confirmed: bool = False) -> dict:
        """Delete a file or directory. Requires confirmation."""
        if not confirmed:
            raise FileManagerError("Deletion requires confirmed=True")

        target = self._resolve_path(path, must_exist=True)
        try:
            if target.is_file():
                target.unlink()
            elif target.is_dir():
                shutil.rmtree(target)
            else:
                raise FileManagerError(f"Unsupported file type: {path}")
        except Exception as e:
            raise FileManagerError(f"Failed to delete: {e}")

        return {"deleted": True, "path": path}

    def search(self, pattern: str, path: str = "") -> list:
        """Search file names under a path using a glob pattern."""
        target = self._resolve_path(path)
        if not target.exists():
            raise FileManagerError(f"Path does not exist: {path}")

        results = []
        for match in target.rglob(pattern):
            try:
                rel = match.relative_to(self.workspace)
                results.append(self._entry_info(match, str(rel)))
            except ValueError:
                continue
        return results

    def execute(self, action: str, path: str = "", content: str = "",
                confirmed: bool = False, limit: int = 100_000,
                pattern: str = "") -> dict:
        """Unified entry point used by the tool wrapper."""
        action = action.lower().strip()

        if action == "info":
            return {"result": self.info(path)}
        if action == "list":
            return {"result": self.list(path)}
        if action == "read":
            return {"result": self.read(path, limit=limit)}
        if action == "write":
            return {"result": self.write(path, content, mode="write")}
        if action == "append":
            return {"result": self.write(path, content, mode="append")}
        if action == "mkdir":
            return {"result": self.mkdir(path)}
        if action == "delete":
            return {"result": self.delete(path, confirmed=confirmed)}
        if action == "search":
            return {"result": self.search(pattern or path, path=path)}

        raise FileManagerError(f"Unknown action: {action}")
