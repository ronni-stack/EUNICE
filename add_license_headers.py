#!/usr/bin/env python3
"""
EUNICE License Header Injector
Adds Elastic License 2.0 headers to all source files in your project.
Skips files that already have the header.
"""

import os
import sys
import argparse
from pathlib import Path

# ── Configuration ─────────────────────────────────────────────────────────────

PROJECT_NAME = "EUNICE"
FULL_NAME = "Efficient Unified Neural Intelligence for Communication and Execution"
COPYRIGHT_YEAR = "2026"
AUTHOR = "Ronny Koome"
LICENSE_NAME = "Elastic License 2.0"

# File extensions → comment style
COMMENT_STYLES = {
    ".py":     ("# ", "# ", "# "),
    ".js":     ("/*\n * ", " * ", " */\n"),
    ".ts":     ("/*\n * ", " * ", " */\n"),
    ".tsx":    ("/*\n * ", " * ", " */\n"),
    ".jsx":    ("/*\n * ", " * ", " */\n"),
    ".html":   ("<!--\n  ", "  ", "\n-->\n"),
    ".css":    ("/*\n * ", " * ", " */\n"),
    ".scss":   ("/*\n * ", " * ", " */\n"),
    ".sh":     ("# ", "# ", "# "),
    ".bash":   ("# ", "# ", "# "),
    ".zsh":    ("# ", "# ", "# "),
    ".yml":    ("# ", "# ", "# "),
    ".yaml":   ("# ", "# ", "# "),
    ".json":   None,
    ".md":     None,
}

SKIP_DIRS = {
    "node_modules", "venv", ".venv", "__pycache__", ".git",
    "dist", "build", ".next", ".nuxt", "coverage", ".pytest_cache",
    "migrations", ".idea", ".vscode", "target", "out",
}

SKIP_FILES = {
    "LICENSE", "LICENSE.txt", "LICENSE.md",
    "CONTRIBUTING.md", "CHANGELOG.md", "README.md",
    ".gitignore", ".gitattributes", ".dockerignore",
    "package-lock.json", "yarn.lock", "pnpm-lock.yaml",
    "poetry.lock", "requirements.txt", "setup.py",
    "Dockerfile", "docker-compose.yml", "docker-compose.yaml",
}

# ── Core Logic ────────────────────────────────────────────────────────────────

def build_header(prefix, mid, suffix):
    lines = [
        f"{PROJECT_NAME} - {FULL_NAME}",
        f"Copyright {COPYRIGHT_YEAR} {AUTHOR}",
        f"Licensed under the {LICENSE_NAME}.",
        "See LICENSE for details.",
    ]
    body = "\n".join(f"{mid}{line}" for line in lines)
    return f"{prefix}{body}\n{suffix}"

def already_has_header(content, project_name=PROJECT_NAME):
    """Check if file already contains the EUNICE header."""
    return project_name in content[:500] and "Copyright" in content[:500]

def process_file(filepath, dry_run=False):
    """Add header to a single file if needed."""
    path = Path(filepath)
    ext = path.suffix.lower()

    style = COMMENT_STYLES.get(ext)
    if style is None:
        return "skipped"  # No comment style for this extension

    if path.name in SKIP_FILES:
        return "skipped"

    try:
        content = path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError) as e:
        return f"error: {e}"

    if already_has_header(content):
        return "already_has_header"

    # Preserve shebang for scripts
    shebang = ""
    rest = content
    if content.startswith("#!/"):
        first_nl = content.find("\n")
        if first_nl != -1:
            shebang = content[:first_nl + 1]
            rest = content[first_nl + 1:]

    # Build and inject header
    header = build_header(*style)
    new_content = shebang + header + rest

    if dry_run:
        return "would_inject"

    # Backup original
    backup_path = path.with_suffix(path.suffix + ".orig")
    if not backup_path.exists():
        path.rename(backup_path)

    path.write_text(new_content, encoding="utf-8")
    return "injected"

def walk_project(root_dir):
    """Yield all source files under root_dir, skipping unwanted directories."""
    root = Path(root_dir).resolve()
    for path in root.rglob("*"):
        if path.is_dir():
            continue
        # Skip hidden dirs and known build/vendor dirs
        parts = set(path.parts)
        if parts & SKIP_DIRS:
            continue
        if any(p.startswith(".") for p in path.relative_to(root).parts):
            continue
        yield path

def main():
    parser = argparse.ArgumentParser(
        description="Inject EUNICE license headers into source files."
    )
    parser.add_argument(
        "root", nargs="?", default=".",
        help="Project root directory (default: current directory)"
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Preview changes without modifying files"
    )
    parser.add_argument(
        "--restore", action="store_true",
        help="Restore .orig backups (undo injections)"
    )
    args = parser.parse_args()

    root = Path(args.root).resolve()
    if not root.is_dir():
        print(f"Error: {root} is not a directory.")
        sys.exit(1)

    # ── Restore mode ──────────────────────────────────────────────────────
    if args.restore:
        restored = 0
        for path in root.rglob("*.orig"):
            original = path.with_suffix(path.suffix.replace(".orig", ""))
            path.rename(original)
            restored += 1
            print(f"  Restored: {original.relative_to(root)}")
        print(f"\nRestored {restored} file(s).")
        return

    # ── Inject mode ───────────────────────────────────────────────────────
    stats = {
        "injected": 0,
        "already_has_header": 0,
        "skipped": 0,
        "error": 0,
    }

    print(f"Scanning: {root}\n")

    for filepath in walk_project(root):
        result = process_file(filepath, dry_run=args.dry_run)

        if result == "injected" or result == "would_inject":
            action = "[DRY-RUN] Would inject" if args.dry_run else "Injected"
            print(f"  {action}: {filepath.relative_to(root)}")
            stats["injected"] += 1
        elif result == "already_has_header":
            stats["already_has_header"] += 1
        elif result.startswith("error"):
            print(f"  ERROR: {filepath.relative_to(root)} — {result}")
            stats["error"] += 1
        else:
            stats["skipped"] += 1

    print(f"\n{'─' * 50}")
    print(f"  Injected:           {stats['injected']}")
    print(f"  Already had header: {stats['already_has_header']}")
    print(f"  Skipped:            {stats['skipped']}")
    print(f"  Errors:             {stats['error']}")
    print(f"{'─' * 50}")

    if not args.dry_run and stats["injected"] > 0:
        print("\nBackups created as *.orig files.")
        print("Run with --restore to undo all changes.")

if __name__ == "__main__":
    main()
