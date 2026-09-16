# UNDERSTAND.md

Everything you need to know to explain this project confidently — how it
works, why it's built this way, and how to answer questions about it in an
interview.

---

## 1. What this is, in one paragraph

A small file-editing agent. An LLM (Groq, tool-calling) decides *what* to
do with files; a code-level gate decides *whether it's allowed to actually
happen*. Every destructive filesystem action — overwrite, delete a file,
recursively delete a directory, or move a file over an existing one —
must pass through a single choke point (`dispatch()`) that blocks and asks
a human before the real filesystem call runs. Non-destructive actions
(read, create-new, append) skip the gate entirely and run immediately.

The core idea worth remembering: **the safety mechanism is enforced in
code, not requested from the model.** The LLM is treated as untrusted
input. It can ask for anything; it cannot make anything destructive
happen without a human typing `yes`.

---

## 2. Architecture

```
agent/tools/file_tools.py     pure filesystem operations (no policy, no prompts)
agent/tools/confirmation.py   classifies actions, builds prompts, blocks for input
agent/session_log.py          append-only JSONL audit trail
agent/agent.py                dispatch() / dispatch_batch() — the ONE enforcement point
agent/runtime.py              Groq tool-calling loop, calls dispatch() for every tool call
```

Each layer has exactly one job:

| Layer | Job | Knows about policy? | Knows about the LLM? |
|---|---|---|---|
| `file_tools` | Do the filesystem operation | No | No |
| `confirmation` | Decide if an action is destructive; build/ask the prompt | Yes | No |
| `session_log` | Append an audit record | No | No |
| `agent.dispatch` | Wire the above together; the mandatory checkpoint | Yes | No |
| `runtime` | Talk to Groq, translate tool calls into `dispatch()` calls | No | Yes |

Nothing above `agent.dispatch` is allowed to call `file_tools` directly.
That's the whole security property of this codebase in one sentence: **there
is exactly one path from "someone wants to touch a file" to "the file gets
touched," and that path runs through the confirmation gate.**

### Request lifecycle (destructive case)

1. User asks `runtime.run_agent_loop("delete notes.txt")`.
2. Groq responds with a `tool_call` for `delete_file`, not with output text.
3. `execute_tool_call()` looks up `delete_file` in `ACTION_NAME_MAP` → internal
   action name `"delete_file"`, then calls `agent.dispatch("delete_file", path, input_func=...)`.
4. `dispatch()` checks `is_destructive("delete_file")` → `True`.
5. `describe_action()` builds a plain-text prompt: action, target, size/mtime,
   "Reversible: No".
6. `confirm(prompt, input_func)` prints the prompt and blocks on `input_func`
   (in production, real `input()`; in tests, an injected fake).
7. If declined: `log_event(..., "declined")`, return a `DispatchResult(False, ...)`
   — the file is never touched, and `dispatch()` never calls `file_tools`.
8. If approved: `file_tools.delete_file(path)` actually runs, then
   `log_event(..., "approved")`.
9. The `DispatchResult.message` goes back into the conversation as a `tool`
   role message, and the LLM continues (e.g. to tell the user what happened).

### Request lifecycle (non-destructive case)

`is_destructive()` returns `False` → `dispatch()` calls `_execute()` immediately.
No prompt, no log gate, no blocking. This is what keeps `read`/`create_file`/`append`
fast and silent, per the spec's requirement that safe actions never prompt.

---

## 3. Key design decisions, and why

**Enforcement lives in `dispatch()`, not in a system prompt telling the LLM
to ask first.**
LLM instructions are advisory — a prompt injection, a weird edge case, or
just model non-determinism can make the model "forget" to ask. A prompt is
not a security boundary. The gate has to live in code that runs
unconditionally between "tool call requested" and "filesystem touched," so
it can't be reasoned around. This is the same principle as a *reference
monitor* in OS security: every access request is mediated by one component
that cannot be bypassed.

**`is_destructive()` is an explicit allow-list (`DESTRUCTIVE_ACTIONS` set),
not an inferred property.**
Fail-closed by construction: a new action added later defaults to *not*
matching the set, so if someone forgets to classify it, `describe_action()`
would never even be reached for it via the destructive path — but more
importantly, the set is a single place you can audit by eye to answer "what
requires confirmation here?" without reading every function body.

**`confirm()` and `run_agent_loop()` take an `input_func`/`client` parameter
instead of hard-wiring `input()` / a module-level Groq client call.**
This is dependency injection for testability. Two things in this codebase
are normally painful to unit test: something that blocks on stdin, and
something that calls a paid external API. Both are solved the same way —
accept the dependency as a parameter with a real default, and tests pass a
fake. This avoids monkeypatching global builtins (`input`), which gets
fragile fast (global mutable state, order-dependent tests, thread-unsafety).
The Groq `client` is still a module-level object so production code doesn't
have to thread it through every call, but tests `monkeypatch.setattr(runtime, "client", fake)`
to swap it out safely per-test.

**Declining returns a `DispatchResult(False, message)` instead of raising
an exception.**
A decline is an expected, common outcome — not an error condition. Using
a return value keeps the caller (`runtime.execute_tool_call`) simple: it
always gets a string back to hand to the LLM, whether the action ran or not.
Exceptions are reserved for genuinely exceptional states (`FileNotFoundError`
from `file_tools` when the target doesn't exist at all).

**Batch operations show every item, then take one `yes` for the whole list.**
This is what the spec asked for — full transparency (nothing is hidden in a
batch), but one confirmation, not N. `dispatch_batch()` builds the full
`describe_action()` output for every destructive item, joins them, and calls
`confirm()` once on the combined text. Non-destructive items in the same
batch still run immediately, un-gated.

**Recursive directory delete requires typing the directory's exact name, not
`yes`.**
A single keystroke (`y`, Enter) is too cheap an action to gate the largest
blast-radius operation in the system. Typing the name forces the user to
actually read which directory they're about to lose.

**The audit log is JSONL (one JSON object per line), append-only.**
Append-only means a crash mid-write can't corrupt earlier entries (unlike a
single JSON array, which requires reading and rewriting the whole file on
every append). JSONL is trivially greppable/streamable and is the standard
shape for audit/event logs.

**`runtime.py` is a separate module from `agent.py`, even though the spec's
suggested layout put "the agent" in one file.**
`agent.py` is pure enforcement logic with zero LLM/network dependencies —
it can be imported and unit tested with nothing but the standard library.
`runtime.py` is a *client* of that enforcement layer that happens to be
LLM-driven. Splitting them means the confirmation gate's correctness doesn't
depend on Groq being reachable, and the LLM wiring can change (different
provider, different tool schema) without touching the safety-critical code.

---

## 4. Function reference

| Module | Function | Signature | Notes |
|---|---|---|---|
| `file_tools` | `read_file` | `(path) -> str` | |
| | `create_file` | `(path, content) -> None` | raises `FileExistsError` if path exists |
| | `append_file` | `(path, content) -> None` | creates file if missing |
| | `overwrite_file` | `(path, content) -> None` | raises `FileNotFoundError` if missing |
| | `delete_file` | `(path) -> None` | raises `FileNotFoundError` if missing |
| | `delete_dir` | `(path) -> None` | raises `NotADirectoryError` if missing; recursive |
| | `move_file` | `(src, dest) -> None` | raises `FileNotFoundError` if src missing |
| `confirmation` | `is_destructive` | `(action) -> bool` | membership test against `DESTRUCTIVE_ACTIONS` |
| | `describe_action` | `(action, path, content=None, dest=None) -> str` | builds the human-readable prompt |
| | `confirm` | `(prompt, input_func=input) -> bool` | `True` only for `yes`/`y` (case-insensitive) |
| | `confirm_recursive_delete` | `(prompt, dir_name, input_func=input) -> bool` | `True` only for exact `dir_name` match |
| `session_log` | `log_event` | `(action, path, outcome, log_path=DEFAULT_LOG_PATH) -> None` | appends one JSON line |
| `agent` | `dispatch` | `(action, path, content=None, dest=None, input_func=input, log_path=...) -> DispatchResult` | the enforcement point |
| | `dispatch_batch` | `(actions: list[dict], input_func=input, log_path=...) -> list[DispatchResult]` | one confirm for all destructive items |
| `runtime` | `execute_tool_call` | `(tool_call, input_func=input) -> str` | translates a Groq tool call into a `dispatch()` call |
| | `run_agent_loop` | `(user_message, system_prompt=..., input_func=input) -> str` | the Groq conversation loop |

---

## 5. Testing strategy

52 tests, all offline and filesystem-isolated:

- **Filesystem isolation:** every test uses pytest's `tmp_path` fixture — a
  fresh temp directory per test, auto-cleaned. No test touches a real
  project file.
- **No real stdin:** `input_func` is injected everywhere confirmation is
  needed. Tests pass lambdas (`lambda _: "yes"`) or counting/asserting
  functions (e.g. one test asserts `input_func` is *never* called for
  non-destructive actions, by passing a function that raises if invoked).
- **No real LLM calls:** `test_runtime.py` builds fake Groq response objects
  with `types.SimpleNamespace`, matching the exact attribute shape the SDK
  returns (`response.choices[0].message.tool_calls[i].function.name/arguments`),
  and monkeypatches `runtime.client` with a fake object exposing
  `.chat.completions.create()`. This tests the *loop logic* (does a tool
  call get executed, does the loop terminate on a plain text response)
  without spending API credits or depending on network availability.
- **Acceptance tests** (`test_acceptance.py`) map 1:1 to the original spec's
  acceptance criteria checklist, so "does this satisfy the spec" is a single
  `pytest tests/test_acceptance.py` run away from being answered.

---

## 6. Known limitations / explicitly out of scope

These were deliberate non-goals, not oversights:

- **No undo/backup.** Declining is the only safety net; there's no snapshot
  of overwritten/deleted content. (Spec's non-goals list this explicitly.)
- **No `--force` bypass flag exists at all**, in either direction — there
  was nothing to gate, so nothing was built. If one is ever added, the spec
  requires it be explicit, user-supplied, and logged.
- **Only file actions are gated.** Network calls, external API calls, etc.
  are out of scope per the spec.
- **No GUI.** Confirmation is a blocking stdin prompt.
- **TOCTOU (time-of-check-to-time-of-use):** `describe_action()` reads file
  size/mtime, then later `_execute()` acts on the same path — if another
  process modifies the file in between, the description shown to the user
  could be stale. Not addressed; would need a lock or an atomic
  read-then-act primitive to fully close.
- **Log file isn't locked.** Concurrent writers to the same `log_path` could
  interleave partial writes. `dispatch()` itself is stateless/reentrant;
  only the shared log file has this gap.
- **`yes`/`y` matching is case-insensitive but not fuzzy** — `"Yes please"` is
  a decline, by design (spec: "anything else ... is treated as a decline").

---

## 7. Interview-style Q&A

**Q: Why intercept at the tool-dispatch layer instead of just prompting the
LLM to ask permission first?**
Because a system prompt is a request, not a control. Models are
non-deterministic and can be steered off a stated policy by adversarial or
even just unusual input (prompt injection, a long context burying the
instruction, model drift). If "ask first" lives only in the prompt, there's
no code path that actually blocks the destructive call — the LLM could, in
principle, emit the tool call and have it executed directly. Putting the
check in `dispatch()` means the gate exists whether or not the LLM
"remembers" to be careful; the LLM's only power is to *request* an action,
never to *perform* one.

**Q: How does this design stop a malicious or confused tool call from
reaching the filesystem?**
Two structural facts, not policy: (1) `runtime.execute_tool_call` maps tool
names through a fixed `ACTION_NAME_MAP` — a tool call for a name not in that
map raises `KeyError` rather than doing anything; (2) even a mapped action
always goes through `dispatch()`, which checks `is_destructive()` before any
`file_tools` call. There is no code path anywhere that lets a `tool_call`
reach `file_tools` directly.

**Q: What's a concrete TOCTOU risk here, and how would you close it?**
`describe_action()` calls `os.path.getsize`/`os.path.getmtime` to build the
prompt; then, after the user answers, `_execute()` operates on the same
path. Between those two steps, an external process could replace or delete
the file, so the size/mtime the user approved might not match what actually
gets deleted or overwritten. Closing it fully would mean opening a file
handle or acquiring a lock at description time and holding it through
execution — not implemented here, since it's a low-probability race for a
single-user CLI tool, but worth naming as the honest gap.

**Q: How did you unit test something that blocks on `input()`?**
Dependency injection: `confirm(prompt, input_func=input)` defaults to the
real `input` but accepts an override. Tests pass a lambda. This is
preferable to monkeypatching `builtins.input` globally because it's
per-call, doesn't leak between tests, and makes the test's intent visible
at the call site instead of hidden in fixture setup.

**Q: How did you test the LLM loop without calling the real API?**
By faking the shape of the Groq SDK's response object with
`types.SimpleNamespace` and monkeypatching the module-level `client`
attribute. The test never crosses a network boundary; it verifies that
`run_agent_loop` correctly drives the loop — call the model, if it returns
tool calls execute them and append `tool` messages, if it returns plain
content stop and return it — independent of what a real model would decide
to do.

**Q: Why JSONL for the audit log instead of a database or a single JSON
array?**
Append-only writes are crash-safe and require no read-modify-write of the
whole file. It's the standard shape for event/audit logs (also used by
things like structured application logs), trivially greppable, and doesn't
require a schema migration story for something this size. A database would
be reasonable at larger scale or if querying/rotation became a requirement.

**Q: If you had to add multi-user or concurrent support, what would you
change first?**
The log write (`open(..., "a")` + write) isn't atomic across processes on
all platforms for arbitrary write sizes, and there's no lock. I'd add a file
lock around the log append (or move to a proper logging library / a
lightweight queue writer). `dispatch()` itself has no shared mutable state
beyond the log, so the core gating logic is already safe to call
concurrently.

**Q: Why does declining return a result object instead of raising?**
Because declining isn't a failure of the system — it's the system working
correctly. Modeling it as a return value (`DispatchResult(executed=False, ...)`)
keeps the happy path and the "user said no" path the same shape for the
caller, which matters because the caller (the LLM loop) needs *some* string
back regardless of outcome to keep the conversation going. Exceptions stay
reserved for actual errors, like the target not existing.

**Q: How would you extend this to support undo?**
Before the destructive `file_tools` call in `dispatch()`, snapshot the
current state (e.g., copy the file/dir to a `.trash/<timestamp>/` folder,
or diff-and-store for overwrites), and record the snapshot location in the
`session_log` entry alongside the existing fields. Restoring would replay
that entry in reverse. This was explicitly a non-goal for this version but
the log's structure (one entry per event, with action/path/outcome) is
already shaped to carry that extra field later without a breaking change.

**Q: What's the single most important line of defense in this whole
codebase?**
`is_destructive()` being checked as the very first thing inside `dispatch()`,
before anything else runs. Every other design choice — prompts, logging,
batch UX, the typed-name confirmation for deletes — sits downstream of that
one boolean gate holding.
