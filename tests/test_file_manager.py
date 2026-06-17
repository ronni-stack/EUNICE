"""EUNICE v0.9 — File Manager Tests"""
import pytest
import config as config_module
from core.file_manager import FileManager, FileManagerError

config_module.JWT_SECRET = "test-secret-32-bytes-long-1234567890"


@pytest.fixture
def fm(tmp_path, monkeypatch):
    monkeypatch.setattr(config_module, "FILES_DIR", tmp_path / "files")
    return FileManager("test_user")


def test_write_and_read(fm):
    fm.write("hello.txt", "Hello, world!")
    content = fm.read("hello.txt")
    assert content == "Hello, world!"


def test_append(fm):
    fm.write("log.txt", "line 1\n")
    fm.write("log.txt", "line 2\n", mode="append")
    content = fm.read("log.txt")
    assert content == "line 1\nline 2\n"


def test_list(fm):
    fm.write("a.txt", "a")
    fm.write("subdir/b.txt", "b")
    entries = fm.list("")
    names = {e["name"] for e in entries}
    assert "a.txt" in names
    assert "subdir" in names


def test_mkdir(fm):
    fm.mkdir("projects/code")
    assert (fm.workspace / "projects" / "code").is_dir()


def test_delete_requires_confirmation(fm):
    fm.write("tmp.txt", "tmp")
    with pytest.raises(FileManagerError):
        fm.delete("tmp.txt", confirmed=False)


def test_delete_confirmed(fm):
    fm.write("tmp.txt", "tmp")
    result = fm.delete("tmp.txt", confirmed=True)
    assert result["deleted"]
    assert not (fm.workspace / "tmp.txt").exists()


def test_path_traversal_blocked(fm):
    with pytest.raises(FileManagerError):
        fm.read("../secret.txt")

    with pytest.raises(FileManagerError):
        fm.read("/etc/passwd")


def test_search(fm):
    fm.write("notes.txt", "notes")
    fm.write("todo.txt", "todo")
    fm.write("archive/old.txt", "old")
    results = fm.search("*.txt")
    names = {r["name"] for r in results}
    assert "notes.txt" in names
    assert "todo.txt" in names
    assert "old.txt" in names


def test_nested_paths(fm):
    fm.write("deep/nested/path/file.txt", "deep content")
    assert fm.read("deep/nested/path/file.txt") == "deep content"
