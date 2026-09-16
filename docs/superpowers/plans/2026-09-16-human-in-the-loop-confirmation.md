# Human-in-the-Loop Confirmation for Destructive Actions — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a small file-editing agent, driven by Groq's chat-completions API with tool calling, where every destructive filesystem action (overwrite, delete file, recursive delete, move-over-existing) is intercepted in code and requires explicit human confirmation before it reaches the filesystem.

**Architecture:** A pure-function `file_tools` module does the actual filesystem work. A `confirmation` module classifies actions and builds/asks the confirmation prompt. A `session_log` module appends a JSONL audit trail. An `agent` module is the dispatch layer that every tool call — human-driven or LLM-driven — must go through; it is the single enforcement point (interception happens at the tool-call layer, not by asking the LLM nicely). A `runtime` module wires Groq's tool-calling loop to that dispatcher, so the LLM can only ever reach the filesystem through the confirmation gate.

**Tech Stack:** Python 3.11+, `groq` SDK (OpenAI-compatible tool calling), `python-dotenv`, `pytest`.

**Spec:** This plan implements the "Human-in-the-Loop Confirmation for Destructive Actions" feature spec provided in conversation (summary, goals, classification table, behavior spec, implementation notes, acceptance criteria, suggested file layout). No separate spec file exists on disk; this plan document carries the requirements forward.

## Global Constraints

- No destructive action (`overwrite`, `delete_file`, `delete_dir`, `move_overwrite`) may reach the filesystem without a confirmation step enforced in code (not just requested of the LLM).
- Non-destructive actions (`read`, `create_file` on a non-existing path, `append`) run with zero prompts.
- Accepted approval responses for a normal destructive action: `yes` or `y` (case-insensitive after stripping whitespace). Anything else — `no`, empty, unrelated text — is a decline.
- Recursive directory delete (`delete_dir`) additionally requires the user to type the directory's exact basename, not `yes`/`y`.
- Declining an action must leave the filesystem untouched and must not silently retry; the caller gets back a result saying it was skipped.
- Batch destructive operations show every item's full description before a single `yes` approves the whole shown batch.
- No `--force`/`--yes` bypass flag is implemented anywhere in this plan. If one is ever added later, the spec requires it be explicit, user-supplied, and logged — until then, the only path to approval is the `confirm()` gate.
- Every confirmation event (approved or declined) is logged with timestamp, action, path, and outcome to a JSONL session log.
- LLM credentials come from `.env` (`GROQ_API_KEY`, `GROQ_MODEL`) via `python-dotenv` — this project uses Groq, not Anthropic, for the agent's LLM calls.

---

## File Structure

```
agent/
  __init__.py
  tools/
    __init__.py
    file_tools.py       # pure filesystem operations, no confirmation logic
    confirmation.py      # is_destructive, describe_action, confirm, confirm_recursive_delete
  session_log.py          # JSONL audit log
  agent.py                # dispatch() / dispatch_batch() — the single enforcement point
  runtime.py               # Groq tool-calling loop, wired through agent.dispatch
tests/
  __init__.py
  test_file_tools.py
  test_confirmation.py
  test_session_log.py
  test_agent_dispatch.py
  test_runtime.py
  test_acceptance.py       # consolidated acceptance-criteria checklist
requirements.txt
README.md
.env                        # already present: GROQ_API_KEY, GROQ_MODEL
```

`agent.py` is the tool-dispatch layer named in the spec's suggested layout. The LLM loop is split into its own `runtime.py` rather than crammed into `agent.py`, since dispatch (enforcement) and the LLM conversation loop (a client of that enforcement) are different responsibilities that should be able to change independently — dispatch must stay correct even if the LLM provider changes later.

---

### Task 1: Filesystem tools (`file_tools.py`)

**Files:**
- Create: `agent/__init__.py` (empty)
- Create: `agent/tools/__init__.py` (empty)
- Create: `agent/tools/file_tools.py`
- Create: `tests/__init__.py` (empty)
- Create: `tests/test_file_tools.py`
- Create: `requirements.txt`

**Interfaces:**
- Produces: `read_file(path: str) -> str`, `create_file(path: str, content: str) -> None` (raises `FileExistsError` if path exists), `append_file(path: str, content: str) -> None`, `overwrite_file(path: str, content: str) -> None` (raises `FileNotFoundError` if path missing), `delete_file(path: str) -> None` (raises `FileNotFoundError` if missing), `delete_dir(path: str) -> None` (raises `NotADirectoryError` if missing), `move_file(src: str, dest: str) -> None` (raises `FileNotFoundError` if src missing).

- [ ] **Step 1: Create `requirements.txt`**

```
groq>=0.9.0
python-dotenv>=1.0.0
pytest>=8.0.0
```

- [ ] **Step 2: Create package init files**

`agent/__init__.py` — empty file.
`agent/tools/__init__.py` — empty file.
`tests/__init__.py` — empty file.

- [ ] **Step 3: Write the failing tests**

`tests/test_file_tools.py`:

```python
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
```

- [ ] **Step 4: Run tests to verify they fail**

Run: `python -m pytest tests/test_file_tools.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'agent.tools.file_tools'`

- [ ] **Step 5: Implement `agent/tools/file_tools.py`**

```python
import os
import shutil


def read_file(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def create_file(path: str, content: str) -> None:
    if os.path.exists(path):
        raise FileExistsError(f"File already exists: {path}")
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


def append_file(path: str, content: str) -> None:
    with open(path, "a", encoding="utf-8") as f:
        f.write(content)


def overwrite_file(path: str, content: str) -> None:
    if not os.path.exists(path):
        raise FileNotFoundError(f"File does not exist: {path}")
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


def delete_file(path: str) -> None:
    if not os.path.isfile(path):
        raise FileNotFoundError(f"File does not exist: {path}")
    os.remove(path)


def delete_dir(path: str) -> None:
    if not os.path.isdir(path):
        raise NotADirectoryError(f"Directory does not exist: {path}")
    shutil.rmtree(path)


def move_file(src: str, dest: str) -> None:
    if not os.path.exists(src):
        raise FileNotFoundError(f"Source does not exist: {src}")
    shutil.move(src, dest)
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `python -m pytest tests/test_file_tools.py -v`
Expected: PASS (13 tests)

- [ ] **Step 7: Commit**

```bash
git add requirements.txt agent/__init__.py agent/tools/__init__.py agent/tools/file_tools.py tests/__init__.py tests/test_file_tools.py
git commit -m "feat: add pure filesystem tool functions"
```

---

### Task 2: Confirmation gate (`confirmation.py`)

**Files:**
- Create: `agent/tools/confirmation.py`
- Create: `tests/test_confirmation.py`

**Interfaces:**
- Consumes: nothing from Task 1 (file-existence checks use `os` directly on paths the caller already knows are valid).
- Produces: `is_destructive(action: str) -> bool`, `describe_action(action: str, path: str, content: str = None, dest: str = None) -> str`, `confirm(prompt: str, input_func=input) -> bool`, `confirm_recursive_delete(prompt: str, dir_name: str, input_func=input) -> bool`. `DESTRUCTIVE_ACTIONS = {"overwrite", "delete_file", "delete_dir", "move_overwrite"}`.

- [ ] **Step 1: Write the failing tests**

`tests/test_confirmation.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_confirmation.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'agent.tools.confirmation'`

- [ ] **Step 3: Implement `agent/tools/confirmation.py`**

```python
import difflib
import os
from datetime import datetime

DESTRUCTIVE_ACTIONS = {"overwrite", "delete_file", "delete_dir", "move_overwrite"}


def is_destructive(action: str) -> bool:
    return action in DESTRUCTIVE_ACTIONS


def _file_summary(path: str) -> str:
    size = os.path.getsize(path)
    mtime = datetime.fromtimestamp(os.path.getmtime(path)).strftime("%Y-%m-%d %H:%M:%S")
    return f"{size} bytes, last modified {mtime}"


def _diff_summary(path: str, new_content: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        old_lines = f.readlines()
    new_lines = new_content.splitlines(keepends=True)
    diff = list(difflib.unified_diff(old_lines, new_lines, lineterm=""))
    added = sum(1 for l in diff if l.startswith("+") and not l.startswith("+++"))
    removed = sum(1 for l in diff if l.startswith("-") and not l.startswith("---"))
    return f"will replace {removed} lines with {added} lines"


def describe_action(action: str, path: str, content: str = None, dest: str = None) -> str:
    if action == "overwrite":
        return (
            f"Action: OVERWRITE\nTarget: {path}\n"
            f"Change: {_diff_summary(path, content)}\n"
            f"Reversible: No"
        )
    if action == "delete_file":
        return (
            f"Action: DELETE FILE\nTarget: {path}\n"
            f"Change: will remove file, {_file_summary(path)}\n"
            f"Reversible: No"
        )
    if action == "delete_dir":
        file_count = sum(len(files) for _, _, files in os.walk(path))
        return (
            f"Action: RECURSIVE DELETE DIRECTORY\nTarget: {path}\n"
            f"Change: will remove directory and all contents ({file_count} files)\n"
            f"Reversible: No\nWARNING: this is a large-blast-radius operation."
        )
    if action == "move_overwrite":
        return (
            f"Action: MOVE/RENAME (OVERWRITE)\nTarget: {dest} (overwritten by {path})\n"
            f"Change: existing file at {dest}, {_file_summary(dest)}, will be replaced\n"
            f"Reversible: No"
        )
    raise ValueError(f"Unknown destructive action: {action}")


def confirm(prompt: str, input_func=input) -> bool:
    print(prompt)
    response = input_func("Type 'yes' to proceed: ")
    return response.strip().lower() in ("y", "yes")


def confirm_recursive_delete(prompt: str, dir_name: str, input_func=input) -> bool:
    print(prompt)
    response = input_func(f"Type the directory name '{dir_name}' to confirm: ")
    return response.strip() == dir_name
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_confirmation.py -v`
Expected: PASS (12 tests)

- [ ] **Step 5: Commit**

```bash
git add agent/tools/confirmation.py tests/test_confirmation.py
git commit -m "feat: add destructive-action classification and confirmation prompts"
```

---

### Task 3: Session audit log (`session_log.py`)

**Files:**
- Create: `agent/session_log.py`
- Create: `tests/test_session_log.py`

**Interfaces:**
- Produces: `DEFAULT_LOG_PATH: str`, `log_event(action: str, path: str, outcome: str, log_path: str = DEFAULT_LOG_PATH) -> None`.

- [ ] **Step 1: Write the failing tests**

`tests/test_session_log.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_session_log.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'agent.session_log'`

- [ ] **Step 3: Implement `agent/session_log.py`**

```python
import json
import os
from datetime import datetime

DEFAULT_LOG_PATH = os.path.join("agent", "logs", "session_log.jsonl")


def log_event(action: str, path: str, outcome: str, log_path: str = DEFAULT_LOG_PATH) -> None:
    parent = os.path.dirname(log_path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    entry = {
        "timestamp": datetime.now().isoformat(),
        "action": action,
        "path": path,
        "outcome": outcome,
    }
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_session_log.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add agent/session_log.py tests/test_session_log.py
git commit -m "feat: add JSONL session audit log"
```

---

### Task 4: Dispatch layer — the enforcement point (`agent.py`)

**Files:**
- Create: `agent/agent.py`
- Create: `tests/test_agent_dispatch.py`

**Interfaces:**
- Consumes: `file_tools.{read_file,create_file,append_file,overwrite_file,delete_file,delete_dir,move_file}` (Task 1); `confirmation.{is_destructive,describe_action,confirm,confirm_recursive_delete}` (Task 2); `session_log.{log_event,DEFAULT_LOG_PATH}` (Task 3).
- Produces: `class DispatchResult: executed: bool, message: str`; `dispatch(action: str, path: str, content: str = None, dest: str = None, input_func=input, log_path: str = DEFAULT_LOG_PATH) -> DispatchResult`; `dispatch_batch(actions: list[dict], input_func=input, log_path: str = DEFAULT_LOG_PATH) -> list[DispatchResult]` where each item in `actions` is `{"action": str, "path": str, "content": str (optional), "dest": str (optional)}`.

- [ ] **Step 1: Write the failing tests**

`tests/test_agent_dispatch.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_agent_dispatch.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'agent.agent'`

- [ ] **Step 3: Implement `agent/agent.py`**

```python
import os

from agent.tools import file_tools
from agent.tools.confirmation import (
    is_destructive,
    describe_action,
    confirm,
    confirm_recursive_delete,
)
from agent.session_log import log_event, DEFAULT_LOG_PATH


class DispatchResult:
    def __init__(self, executed: bool, message: str):
        self.executed = executed
        self.message = message


def _execute(action, path, content, dest):
    if action == "read":
        return file_tools.read_file(path)
    if action == "create_file":
        file_tools.create_file(path, content)
        return f"Created {path}"
    if action == "append":
        file_tools.append_file(path, content)
        return f"Appended to {path}"
    if action == "overwrite":
        file_tools.overwrite_file(path, content)
        return f"Overwrote {path}"
    if action == "delete_file":
        file_tools.delete_file(path)
        return f"Deleted {path}"
    if action == "delete_dir":
        file_tools.delete_dir(path)
        return f"Deleted directory {path}"
    if action == "move_overwrite":
        file_tools.move_file(path, dest)
        return f"Moved {path} to {dest}"
    raise ValueError(f"Unknown action: {action}")


def dispatch(
    action, path, content=None, dest=None, input_func=input, log_path=DEFAULT_LOG_PATH
) -> DispatchResult:
    if not is_destructive(action):
        message = _execute(action, path, content, dest)
        return DispatchResult(True, message)

    prompt = describe_action(action, path, content=content, dest=dest)

    if action == "delete_dir":
        dir_name = os.path.basename(os.path.normpath(path))
        approved = confirm_recursive_delete(prompt, dir_name, input_func=input_func)
    else:
        approved = confirm(prompt, input_func=input_func)

    if not approved:
        log_event(action, path, "declined", log_path=log_path)
        return DispatchResult(
            False, f"Skipped: {action} on {path} was declined. What would you like to do instead?"
        )

    message = _execute(action, path, content, dest)
    log_event(action, path, "approved", log_path=log_path)
    return DispatchResult(True, message)


def dispatch_batch(actions, input_func=input, log_path=DEFAULT_LOG_PATH):
    destructive = [a for a in actions if is_destructive(a["action"])]
    non_destructive = [a for a in actions if not is_destructive(a["action"])]

    results = []
    for a in non_destructive:
        results.append(
            dispatch(
                a["action"],
                a["path"],
                a.get("content"),
                a.get("dest"),
                input_func=input_func,
                log_path=log_path,
            )
        )

    if not destructive:
        return results

    prompts = [
        describe_action(a["action"], a["path"], content=a.get("content"), dest=a.get("dest"))
        for a in destructive
    ]
    full_prompt = "\n\n".join(prompts)
    approved = confirm(full_prompt, input_func=input_func)

    for a in destructive:
        if not approved:
            log_event(a["action"], a["path"], "declined", log_path=log_path)
            results.append(
                DispatchResult(False, f"Skipped: {a['action']} on {a['path']} was declined.")
            )
            continue
        message = _execute(a["action"], a["path"], a.get("content"), a.get("dest"))
        log_event(a["action"], a["path"], "approved", log_path=log_path)
        results.append(DispatchResult(True, message))

    return results
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_agent_dispatch.py -v`
Expected: PASS (13 tests)

- [ ] **Step 5: Commit**

```bash
git add agent/agent.py tests/test_agent_dispatch.py
git commit -m "feat: add dispatch layer enforcing confirmation for destructive actions"
```

---

### Task 5: Groq tool-calling loop (`runtime.py`)

**Files:**
- Create: `agent/runtime.py`
- Create: `tests/test_runtime.py`

**Interfaces:**
- Consumes: `agent.agent.dispatch` (Task 4).
- Produces: `TOOLS: list[dict]` (Groq/OpenAI-style tool schemas), `execute_tool_call(tool_call, input_func=input) -> str`, `run_agent_loop(user_message: str, system_prompt: str = ..., input_func=input) -> str`, module-level `client` (a `groq.Groq` instance) and `MODEL` (str), both overridable/monkeypatchable for tests.

- [ ] **Step 1: Write the failing tests**

`tests/test_runtime.py`:

```python
import json
from types import SimpleNamespace

from agent import runtime


def _fake_tool_call(name, arguments, call_id="call_1"):
    return SimpleNamespace(
        id=call_id,
        function=SimpleNamespace(name=name, arguments=json.dumps(arguments)),
    )


def test_execute_tool_call_delete_file_requires_confirmation(tmp_path):
    p = tmp_path / "a.txt"
    p.write_text("data")
    tool_call = _fake_tool_call("delete_file", {"path": str(p)})

    message = runtime.execute_tool_call(tool_call, input_func=lambda _: "no")

    assert p.exists()
    assert "skip" in message.lower() or "declined" in message.lower()


def test_execute_tool_call_read_file_no_confirmation(tmp_path):
    p = tmp_path / "a.txt"
    p.write_text("hello")
    tool_call = _fake_tool_call("read_file", {"path": str(p)})

    def blow_up(_):
        raise AssertionError("read should not prompt")

    message = runtime.execute_tool_call(tool_call, input_func=blow_up)
    assert message == "hello"


def test_execute_tool_call_delete_file_approved_removes_file(tmp_path):
    p = tmp_path / "a.txt"
    p.write_text("data")
    tool_call = _fake_tool_call("delete_file", {"path": str(p)})

    runtime.execute_tool_call(tool_call, input_func=lambda _: "yes")
    assert not p.exists()


def test_run_agent_loop_executes_tool_then_returns_final_message(tmp_path, monkeypatch):
    p = tmp_path / "a.txt"
    p.write_text("hi")

    tool_call = _fake_tool_call("read_file", {"path": str(p)})
    first_response = SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(content=None, tool_calls=[tool_call], role="assistant")
            )
        ]
    )
    second_response = SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(
                    content="The file contains: hi", tool_calls=None, role="assistant"
                )
            )
        ]
    )
    responses = [first_response, second_response]

    class FakeCompletions:
        def create(self, **kwargs):
            return responses.pop(0)

    class FakeChat:
        completions = FakeCompletions()

    monkeypatch.setattr(runtime, "client", SimpleNamespace(chat=FakeChat()))

    result = runtime.run_agent_loop(f"read {p}", input_func=lambda _: "yes")
    assert result == "The file contains: hi"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_runtime.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'agent.runtime'`

- [ ] **Step 3: Implement `agent/runtime.py`**

```python
import json
import os

from dotenv import load_dotenv
from groq import Groq

from agent.agent import dispatch

load_dotenv()

client = Groq(api_key=os.environ["GROQ_API_KEY"])
MODEL = os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile")

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read the contents of a file.",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_file",
            "description": "Create a new file. Fails if the file already exists.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "content": {"type": "string"},
                },
                "required": ["path", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "append_file",
            "description": "Append content to an existing or new file.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "content": {"type": "string"},
                },
                "required": ["path", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "overwrite_file",
            "description": "Overwrite an existing file's contents. Destructive and irreversible; requires human confirmation.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "content": {"type": "string"},
                },
                "required": ["path", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "delete_file",
            "description": "Delete a file. Destructive and irreversible; requires human confirmation.",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "delete_dir",
            "description": "Recursively delete a directory. Destructive and irreversible; requires typing the directory name to confirm.",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "move_overwrite",
            "description": "Move/rename a file over an existing file at the destination. Destructive and irreversible; requires human confirmation.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "dest": {"type": "string"},
                },
                "required": ["path", "dest"],
            },
        },
    },
]

ACTION_NAME_MAP = {
    "read_file": "read",
    "create_file": "create_file",
    "append_file": "append",
    "overwrite_file": "overwrite",
    "delete_file": "delete_file",
    "delete_dir": "delete_dir",
    "move_overwrite": "move_overwrite",
}


def execute_tool_call(tool_call, input_func=input) -> str:
    name = tool_call.function.name
    args = json.loads(tool_call.function.arguments)
    action = ACTION_NAME_MAP[name]
    result = dispatch(
        action,
        args["path"],
        content=args.get("content"),
        dest=args.get("dest"),
        input_func=input_func,
    )
    return result.message


def run_agent_loop(
    user_message: str,
    system_prompt: str = "You are a careful file-editing assistant.",
    input_func=input,
) -> str:
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message},
    ]
    while True:
        response = client.chat.completions.create(
            model=MODEL,
            messages=messages,
            tools=TOOLS,
        )
        message = response.choices[0].message
        messages.append(message)

        if not message.tool_calls:
            return message.content

        for tool_call in message.tool_calls:
            output = execute_tool_call(tool_call, input_func=input_func)
            messages.append(
                {"role": "tool", "tool_call_id": tool_call.id, "content": output}
            )


if __name__ == "__main__":
    import sys

    user_input = " ".join(sys.argv[1:]) or "List what you can do."
    print(run_agent_loop(user_input))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_runtime.py -v`
Expected: PASS (4 tests)

Note: `client = Groq(api_key=os.environ["GROQ_API_KEY"])` runs at import time, so `.env` must contain `GROQ_API_KEY` before running any test that imports `agent.runtime` — it already does. This only constructs the client (no network call); network calls happen in `client.chat.completions.create`, which the tests monkeypatch.

- [ ] **Step 5: Commit**

```bash
git add agent/runtime.py tests/test_runtime.py
git commit -m "feat: wire Groq tool-calling loop through the confirmation-gated dispatcher"
```

---

### Task 6: Acceptance checklist, README

**Files:**
- Create: `tests/test_acceptance.py`
- Create: `README.md`

**Interfaces:**
- Consumes: `agent.agent.dispatch`, `agent.session_log.log_event` (read-back), all from prior tasks. No new production code.

- [ ] **Step 1: Write the acceptance test file**

`tests/test_acceptance.py` — one test per line item in the spec's Acceptance Criteria:

```python
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
```

- [ ] **Step 2: Run the full test suite**

Run: `python -m pytest tests/ -v`
Expected: PASS (all tests across Tasks 1–6)

- [ ] **Step 3: Write `README.md`**

```markdown
# Human-in-the-Loop File Agent

A file-editing agent whose LLM brain runs on Groq, wired so that every
destructive filesystem action — overwrite, delete file, recursive directory
delete, move-over-existing — is intercepted in code and requires explicit
human confirmation before it touches disk. The interception happens in the
dispatch layer (`agent/agent.py`), not as an instruction to the LLM, so it
cannot be reasoned around, retried past, or skipped by a bad plan step.

## Setup

```bash
pip install -r requirements.txt
```

`.env` must contain:

```
GROQ_API_KEY=...
GROQ_MODEL=...
```

## Run

```bash
python -m agent.runtime "read the file notes.txt"
```

Destructive requests will pause and print a prompt like:

```
Action: DELETE FILE
Target: notes.txt
Change: will remove file, 512 bytes, last modified 2026-09-10 14:02:00
Reversible: No
Type 'yes' to proceed:
```

Typing anything other than `yes`/`y` declines the action and leaves the
file untouched.

## Layout

- `agent/tools/file_tools.py` — pure filesystem operations.
- `agent/tools/confirmation.py` — classifies actions and builds/asks prompts.
- `agent/session_log.py` — JSONL audit trail of every confirmation event.
- `agent/agent.py` — `dispatch()`/`dispatch_batch()`, the single enforcement
  point every tool call (human or LLM) must go through.
- `agent/runtime.py` — Groq tool-calling loop, routes every tool call through
  `agent.dispatch()`.

## Tests

```bash
python -m pytest tests/ -v
```
```

- [ ] **Step 4: Commit**

```bash
git add tests/test_acceptance.py README.md
git commit -m "test: add spec acceptance checklist and document usage"
```
