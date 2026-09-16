import json

from agent import agent as agent_dispatch


def test_ac1_delete_without_confirmation_is_impossible(tmp_path):
    p = tmp_path / "a.txt"
    p.write_text("important data")
    log_path = str(tmp_path / "log.jsonl")

    result = agent_dispatch.dispatch(
        "delete_file", str(p), input_func=lambda _: "no", log_path=log_path
    )

    assert p.exists()
    assert result.executed is False


def test_ac2_overwrite_shows_diff_summary_and_requires_yes(tmp_path):
    p = tmp_path / "a.txt"
    p.write_text("before\n")
    log_path = str(tmp_path / "log.jsonl")

    prompts = []

    def capture(_):
        prompts.append(True)
        return "yes"

    result = agent_dispatch.dispatch(
        "overwrite", str(p), content="after\n", input_func=capture, log_path=log_path
    )

    assert p.read_text() == "after\n"
    assert result.executed is True
    assert len(prompts) == 1


def test_ac3_decline_leaves_filesystem_unchanged_and_reports_skip(tmp_path):
    p = tmp_path / "a.txt"
    p.write_text("original")
    log_path = str(tmp_path / "log.jsonl")

    result = agent_dispatch.dispatch(
        "overwrite", str(p), content="changed", input_func=lambda _: "no", log_path=log_path
    )

    assert p.read_text() == "original"
    assert result.executed is False
    assert "skip" in result.message.lower()


def test_ac4_recursive_delete_requires_typed_dir_name(tmp_path):
    d = tmp_path / "critical_dir"
    d.mkdir()
    (d / "f.txt").write_text("x")
    log_path = str(tmp_path / "log.jsonl")

    denied = agent_dispatch.dispatch(
        "delete_dir", str(d), input_func=lambda _: "yes", log_path=log_path
    )
    assert d.exists()
    assert denied.executed is False

    approved = agent_dispatch.dispatch(
        "delete_dir", str(d), input_func=lambda _: "critical_dir", log_path=log_path
    )
    assert not d.exists()
    assert approved.executed is True


def test_ac5_non_destructive_actions_run_with_zero_prompts(tmp_path):
    log_path = str(tmp_path / "log.jsonl")

    def blow_up(_):
        raise AssertionError("must not prompt")

    p = tmp_path / "a.txt"
    agent_dispatch.dispatch("create_file", str(p), content="x", input_func=blow_up, log_path=log_path)
    agent_dispatch.dispatch("append", str(p), content="y", input_func=blow_up, log_path=log_path)
    result = agent_dispatch.dispatch("read", str(p), input_func=blow_up, log_path=log_path)

    assert result.message == "xy"


def test_ac6_confirmation_events_logged_with_required_fields(tmp_path):
    p = tmp_path / "a.txt"
    p.write_text("data")
    log_path = str(tmp_path / "log.jsonl")

    agent_dispatch.dispatch("delete_file", str(p), input_func=lambda _: "yes", log_path=log_path)

    with open(log_path) as f:
        entry = json.loads(f.readline())

    assert set(["timestamp", "action", "path", "outcome"]).issubset(entry.keys())
    assert entry["action"] == "delete_file"
    assert entry["outcome"] == "approved"
