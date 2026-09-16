from agent.tools import confirmation


def test_is_destructive_true_for_destructive_actions():
    for action in ("overwrite", "delete_file", "delete_dir", "move_overwrite"):
        assert confirmation.is_destructive(action) is True


def test_is_destructive_false_for_safe_actions():
    for action in ("read", "create_file", "append"):
        assert confirmation.is_destructive(action) is False


def test_describe_action_overwrite_reports_line_diff(tmp_path):
    p = tmp_path / "a.txt"
    p.write_text("line1\nline2\nline3\n")
    desc = confirmation.describe_action("overwrite", str(p), content="line1\n")
    assert "OVERWRITE" in desc
    assert str(p) in desc
    assert "Reversible: No" in desc
    assert "lines" in desc


def test_describe_action_delete_file_reports_size(tmp_path):
    p = tmp_path / "a.txt"
    p.write_text("hello")
    desc = confirmation.describe_action("delete_file", str(p))
    assert "DELETE FILE" in desc
    assert "bytes" in desc
    assert "Reversible: No" in desc


def test_describe_action_delete_dir_warns_about_blast_radius(tmp_path):
    d = tmp_path / "sub"
    d.mkdir()
    (d / "a.txt").write_text("x")
    (d / "b.txt").write_text("y")
    desc = confirmation.describe_action("delete_dir", str(d))
    assert "RECURSIVE DELETE" in desc
    assert "2 files" in desc
    assert "WARNING" in desc


def test_describe_action_move_overwrite_reports_target(tmp_path):
    dest = tmp_path / "existing.txt"
    dest.write_text("old")
    src = tmp_path / "src.txt"
    src.write_text("new")
    desc = confirmation.describe_action("move_overwrite", str(src), dest=str(dest))
    assert "MOVE/RENAME" in desc
    assert str(dest) in desc


def test_confirm_returns_true_for_yes():
    assert confirmation.confirm("prompt", input_func=lambda _: "yes") is True


def test_confirm_returns_true_for_y_case_insensitive():
    assert confirmation.confirm("prompt", input_func=lambda _: "Y") is True


def test_confirm_returns_false_for_no():
    assert confirmation.confirm("prompt", input_func=lambda _: "no") is False


def test_confirm_returns_false_for_empty():
    assert confirmation.confirm("prompt", input_func=lambda _: "") is False


def test_confirm_returns_false_for_unrelated_text():
    assert confirmation.confirm("prompt", input_func=lambda _: "sure whatever") is False


def test_confirm_recursive_delete_requires_exact_dir_name():
    assert confirmation.confirm_recursive_delete(
        "prompt", "important_data", input_func=lambda _: "important_data"
    ) is True


def test_confirm_recursive_delete_rejects_yes_alone():
    assert confirmation.confirm_recursive_delete(
        "prompt", "important_data", input_func=lambda _: "yes"
    ) is False
