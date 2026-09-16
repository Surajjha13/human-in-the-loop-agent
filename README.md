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

## How it works

```
user prompt
   │
   ▼
agent/runtime.py  ──calls──▶  Groq chat.completions (tool calling)
   │                                   │
   │                          returns a tool_call
   ▼                                   │
execute_tool_call() ◀──────────────────┘
   │  maps tool name → action, forwards to dispatch()
   ▼
agent/agent.py: dispatch()
   │  is_destructive(action)?
   ├─ No  → run the file_tools function directly, return result
   └─ Yes → describe_action() builds a human-readable prompt
            confirm() / confirm_recursive_delete() blocks for input
            approved → run file_tools function, log "approved"
            declined → skip, log "declined", report back to caller
```

The LLM never touches the filesystem directly — it can only ask for a tool
call, and every tool call is forced through `dispatch()`. See
[`UNDERSTAND.md`](./UNDERSTAND.md) for the full design rationale, a
line-by-line walkthrough, and interview-style Q&A about the architecture.

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
