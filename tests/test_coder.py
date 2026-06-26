# # EUNICE - Efficient Unified Neural Intelligence for Communication and Execution
# Copyright 2026 Ronny Koome
# Licensed under the Elastic License 2.0.
# See LICENSE for details.

"""EUNICE v0.9 — Coding Assistant Tests"""
import pytest
import config as config_module
from core.coder import CoderAgent, CoderError

config_module.JWT_SECRET = "test-secret-32-bytes-long-1234567890"


@pytest.fixture
def coder(tmp_path, monkeypatch):
    monkeypatch.setattr(config_module, "FILES_DIR", tmp_path / "files")
    return CoderAgent("coder_user")


def test_write_and_read_generated_code(coder):
    # Simulate generation by writing directly
    result = coder.fm.write(coder._relative_path("hello.py"), "print('hello')")
    assert result["name"] == "hello.py"

    code = coder.fm.read(coder._relative_path("hello.py"))
    assert "print('hello')" in code


def test_analyze_existing_file(coder):
    coder.fm.write(coder._relative_path("script.py"), "x = 1\ny = 2\nprint(x + y)")
    analysis = coder.analyze("script.py")
    assert analysis["lines"] == 3
    assert analysis["filename"] == coder._relative_path("script.py")


def test_run_python_code(coder):
    coder.fm.write(coder._relative_path("add.py"), "print(2 + 3)")
    run_result = coder.run("add.py")
    assert run_result["returncode"] == 0
    assert "5" in run_result["stdout"]


def test_run_timeout(coder):
    coder.fm.write(coder._relative_path("loop.py"), "while True: pass")
    run_result = coder.run("loop.py", timeout=1)
    assert run_result["returncode"] == -1
    assert "timed out" in run_result["stderr"]


def test_dangerous_code_blocked(coder):
    coder.fm.write(coder._relative_path("danger.py"), "import os\nos.system('ls')")
    with pytest.raises(CoderError):
        coder.run("danger.py")


def test_path_sanitization(coder):
    rel = coder._relative_path("../../etc/passwd")
    assert ".." not in rel
    assert rel.startswith("coding/")


def test_edit_existing_file(coder, monkeypatch):
    coder.fm.write(coder._relative_path("edit.py"), "x = 1")

    async def fake_generate(prompt):
        return "x = 42"

    monkeypatch.setattr("core.coder.generate_non_stream", fake_generate)

    import asyncio
    result = asyncio.run(coder.edit("change x to 42", "edit.py"))

    assert "edit.py" in result["filename"]
    assert "42" in result["code"]
