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
