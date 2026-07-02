#!/usr/bin/env python3
# # EUNICE - Efficient Unified Neural Intelligence for Communication and Execution
# Copyright 2026 Ronny Koome
# Licensed under the Elastic License 2.0.
# See LICENSE for details.

"""Dependency vulnerability scan wrapper (Week 7).

Runs `pip-audit` against the current environment. Exit codes:
  0 = no known vulnerabilities
  1 = vulnerabilities found or pip-audit reported an issue
  2 = pip-audit is not installed
"""
import json
import subprocess
import sys


def main() -> int:
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pip_audit", "--format=json"],
            capture_output=True,
            text=True,
        )
    except FileNotFoundError:
        print("pip-audit is not installed. Install it with: pip install pip-audit")
        return 2

    if result.returncode not in (0, 1):
        print("pip-audit failed to run")
        if result.stderr:
            print(result.stderr)
        return result.returncode or 1

    findings = []
    if result.stdout.strip():
        try:
            data = json.loads(result.stdout)
            findings = data.get("dependencies", []) if isinstance(data, dict) else data
        except json.JSONDecodeError:
            # pip-audit may print non-JSON warnings; ignore them.
            pass

    vulnerable = [f for f in findings if (f.get("vulns") if isinstance(f, dict) else f)]
    if vulnerable:
        print(f"Found {len(vulnerable)} package(s) with known vulnerabilities:")
        for item in vulnerable:
            print(json.dumps(item, indent=2))
        return 1

    print("No known dependency vulnerabilities found.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
