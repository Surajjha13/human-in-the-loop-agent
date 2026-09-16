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
