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
