import json
import os
from agent import session_log


def test_log_event_appends_jsonl_entry(tmp_path):
    log_path = str(tmp_path / "session.jsonl")
    session_log.log_event("delete_file", "/tmp/a.txt", "approved", log_path=log_path)

    with open(log_path) as f:
        lines = f.readlines()
    assert len(lines) == 1
    entry = json.loads(lines[0])
    assert entry["action"] == "delete_file"
    assert entry["path"] == "/tmp/a.txt"
    assert entry["outcome"] == "approved"
    assert "timestamp" in entry


def test_log_event_appends_multiple_entries(tmp_path):
    log_path = str(tmp_path / "session.jsonl")
    session_log.log_event("read", "/tmp/a.txt", "n/a", log_path=log_path)
    session_log.log_event("overwrite", "/tmp/b.txt", "declined", log_path=log_path)

    with open(log_path) as f:
        lines = f.readlines()
    assert len(lines) == 2


def test_log_event_creates_parent_dir_if_missing(tmp_path):
    log_path = str(tmp_path / "nested" / "dir" / "session.jsonl")
    session_log.log_event("read", "/tmp/a.txt", "n/a", log_path=log_path)
    assert os.path.exists(log_path)
