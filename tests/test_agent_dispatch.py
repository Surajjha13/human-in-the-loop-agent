from agent import agent as agent_dispatch


def test_delete_declined_leaves_file_untouched(tmp_path):
    p = tmp_path / "a.txt"
    p.write_text("data")
    log_path = str(tmp_path / "log.jsonl")

    result = agent_dispatch.dispatch(
        "delete_file", str(p), input_func=lambda _: "no", log_path=log_path
    )

    assert p.exists()
    assert result.executed is False


def test_delete_approved_removes_file(tmp_path):
    p = tmp_path / "a.txt"
    p.write_text("data")
    log_path = str(tmp_path / "log.jsonl")

    result = agent_dispatch.dispatch(
        "delete_file", str(p), input_func=lambda _: "yes", log_path=log_path
    )

    assert not p.exists()
    assert result.executed is True


def test_overwrite_requires_yes(tmp_path):
    p = tmp_path / "a.txt"
    p.write_text("old")
    log_path = str(tmp_path / "log.jsonl")

    result = agent_dispatch.dispatch(
        "overwrite", str(p), content="new", input_func=lambda _: "yes", log_path=log_path
    )

    assert p.read_text() == "new"
    assert result.executed is True


def test_overwrite_declined_leaves_content_unchanged(tmp_path):
    p = tmp_path / "a.txt"
    p.write_text("old")
    log_path = str(tmp_path / "log.jsonl")

    result = agent_dispatch.dispatch(
        "overwrite", str(p), content="new", input_func=lambda _: "n", log_path=log_path
    )

    assert p.read_text() == "old"
    assert result.executed is False


def test_recursive_delete_requires_dir_name_not_yes(tmp_path):
    d = tmp_path / "important_data"
    d.mkdir()
    (d / "f.txt").write_text("x")
    log_path = str(tmp_path / "log.jsonl")

    result = agent_dispatch.dispatch(
        "delete_dir", str(d), input_func=lambda _: "yes", log_path=log_path
    )

    assert d.exists()
    assert result.executed is False


def test_recursive_delete_approved_with_dir_name(tmp_path):
    d = tmp_path / "important_data"
    d.mkdir()
    (d / "f.txt").write_text("x")
    log_path = str(tmp_path / "log.jsonl")

    result = agent_dispatch.dispatch(
        "delete_dir", str(d), input_func=lambda _: "important_data", log_path=log_path
    )

    assert not d.exists()
    assert result.executed is True


def test_move_overwrite_requires_confirmation(tmp_path):
    src = tmp_path / "src.txt"
    dest = tmp_path / "dest.txt"
    src.write_text("new")
    dest.write_text("old")
    log_path = str(tmp_path / "log.jsonl")

    result = agent_dispatch.dispatch(
        "move_overwrite", str(src), dest=str(dest), input_func=lambda _: "yes", log_path=log_path
    )

    assert not src.exists()
    assert dest.read_text() == "new"
    assert result.executed is True


def test_move_overwrite_declined_leaves_files_untouched(tmp_path):
    src = tmp_path / "src.txt"
    dest = tmp_path / "dest.txt"
    src.write_text("new")
    dest.write_text("old")
    log_path = str(tmp_path / "log.jsonl")

    result = agent_dispatch.dispatch(
        "move_overwrite", str(src), dest=str(dest), input_func=lambda _: "no", log_path=log_path
    )

    assert src.exists()
    assert dest.read_text() == "old"
    assert result.executed is False


def test_non_destructive_actions_never_prompt(tmp_path):
    p = tmp_path / "a.txt"
    log_path = str(tmp_path / "log.jsonl")

    def blow_up(_):
        raise AssertionError("prompt should not be called for non-destructive actions")

    result = agent_dispatch.dispatch(
        "create_file", str(p), content="hi", input_func=blow_up, log_path=log_path
    )
    assert p.read_text() == "hi"
    assert result.executed is True

    result = agent_dispatch.dispatch("read", str(p), input_func=blow_up, log_path=log_path)
    assert result.message == "hi"

    p2 = tmp_path / "b.txt"
    result = agent_dispatch.dispatch(
        "append", str(p2), content="x", input_func=blow_up, log_path=log_path
    )
    assert p2.read_text() == "x"


def test_declined_action_is_logged(tmp_path):
    p = tmp_path / "a.txt"
    p.write_text("data")
    log_path = str(tmp_path / "log.jsonl")

    agent_dispatch.dispatch("delete_file", str(p), input_func=lambda _: "no", log_path=log_path)

    with open(log_path) as f:
        entries = f.readlines()
    assert len(entries) == 1
    assert '"outcome": "declined"' in entries[0]


def test_approved_action_is_logged(tmp_path):
    p = tmp_path / "a.txt"
    p.write_text("data")
    log_path = str(tmp_path / "log.jsonl")

    agent_dispatch.dispatch("delete_file", str(p), input_func=lambda _: "yes", log_path=log_path)

    with open(log_path) as f:
        entries = f.readlines()
    assert len(entries) == 1
    assert '"outcome": "approved"' in entries[0]


def test_batch_shows_full_list_before_single_confirmation(tmp_path, capsys):
    a = tmp_path / "a.txt"
    b = tmp_path / "b.txt"
    a.write_text("1")
    b.write_text("2")
    log_path = str(tmp_path / "log.jsonl")

    call_count = {"n": 0}

    def count_input(_):
        call_count["n"] += 1
        return "yes"

    results = agent_dispatch.dispatch_batch(
        [
            {"action": "delete_file", "path": str(a)},
            {"action": "delete_file", "path": str(b)},
        ],
        input_func=count_input,
        log_path=log_path,
    )

    captured = capsys.readouterr()
    assert str(a) in captured.out
    assert str(b) in captured.out
    assert call_count["n"] == 1
    assert not a.exists()
    assert not b.exists()
    assert all(r.executed for r in results)


def test_batch_decline_leaves_all_files_untouched(tmp_path):
    a = tmp_path / "a.txt"
    b = tmp_path / "b.txt"
    a.write_text("1")
    b.write_text("2")
    log_path = str(tmp_path / "log.jsonl")

    results = agent_dispatch.dispatch_batch(
        [
            {"action": "delete_file", "path": str(a)},
            {"action": "delete_file", "path": str(b)},
        ],
        input_func=lambda _: "no",
        log_path=log_path,
    )

    assert a.exists()
    assert b.exists()
    assert all(not r.executed for r in results)
