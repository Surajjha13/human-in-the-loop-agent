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
