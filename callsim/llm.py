"""LLM client for any OpenAI-compatible server (default: local MiMo on 127.0.0.1:8000).

Stdlib only. Structured output via `response_format: json_schema`, validated with pydantic.
Sampling parameters are not sent, so the server's defaults apply.
"""

import json
import os
import re
import urllib.error
import urllib.request
from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError

T = TypeVar("T", bound=BaseModel)

DEFAULT_BASE_URL = "http://127.0.0.1:8000/v1"


class LLMError(RuntimeError):
    """Server unreachable, bad HTTP status, or output that never validated."""


class Usage(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0

    def add(self, other: "Usage") -> None:
        self.prompt_tokens += other.prompt_tokens
        self.completion_tokens += other.completion_tokens


class LLM:
    def __init__(
        self,
        base_url: str | None = None,
        model: str | None = None,
        timeout_s: float = 120.0,
        max_tokens: int = 800,
    ) -> None:
        self.base_url = (
            base_url or os.environ.get("CALLSIM_LLM_BASE_URL") or DEFAULT_BASE_URL
        ).rstrip("/")
        self.model = model or os.environ.get("CALLSIM_LLM_MODEL")
        self.timeout_s = timeout_s
        self.max_tokens = max_tokens
        self.usage = Usage()

    def _post(self, path: str, body: dict[str, Any] | None) -> dict[str, Any]:
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(
            self.base_url + path,
            data=data,
            headers={"content-type": "application/json"},
            method="POST" if body is not None else "GET",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout_s) as resp:
                out = json.loads(resp.read())
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise LLMError(f"LLM request to {self.base_url}{path} failed: {exc}") from exc
        if not isinstance(out, dict):
            raise LLMError(f"unexpected response shape from {path}")
        return out

    def resolve_model(self) -> str:
        if self.model is None:
            models = self._post("/models", None).get("data", [])
            if not models:
                raise LLMError("server lists no models; set CALLSIM_LLM_MODEL")
            self.model = str(models[0]["id"])
        return self.model

    def parse(
        self, system: str, messages: list[dict[str, str]], output_model: type[T], retries: int = 1
    ) -> T:
        """One structured completion. Retries once, telling the model what was wrong."""
        convo = [{"role": "system", "content": system}, *messages]
        last_err = ""
        for _ in range(retries + 1):
            if last_err:
                convo = [
                    *convo,
                    {"role": "user", "content": f"Invalid output ({last_err}). Retry."},
                ]
            body = {
                "model": self.resolve_model(),
                "messages": convo,
                "max_tokens": self.max_tokens,
                "response_format": {
                    "type": "json_schema",
                    "json_schema": {
                        "name": output_model.__name__,
                        "schema": output_model.model_json_schema(),
                    },
                },
            }
            resp = self._post("/chat/completions", body)
            self.usage.add(Usage.model_validate(resp.get("usage", {})))
            try:
                text = resp["choices"][0]["message"]["content"] or ""
                return output_model.model_validate_json(_strip_think(text))
            except (KeyError, IndexError, ValidationError) as exc:
                last_err = str(exc).splitlines()[0][:200]
        raise LLMError(f"output never validated against {output_model.__name__}: {last_err}")


def _strip_think(text: str) -> str:
    return re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
