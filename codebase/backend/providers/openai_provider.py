from __future__ import annotations

import json
import os
from typing import Any

from providers.base import ModelResponse, ResponseModel, ToolCall

DEFAULT_EMBEDDING_MODEL = "text-embedding-3-small"


class OpenAIProvider:
    """OpenAI Chat Completions provider with normalized tool_calls output."""

    def __init__(
        self,
        *,
        api_key_env: str = "OPENAI_API_KEY",
        base_url: str | None = None,
        default_model: str = "gpt-4o",
    ) -> None:
        self.api_key_env = api_key_env
        self.base_url = base_url
        self.default_model = default_model

    def _client(self) -> Any:
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise RuntimeError("Install live provider dependency first: pip install openai") from exc

        api_key = (
            os.getenv(self.api_key_env)
            or os.getenv("OPENAI_API_KEY")
            or os.getenv("GEMINI_API_KEY")
            or os.getenv("GOOGLE_API_KEY")
        )
        if not api_key:
            raise RuntimeError(f"Missing API key env var: {self.api_key_env} (or GEMINI_API_KEY / GOOGLE_API_KEY)")

        base_url = self.base_url
        if not base_url and (os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")) and not os.getenv("OPENAI_API_KEY"):
            base_url = "https://generativelanguage.googleapis.com/v1beta/openai/"

        return OpenAI(api_key=api_key, base_url=base_url)

    def complete(
        self,
        messages: list[dict[str, str]],
        tools: list[dict[str, Any]] | None = None,
        *,
        model: str | None = None,
        temperature: float = 0.0,
        tool_choice: Any | None = None,
    ) -> ModelResponse:
        client = self._client()
        kwargs: dict[str, Any] = {
            "model": model or self.default_model,
            "messages": messages,
            "temperature": temperature,
        }
        if tools:
            kwargs["tools"] = tools
        if tool_choice is not None:
            kwargs["tool_choice"] = tool_choice

        resp = client.chat.completions.create(**kwargs)
        msg = resp.choices[0].message
        calls: list[ToolCall] = []
        for call in msg.tool_calls or []:
            args = json.loads(call.function.arguments or "{}")
            calls.append(ToolCall(name=call.function.name, args=args))
        return ModelResponse(text=msg.content, tool_calls=calls, raw=resp)

    def parse(
        self,
        messages: list[dict[str, str]],
        response_format: type[ResponseModel],
        *,
        model: str | None = None,
        temperature: float = 0.0,
    ) -> ResponseModel:
        """Structured-output completion — the OpenAI-native equivalent of
        LangChain's `.with_structured_output(response_format)`, used by
        studypulse/ nodes so they don't need a LangChain chat model."""
        client = self._client()
        resp = client.chat.completions.parse(
            model=model or self.default_model,
            messages=messages,
            temperature=temperature,
            response_format=response_format,
        )
        parsed = resp.choices[0].message.parsed
        if parsed is None:
            refusal = resp.choices[0].message.refusal
            raise RuntimeError(f"Model declined to produce {response_format.__name__}: {refusal}")
        return parsed

    def embed(self, texts: list[str], *, model: str | None = None) -> list[list[float]]:
        client = self._client()
        resp = client.embeddings.create(model=model or DEFAULT_EMBEDDING_MODEL, input=texts)
        return [item.embedding for item in resp.data]
