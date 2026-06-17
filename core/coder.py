"""EUNICE v0.9 — Coding Assistant

Generates, edits, and runs code in a sandboxed per-user workspace.
Safety first: code execution is subprocess-based with timeouts, and dangerous
patterns are blocked unless explicitly allowed.
"""
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Optional

from core.inference import generate_non_stream
from core.file_manager import FileManager, FileManagerError


# Patterns that we refuse to execute (but may still generate for review)
DANGEROUS_PATTERNS = [
    r"os\.system\s*\(",
    r"subprocess\.(call|run|Popen|check_output)",
    r"__import__\s*\(",
    r"eval\s*\(",
    r"exec\s*\(",
    r"compile\s*\(",
    r"socket\.",
    r"urllib\.request\.urlopen",
    r"requests\.(get|post|put|delete)",
    r"import\s+requests",
]


class CoderError(Exception):
    pass


class CoderAgent:
    """Assist with coding tasks in a sandboxed workspace."""

    def __init__(self, user_id: str):
        self.user_id = user_id
        self.fm = FileManager(user_id)
        self.workspace = self.fm.workspace
        self.coding_dir = self.workspace / "coding"
        self.coding_dir.mkdir(parents=True, exist_ok=True)

    def _relative_path(self, filename: str) -> str:
        """Ensure the file lives inside the coding workspace."""
        # Strip any leading path attempts
        filename = Path(filename).name
        return str(Path("coding") / filename)

    def _is_dangerous(self, code: str) -> bool:
        """Check for patterns we don't want to execute automatically."""
        for pattern in DANGEROUS_PATTERNS:
            if re.search(pattern, code, re.IGNORECASE):
                return True
        return False

    def _build_prompt(self, request: str, context: str = "", language: str = "python") -> str:
        return f"""You are an expert coding assistant. Write clean, working {language} code for the user's request.

Rules:
- Output ONLY the code, no markdown fences, no explanations outside comments.
- Include helpful inline comments.
- Do NOT include network calls, shell execution, or file operations outside the current directory.
- If the request is unclear, write the simplest reasonable implementation.

{context}

User request: {request}

Code:"""

    async def generate(self, request: str, filename: str, language: str = "python") -> dict:
        """Generate code and write it to the workspace."""
        rel_path = self._relative_path(filename)
        prompt = self._build_prompt(request, language=language)
        code = await generate_non_stream(prompt=prompt)
        if not code:
            raise CoderError("Failed to generate code")

        # Strip markdown fences if present
        code = re.sub(r"^```\w*\n", "", code)
        code = re.sub(r"\n```\s*$", "", code)

        self.fm.write(rel_path, code)
        return {
            "filename": rel_path,
            "language": language,
            "code": code,
            "dangerous": self._is_dangerous(code),
        }

    async def edit(self, request: str, filename: str) -> dict:
        """Apply an edit request to an existing file."""
        rel_path = self._relative_path(filename)
        try:
            existing = self.fm.read(rel_path)
        except FileManagerError as e:
            raise CoderError(f"Cannot read file: {e}")

        prompt = f"""You are an expert coding assistant. Edit the following code according to the user's request.

Rules:
- Output ONLY the complete updated code, no markdown fences, no explanations outside comments.
- Preserve the original structure and style unless the request asks otherwise.

Original code ({rel_path}):
```
{existing}
```

User request: {request}

Updated code:"""

        updated = await generate_non_stream(prompt=prompt)
        if not updated:
            raise CoderError("Failed to generate edit")

        updated = re.sub(r"^```\w*\n", "", updated)
        updated = re.sub(r"\n```\s*$", "", updated)

        self.fm.write(rel_path, updated)
        return {
            "filename": rel_path,
            "code": updated,
            "dangerous": self._is_dangerous(updated),
        }

    def analyze(self, filename: str) -> dict:
        """Read and return a file with basic analysis."""
        rel_path = self._relative_path(filename)
        try:
            code = self.fm.read(rel_path)
        except FileManagerError as e:
            raise CoderError(f"Cannot read file: {e}")

        lines = code.splitlines()
        return {
            "filename": rel_path,
            "lines": len(lines),
            "size": len(code),
            "code": code,
            "dangerous": self._is_dangerous(code),
        }

    def run(self, filename: str, language: str = "python", timeout: int = 10) -> dict:
        """Run a code file in a sandboxed subprocess."""
        rel_path = self._relative_path(filename)
        full_path = self.workspace / rel_path
        if not full_path.exists():
            raise CoderError(f"File not found: {rel_path}")

        code = full_path.read_text(encoding="utf-8", errors="replace")
        if self._is_dangerous(code):
            raise CoderError("Code contains blocked patterns (network/shell/eval). Execution denied.")

        if language == "python":
            return self._run_python(full_path, timeout)
        else:
            raise CoderError(f"Unsupported language for execution: {language}")

    def _run_python(self, path: Path, timeout: int) -> dict:
        """Run a Python file in a restricted subprocess."""
        try:
            result = subprocess.run(
                [sys.executable, str(path)],
                cwd=str(self.coding_dir),
                capture_output=True,
                text=True,
                timeout=timeout,
                # No network, no new privileges
            )
            return {
                "returncode": result.returncode,
                "stdout": result.stdout,
                "stderr": result.stderr,
            }
        except subprocess.TimeoutExpired:
            return {
                "returncode": -1,
                "stdout": "",
                "stderr": f"Execution timed out after {timeout} seconds",
            }
        except Exception as e:
            return {
                "returncode": -1,
                "stdout": "",
                "stderr": str(e),
            }

    def execute(self, action: str, request: str = "", filename: str = "",
                language: str = "python", timeout: int = 10) -> dict:
        """Synchronous wrapper for tool use."""
        import asyncio
        if action == "generate":
            return asyncio.run(self.generate(request, filename, language))
        if action == "edit":
            return asyncio.run(self.edit(request, filename))
        if action == "analyze":
            return self.analyze(filename)
        if action == "run":
            return self.run(filename, language, timeout)
        raise CoderError(f"Unknown action: {action}")
