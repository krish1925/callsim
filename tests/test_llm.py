import json
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any

import pytest
from pydantic import BaseModel

from callsim.llm import LLM, LLMError


class Out(BaseModel):
    message: str


def _serve(replies: list[str]) -> Iterator[tuple[str, list[dict[str, Any]]]]:
    seen: list[dict[str, Any]] = []

    class H(BaseHTTPRequestHandler):
        def log_message(self, *a: object) -> None:
            pass

        def _send(self, obj: dict[str, Any]) -> None:
            data = json.dumps(obj).encode()
            self.send_response(200)
            self.send_header("content-length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self) -> None:
            self._send({"data": [{"id": "stub-model"}]})

        def do_POST(self) -> None:
            seen.append(json.loads(self.rfile.read(int(self.headers["content-length"]))))
            content = replies[min(len(seen) - 1, len(replies) - 1)]
            self._send(
                {
                    "choices": [{"message": {"content": content}}],
                    "usage": {"prompt_tokens": 10, "completion_tokens": 5},
                }
            )

    srv = HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        yield f"http://127.0.0.1:{srv.server_port}/v1", seen
    finally:
        srv.shutdown()


@pytest.fixture
def good() -> Iterator[tuple[str, list[dict[str, Any]]]]:
    yield from _serve(['{"message": "hi"}'])


@pytest.fixture
def flaky() -> Iterator[tuple[str, list[dict[str, Any]]]]:
    yield from _serve(["not json", '<think>hmm</think>{"message": "ok"}'])


@pytest.fixture
def bad() -> Iterator[tuple[str, list[dict[str, Any]]]]:
    yield from _serve(["nope"])


def test_parse_resolves_model_and_sends_schema_no_temperature(
    good: tuple[str, list[dict[str, Any]]],
) -> None:
    url, seen = good
    llm = LLM(base_url=url)
    assert llm.parse("sys", [{"role": "user", "content": "x"}], Out).message == "hi"
    body = seen[0]
    assert body["model"] == "stub-model"
    assert body["response_format"]["json_schema"]["schema"]["required"] == ["message"]
    assert "temperature" not in body
    assert llm.usage.prompt_tokens == 10 and llm.usage.completion_tokens == 5


def test_invalid_output_is_retried_once_and_think_is_stripped(
    flaky: tuple[str, list[dict[str, Any]]],
) -> None:
    url, seen = flaky
    assert LLM(base_url=url).parse("s", [], Out).message == "ok"
    assert len(seen) == 2 and "Invalid output" in seen[1]["messages"][-1]["content"]


def test_persistent_garbage_raises(bad: tuple[str, list[dict[str, Any]]]) -> None:
    with pytest.raises(LLMError):
        LLM(base_url=bad[0]).parse("s", [], Out)


def test_unreachable_server_raises() -> None:
    with pytest.raises(LLMError):
        LLM(base_url="http://127.0.0.1:1/v1", timeout_s=1).parse("s", [], Out)
