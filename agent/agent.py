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
