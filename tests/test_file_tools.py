import pytest
from agent.tools import file_tools


def test_read_file_returns_contents(tmp_path):
    p = tmp_path / "a.txt"
    p.write_text("hello")
    assert file_tools.read_file(str(p)) == "hello"


def test_create_file_writes_new_file(tmp_path):
    p = tmp_path / "new.txt"
    file_tools.create_file(str(p), "content")
    assert p.read_text() == "content"


def test_create_file_raises_if_exists(tmp_path):
    p = tmp_path / "exists.txt"
    p.write_text("old")
    with pytest.raises(FileExistsError):
        file_tools.create_file(str(p), "new")


def test_append_file_adds_to_end(tmp_path):
    p = tmp_path / "a.txt"
    p.write_text("hello ")
    file_tools.append_file(str(p), "world")
    assert p.read_text() == "hello world"


def test_append_file_creates_if_missing(tmp_path):
    p = tmp_path / "new.txt"
    file_tools.append_file(str(p), "content")
    assert p.read_text() == "content"


def test_overwrite_file_replaces_contents(tmp_path):
    p = tmp_path / "a.txt"
    p.write_text("old")
    file_tools.overwrite_file(str(p), "new")
    assert p.read_text() == "new"


def test_overwrite_file_raises_if_missing(tmp_path):
    p = tmp_path / "missing.txt"
    with pytest.raises(FileNotFoundError):
        file_tools.overwrite_file(str(p), "new")


def test_delete_file_removes_file(tmp_path):
    p = tmp_path / "a.txt"
    p.write_text("bye")
    file_tools.delete_file(str(p))
    assert not p.exists()


def test_delete_file_raises_if_missing(tmp_path):
    p = tmp_path / "missing.txt"
    with pytest.raises(FileNotFoundError):
        file_tools.delete_file(str(p))


def test_delete_dir_removes_directory_tree(tmp_path):
    d = tmp_path / "sub"
    d.mkdir()
    (d / "a.txt").write_text("x")
    file_tools.delete_dir(str(d))
    assert not d.exists()


def test_delete_dir_raises_if_missing(tmp_path):
    d = tmp_path / "missing"
    with pytest.raises(NotADirectoryError):
        file_tools.delete_dir(str(d))


def test_move_file_relocates_file(tmp_path):
    src = tmp_path / "a.txt"
    dest = tmp_path / "b.txt"
    src.write_text("content")
    file_tools.move_file(str(src), str(dest))
    assert not src.exists()
    assert dest.read_text() == "content"


def test_move_file_raises_if_src_missing(tmp_path):
    src = tmp_path / "missing.txt"
    dest = tmp_path / "b.txt"
    with pytest.raises(FileNotFoundError):
        file_tools.move_file(str(src), str(dest))
