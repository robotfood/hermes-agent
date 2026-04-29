"""OpenAI-compatible facade over Vertex AI Gemini via Google Gen AI SDK."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any, Dict, Iterator, List, Optional

from agent.gemini_native_adapter import (
    GeminiAPIError,
    _GeminiStreamChunk,
    build_gemini_request,
    translate_gemini_response,
    translate_stream_event,
)
from agent.google_vertex import init_google_vertex
from hermes_cli.config import load_config


def is_vertex_base_url(base_url: str) -> bool:
    return str(base_url or "").strip().lower().startswith("vertexai://")


def _genai_modules() -> tuple[Any, Any]:
    try:
        from google import genai
        from google.genai import types
    except ImportError as exc:
        raise RuntimeError(
            "Google Vertex AI support requires google-genai. "
            "Install it with `pip install google-genai`."
        ) from exc
    return genai, types


def _enum_values(payload: Any) -> Any:
    """Convert SDK enum objects in responses back to plain string values."""

    if isinstance(payload, list):
        return [_enum_values(item) for item in payload]
    if isinstance(payload, dict):
        return {key: _enum_values(value) for key, value in payload.items()}
    value = getattr(payload, "value", None)
    if isinstance(value, str):
        return value
    return payload


def _function_declarations_for_genai(payload: Any) -> Any:
    if isinstance(payload, list):
        return [_function_declarations_for_genai(item) for item in payload]
    if not isinstance(payload, dict):
        return payload

    converted: Dict[str, Any] = {}
    for key, value in payload.items():
        if key == "parameters" and isinstance(value, dict):
            converted["parametersJsonSchema"] = value
        else:
            converted[key] = _function_declarations_for_genai(value)
    return converted


def _contents_from_request(request: Dict[str, Any]) -> List[Any]:
    return [item for item in request.get("contents", []) if isinstance(item, dict)]


def _tools_from_request(request: Dict[str, Any]) -> Optional[List[Any]]:
    tools = request.get("tools")
    if not isinstance(tools, list) or not tools:
        return None
    return [
        _function_declarations_for_genai(item)
        for item in tools
        if isinstance(item, dict)
    ]


def _system_instruction_from_request(request: Dict[str, Any]) -> Any:
    system = request.get("systemInstruction")
    if not isinstance(system, dict):
        return None
    parts = system.get("parts")
    if not isinstance(parts, list):
        return None
    text = "\n".join(
        str(part.get("text"))
        for part in parts
        if isinstance(part, dict) and part.get("text")
    ).strip()
    return text or None


def _response_to_dict(response: Any) -> Dict[str, Any]:
    if isinstance(response, dict):
        return response
    model_dump = getattr(response, "model_dump", None)
    if callable(model_dump):
        value = model_dump(by_alias=True, exclude_none=True)
        if isinstance(value, dict):
            return _enum_values(value)
    to_dict = getattr(response, "to_dict", None)
    if callable(to_dict):
        value = to_dict()
        if isinstance(value, dict):
            return _enum_values(value)
    raw = getattr(response, "_raw_response", None)
    if raw is not None:
        raw_to_dict = getattr(raw, "to_dict", None)
        if callable(raw_to_dict):
            value = raw_to_dict()
            if isinstance(value, dict):
                return value

    candidates_payload = []
    for cand in getattr(response, "candidates", []) or []:
        parts_payload = []
        content = getattr(cand, "content", None)
        for part in getattr(content, "parts", []) or []:
            part_payload: Dict[str, Any] = {}
            text = getattr(part, "text", None)
            if text:
                part_payload["text"] = text
            function_call = getattr(part, "function_call", None) or getattr(part, "functionCall", None)
            if function_call is not None:
                name = getattr(function_call, "name", "")
                args = getattr(function_call, "args", {}) or {}
                part_payload["functionCall"] = {"name": name, "args": dict(args)}
            if part_payload:
                parts_payload.append(part_payload)
        candidates_payload.append(
            {
                "content": {"parts": parts_payload},
                "finishReason": _enum_values(
                    getattr(cand, "finish_reason", None) or getattr(cand, "finishReason", None)
                ),
            }
        )

    usage = getattr(response, "usage_metadata", None) or getattr(response, "usageMetadata", None)
    usage_payload: Dict[str, Any] = {}
    if usage is not None:
        usage_payload = {
            "promptTokenCount": getattr(usage, "prompt_token_count", 0),
            "candidatesTokenCount": getattr(usage, "candidates_token_count", 0),
            "totalTokenCount": getattr(usage, "total_token_count", 0),
        }
    return {"candidates": candidates_payload, "usageMetadata": usage_payload}


class _VertexChatCompletions:
    def __init__(self, client: "GeminiVertexClient"):
        self._client = client

    def create(self, **kwargs: Any) -> Any:
        return self._client._create_chat_completion(**kwargs)


class _AsyncVertexChatCompletions:
    def __init__(self, client: "AsyncGeminiVertexClient"):
        self._client = client

    async def create(self, **kwargs: Any) -> Any:
        return await self._client._create_chat_completion(**kwargs)


class _VertexChatNamespace:
    def __init__(self, client: "GeminiVertexClient"):
        self.completions = _VertexChatCompletions(client)


class _AsyncVertexChatNamespace:
    def __init__(self, client: "AsyncGeminiVertexClient"):
        self.completions = _AsyncVertexChatCompletions(client)


class GeminiVertexClient:
    """Minimal OpenAI-SDK-compatible facade over Vertex Gemini."""

    def __init__(
        self,
        *,
        project: str = "",
        location: str = "",
        timeout: Any = None,
        **_: Any,
    ) -> None:
        config = load_config()
        vertex_config = init_google_vertex(config)
        if not vertex_config:
            if not project:
                raise RuntimeError(
                    "Google Vertex AI requires a project. Set "
                    "provider.google-vertex.options.project in config.yaml or "
                    "GOOGLE_CLOUD_PROJECT, GCP_PROJECT, or GCLOUD_PROJECT."
                )
            vertex_config = {"project": project, "location": location or "us-central1"}
            try:
                genai, _ = _genai_modules()
            except ImportError as exc:
                raise RuntimeError(
                    "Google Vertex AI support requires google-genai. "
                    "Install it with `pip install google-genai`."
                ) from exc
            self._genai = genai
        else:
            self._genai, _ = _genai_modules()

        self.project = vertex_config["project"]
        self.location = vertex_config["location"]
        self.api_key = "google-adc"
        self.base_url = "vertexai://google"
        self.timeout = timeout
        self._genai_client = self._genai.Client(
            vertexai=True,
            project=self.project,
            location=self.location,
        )
        self.chat = _VertexChatNamespace(self)
        self.is_closed = False

    def close(self) -> None:
        self.is_closed = True

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    @staticmethod
    def _advance_stream_iterator(iterator: Iterator[_GeminiStreamChunk]) -> tuple[bool, Optional[_GeminiStreamChunk]]:
        try:
            return False, next(iterator)
        except StopIteration:
            return True, None

    def _create_chat_completion(
        self,
        *,
        model: str = "gemini-2.5-flash",
        messages: Optional[List[Dict[str, Any]]] = None,
        stream: bool = False,
        tools: Any = None,
        tool_choice: Any = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        top_p: Optional[float] = None,
        stop: Any = None,
        extra_body: Optional[Dict[str, Any]] = None,
        **_: Any,
    ) -> Any:
        thinking_config = None
        if isinstance(extra_body, dict):
            thinking_config = extra_body.get("thinking_config") or extra_body.get("thinkingConfig")

        request = build_gemini_request(
            messages=messages or [],
            tools=tools,
            tool_choice=tool_choice,
            temperature=temperature,
            max_tokens=max_tokens,
            top_p=top_p,
            stop=stop,
            thinking_config=thinking_config,
        )

        config = {
            **(request.get("generationConfig") if isinstance(request.get("generationConfig"), dict) else {}),
            "systemInstruction": _system_instruction_from_request(request),
            "tools": _tools_from_request(request),
            "toolConfig": request.get("toolConfig") if isinstance(request.get("toolConfig"), dict) else None,
        }
        config = {key: value for key, value in config.items() if value is not None}

        try:
            if stream:
                result = self._genai_client.models.generate_content_stream(
                    model=model,
                    contents=_contents_from_request(request),
                    config=config or None,
                )
            else:
                result = self._genai_client.models.generate_content(
                    model=model,
                    contents=_contents_from_request(request),
                    config=config or None,
                )
        except Exception as exc:
            raise GeminiAPIError(
                f"Vertex Gemini request failed: {exc}",
                code="vertex_gemini_error",
            ) from exc

        if stream:
            return self._stream_chunks(result, model=model)
        return translate_gemini_response(_response_to_dict(result), model=model)

    def _stream_chunks(self, responses: Any, *, model: str) -> Iterator[_GeminiStreamChunk]:
        tool_call_indices: Dict[str, Dict[str, Any]] = {}
        for response in responses:
            for chunk in translate_stream_event(_response_to_dict(response), model, tool_call_indices):
                yield chunk


class AsyncGeminiVertexClient:
    def __init__(self, sync_client: GeminiVertexClient):
        self._sync = sync_client
        self.api_key = sync_client.api_key
        self.base_url = sync_client.base_url
        self.chat = _AsyncVertexChatNamespace(self)

    async def _create_chat_completion(self, **kwargs: Any) -> Any:
        stream = bool(kwargs.get("stream"))
        result = await asyncio.to_thread(self._sync.chat.completions.create, **kwargs)
        if not stream:
            return result

        async def _async_stream() -> Any:
            while True:
                done, chunk = await asyncio.to_thread(self._sync._advance_stream_iterator, result)
                if done:
                    break
                yield chunk

        return _async_stream()

    async def close(self) -> None:
        await asyncio.to_thread(self._sync.close)
