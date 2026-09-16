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
file untouched. Recursive directory deletes ask for the directory's exact
name instead of `yes`.

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
