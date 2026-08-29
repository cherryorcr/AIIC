"""Resilient OpenAI-compatible model routing.

The application calls this module rather than provider SDKs directly. Local
models are preferred for cheap extraction/embedding/reranking tasks, while the
strong provider is preferred for interview feedback. Calls have bounded
timeouts, retries and provider fallback. When a model is unavailable callers
can use their deterministic fallback without interrupting a session.
"""

from __future__ import annotations

import asyncio
import ast
import json
import math
import re
import time
import uuid
from typing import Any

try:  # optional in a minimal development install
    import httpx
except ImportError:  # pragma: no cover
    httpx = None

try:  # jsonschema is optional; a small validator is provided below
    from jsonschema import ValidationError as JsonSchemaValidationError
    from jsonschema import validate as jsonschema_validate
except ImportError:  # pragma: no cover
    JsonSchemaValidationError = Exception  # type: ignore[misc,assignment]
    jsonschema_validate = None

from app.config import Settings
from app.storage.db import Database


LOCAL_TASKS = {"extract", "embed", "embedding", "rerank", "simple_evaluate"}
TRANSIENT_STATUS = {408, 409, 425, 429, 500, 502, 503, 504}


class ModelRouter:
    """Business-layer entry point for local and hosted model gateways."""

    def __init__(self, settings: Settings, db: Database):
        self.settings = settings
        self.db = db
        # In-memory state is diagnostic only; durable call records remain in DB.
        self.provider_states: dict[str, dict[str, Any]] = {}

    def _providers(self, task: str) -> list[tuple[str, str, str, str]]:
        """Return configured providers in preferred order, deduplicated."""
        local = (
            "local",
            str(getattr(self.settings, "local_model_base_url", "") or ""),
            str(getattr(self.settings, "local_model_api_key", "") or ""),
            str(getattr(self.settings, "local_model_name", "local-interview") or "local-interview"),
        )
        strong = (
            "strong",
            str(getattr(self.settings, "strong_model_base_url", "") or ""),
            str(getattr(self.settings, "strong_model_api_key", "") or ""),
            str(getattr(self.settings, "strong_model_name", "gpt-4o-mini") or "gpt-4o-mini"),
        )
        preferred = [local, strong] if task in LOCAL_TASKS else [strong, local]
        result: list[tuple[str, str, str, str]] = []
        seen: set[tuple[str, str]] = set()
        for item in preferred:
            # Hosted providers require a key; local gateways commonly permit
            # an empty key, but always require a URL.
            if not item[1] or (item[0] == "strong" and not item[2]):
                continue
            identity = (item[0], item[1])
            if identity not in seen:
                seen.add(identity)
                result.append(item)
        return result

    def _provider(self, task: str) -> tuple[str, str, str, str] | None:
        """Backward-compatible access to the first provider."""
        providers = self._providers(task)
        return providers[0] if providers else None

    async def complete(
        self,
        task: str,
        messages: list[dict[str, str]],
        session_id: str | None = None,
        *,
        response_schema: dict[str, Any] | None = None,
        temperature: float = 0.2,
        max_tokens: int | None = None,
    ) -> dict[str, Any]:
        """Call a provider with timeout/retry/fallback and normalized telemetry."""
        providers = self._providers(task)
        if not providers or httpx is None:
            self._record_invocation(
                session_id=session_id,
                task=task,
                provider="fallback",
                model="rules",
                latency_ms=0,
                status="fallback",
                fallback_reason="no_model_configured",
            )
            self._mark_provider("fallback", ok=True, error="no_model_configured")
            return {
                "ok": False,
                "text": "",
                "provider": "fallback",
                "model": "rules",
                "error": "no_model_configured",
                "fallback": True,
                "fallback_reason": "no_model_configured",
            }

        max_retries = max(0, int(getattr(self.settings, "model_max_retries", 2)))
        timeout_seconds = max(0.1, float(getattr(self.settings, "model_timeout_seconds", 30)))
        backoff = max(0.0, float(getattr(self.settings, "model_retry_backoff_seconds", 0.25)))
        last_error = "provider_unavailable"
        total_attempts = 0

        for provider_name, base_url, api_key, model in providers:
            for attempt in range(max_retries + 1):
                total_attempts += 1
                started = time.perf_counter()
                status_code: int | None = None
                input_tokens = self._estimate_tokens(messages)
                output_tokens = 0
                try:
                    headers = {"Content-Type": "application/json"}
                    if api_key:
                        headers["Authorization"] = f"Bearer {api_key}"
                    request_body: dict[str, Any] = {
                        "model": model,
                        "messages": messages,
                        "temperature": temperature,
                    }
                    if max_tokens is not None:
                        request_body["max_tokens"] = max_tokens
                    if response_schema is not None:
                        # json_object is supported by most OpenAI-compatible
                        # gateways; full schema validation still happens below.
                        request_body["response_format"] = {"type": "json_object"}
                    url = f"{base_url.rstrip('/')}/chat/completions"
                    async with httpx.AsyncClient(timeout=timeout_seconds) as client:
                        response = await client.post(url, headers=headers, json=request_body)
                    status_code = response.status_code
                    if status_code in TRANSIENT_STATUS:
                        raise RuntimeError(f"http_{status_code}")
                    response.raise_for_status()
                    payload = response.json()
                    text = self._extract_text(payload)
                    output_tokens = self._usage_tokens(payload, "completion_tokens") or self._estimate_tokens_text(text)
                    if not text:
                        raise ValueError("empty_response")
                    repaired = False
                    if response_schema is not None:
                        parsed = self.parse_json(text)
                        if parsed is None:
                            parsed = self.repair_json(text)
                            repaired = parsed is not None
                        self.validate_json(parsed, response_schema)
                        if repaired:
                            text = json.dumps(parsed, ensure_ascii=False)
                    latency_ms = round((time.perf_counter() - started) * 1000, 2)
                    cost = self.estimate_cost(provider_name, input_tokens, output_tokens)
                    self._record_invocation(
                        session_id=session_id,
                        task=task,
                        provider=provider_name,
                        model=model,
                        latency_ms=latency_ms,
                        status="ok",
                        input_tokens=input_tokens,
                        output_tokens=output_tokens,
                        cost_usd=cost,
                        attempt=attempt + 1,
                    )
                    self._mark_provider(provider_name, ok=True)
                    return {
                        "ok": True,
                        "text": text,
                        "provider": provider_name,
                        "model": model,
                        "latency_ms": latency_ms,
                        "input_tokens": input_tokens,
                        "output_tokens": output_tokens,
                        "cost_usd": cost,
                        "attempts": total_attempts,
                        "json_repaired": repaired,
                    }
                except Exception as exc:  # network, protocol, JSON and schema errors
                    error = self._error_name(exc, status_code)
                    last_error = error
                    latency_ms = round((time.perf_counter() - started) * 1000, 2)
                    cost = self.estimate_cost(provider_name, input_tokens, output_tokens)
                    self._record_invocation(
                        session_id=session_id,
                        task=task,
                        provider=provider_name,
                        model=model,
                        latency_ms=latency_ms,
                        status="error",
                        fallback_reason=error,
                        input_tokens=input_tokens,
                        output_tokens=output_tokens,
                        cost_usd=cost,
                        attempt=attempt + 1,
                    )
                    self._mark_provider(provider_name, ok=False, error=error)
                    if attempt < max_retries and backoff:
                        await asyncio.sleep(min(backoff * (2**attempt), 5.0))

        self._record_invocation(
            session_id=session_id,
            task=task,
            provider="fallback",
            model="rules",
            latency_ms=0,
            status="fallback",
            fallback_reason=last_error,
            attempt=total_attempts,
        )
        self._mark_provider("fallback", ok=True, error=last_error)
        return {
            "ok": False,
            "text": "",
            "provider": "fallback",
            "model": "rules",
            "error": last_error,
            "fallback": True,
            "attempts": total_attempts,
            "fallback_reason": last_error,
        }

    async def health(self) -> dict[str, Any]:
        """Probe configured OpenAI-compatible gateways without exposing keys."""
        result: dict[str, Any] = {}
        if httpx is None:
            return {"httpx": "unavailable", "providers": result}
        timeout_seconds = min(max(0.1, float(getattr(self.settings, "model_timeout_seconds", 30))), 5.0)
        for name, base_url, api_key, model in self._providers("evaluate") + self._providers("embed"):
            if name in result:
                continue
            started = time.perf_counter()
            headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
            try:
                async with httpx.AsyncClient(timeout=timeout_seconds) as client:
                    response = await client.get(f"{base_url.rstrip('/')}/models", headers=headers)
                result[name] = {
                    "ok": response.is_success,
                    "status_code": response.status_code,
                    "model": model,
                    "latency_ms": round((time.perf_counter() - started) * 1000, 2),
                }
                self._mark_provider(name, ok=response.is_success, error=None if response.is_success else f"http_{response.status_code}")
            except Exception as exc:  # health is diagnostic, never fatal
                result[name] = {"ok": False, "model": model, "error": self._error_name(exc, None)}
                self._mark_provider(name, ok=False, error=self._error_name(exc, None))
        return {"providers": result, "fallback_available": True, "states": self.provider_states.copy()}

    async def embed(self, texts: list[str], session_id: str | None = None) -> dict[str, Any]:
        """Request embeddings where an OpenAI-compatible endpoint supports it."""
        if not texts:
            return {"ok": True, "embeddings": [], "provider": "none", "model": "none"}
        providers = self._providers("embed")
        if not providers or httpx is None:
            self._record_invocation(session_id=session_id, task="embed", provider="fallback", model="rules", status="fallback", fallback_reason="no_model_configured")
            return {"ok": False, "embeddings": [], "provider": "fallback", "error": "no_model_configured"}
        for provider_name, base_url, api_key, model in providers:
            for attempt in range(max(0, int(getattr(self.settings, "model_max_retries", 2))) + 1):
                started = time.perf_counter()
                input_tokens = self._estimate_tokens_text(" ".join(texts))
                status_code: int | None = None
                try:
                    headers = {"Content-Type": "application/json"}
                    if api_key:
                        headers["Authorization"] = f"Bearer {api_key}"
                    async with httpx.AsyncClient(timeout=float(getattr(self.settings, "model_timeout_seconds", 30))) as client:
                        response = await client.post(f"{base_url.rstrip('/')}/embeddings", headers=headers, json={"model": model, "input": texts})
                    status_code = response.status_code
                    response.raise_for_status()
                    payload = response.json()
                    vectors = [entry.get("embedding") for entry in payload.get("data", [])]
                    if len(vectors) != len(texts) or any(not isinstance(v, list) for v in vectors):
                        raise ValueError("invalid_embedding_response")
                    self._record_invocation(session_id=session_id, task="embed", provider=provider_name, model=model, latency_ms=round((time.perf_counter() - started) * 1000, 2), status="ok", input_tokens=input_tokens, attempt=attempt + 1)
                    self._mark_provider(provider_name, ok=True)
                    return {"ok": True, "embeddings": vectors, "provider": provider_name, "model": model, "attempts": attempt + 1}
                except Exception as exc:
                    error = self._error_name(exc, status_code)
                    self._record_invocation(session_id=session_id, task="embed", provider=provider_name, model=model, latency_ms=round((time.perf_counter() - started) * 1000, 2), status="error", fallback_reason=error, input_tokens=input_tokens, attempt=attempt + 1)
                    self._mark_provider(provider_name, ok=False, error=error)
                    if attempt < int(getattr(self.settings, "model_max_retries", 2)):
                        await asyncio.sleep(min(max(0.0, float(getattr(self.settings, "model_retry_backoff_seconds", .25))) * (2**attempt), 5.0))
        self._record_invocation(session_id=session_id, task="embed", provider="fallback", model="rules", status="fallback", fallback_reason="embedding_unavailable")
        self._mark_provider("fallback", ok=True, error="embedding_unavailable")
        return {"ok": False, "embeddings": [], "provider": "fallback", "error": "embedding_unavailable", "fallback": True}

    @staticmethod
    def _extract_text(payload: dict[str, Any]) -> str:
        choices = payload.get("choices") or []
        if not choices:
            return ""
        message = choices[0].get("message") or {}
        content = message.get("content", choices[0].get("text", ""))
        if isinstance(content, list):
            content = "".join(str(x.get("text", "")) for x in content if isinstance(x, dict))
        return str(content or "").strip()

    @staticmethod
    def parse_json(text: str) -> dict[str, Any] | None:
        """Parse a JSON object from plain or fenced model output."""
        if not text:
            return None
        candidate = text.strip()
        candidate = re.sub(r"^```(?:json)?\s*", "", candidate, flags=re.I)
        candidate = re.sub(r"\s*```$", "", candidate)
        try:
            value = json.loads(candidate)
            return value if isinstance(value, dict) else None
        except json.JSONDecodeError:
            start, end = candidate.find("{"), candidate.rfind("}")
            if start >= 0 and end > start:
                try:
                    value = json.loads(candidate[start : end + 1])
                    return value if isinstance(value, dict) else None
                except json.JSONDecodeError:
                    return None
            return None

    @staticmethod
    def repair_json(text: str) -> dict[str, Any] | None:
        """Best-effort, safe repair for common LLM JSON formatting mistakes."""
        if not text:
            return None
        candidate = text.strip()
        candidate = re.sub(r"^```(?:json)?\s*", "", candidate, flags=re.I)
        candidate = re.sub(r"\s*```$", "", candidate).strip()
        start, end = candidate.find("{"), candidate.rfind("}")
        if start >= 0 and end > start:
            candidate = candidate[start : end + 1]
        # Remove trailing commas before a closing token, a frequent provider
        # failure.  ast.literal_eval handles single-quoted dicts without code
        # execution and is only used after JSON parsing already failed.
        candidate = re.sub(r",\s*([}\]])", r"\1", candidate)
        try:
            value = json.loads(candidate)
        except json.JSONDecodeError:
            try:
                value = ast.literal_eval(candidate)
            except (ValueError, SyntaxError, MemoryError, RecursionError):
                return None
        return value if isinstance(value, dict) else None

    def _mark_provider(self, provider: str, *, ok: bool, error: str | None = None) -> None:
        state = self.provider_states.setdefault(provider, {"attempts": 0, "failures": 0})
        state["attempts"] = int(state.get("attempts", 0)) + 1
        if ok:
            state.update({"ok": True, "last_error": None, "last_success_at": time.time()})
        else:
            state.update({"ok": False, "failures": int(state.get("failures", 0)) + 1, "last_error": error})

    def provider_status(self) -> dict[str, dict[str, Any]]:
        """Return a copy suitable for diagnostics/health endpoints."""
        return {name: state.copy() for name, state in self.provider_states.items()}

    @staticmethod
    def validate_json(value: Any, schema: dict[str, Any]) -> None:
        """Validate model JSON, raising ``ValueError`` with a safe message."""
        if value is None:
            raise ValueError("response_not_valid_json")
        if jsonschema_validate is not None:
            try:
                jsonschema_validate(value, schema)
                return
            except JsonSchemaValidationError as exc:
                path = ".".join(str(x) for x in getattr(exc, "path", []))
                raise ValueError(f"response_schema_invalid:{path}" if path else "response_schema_invalid") from exc
        if schema.get("type") == "object" and not isinstance(value, dict):
            raise ValueError("response_schema_invalid:type")
        for key in schema.get("required", []):
            if key not in value:
                raise ValueError(f"response_schema_invalid:required:{key}")
        for key, rule in schema.get("properties", {}).items():
            if key not in value:
                continue
            expected = rule.get("type")
            actual = value[key]
            if expected == "string" and not isinstance(actual, str):
                raise ValueError(f"response_schema_invalid:type:{key}")
            if expected == "array" and not isinstance(actual, list):
                raise ValueError(f"response_schema_invalid:type:{key}")
            if expected == "object" and not isinstance(actual, dict):
                raise ValueError(f"response_schema_invalid:type:{key}")
            if "enum" in rule and actual not in rule["enum"]:
                raise ValueError(f"response_schema_invalid:enum:{key}")

    @staticmethod
    def _usage_tokens(payload: dict[str, Any], key: str) -> int:
        usage = payload.get("usage") or {}
        try:
            return max(0, int(usage.get(key) or 0))
        except (TypeError, ValueError):
            return 0

    @staticmethod
    def _estimate_tokens(messages: list[dict[str, str]]) -> int:
        return ModelRouter._estimate_tokens_text(" ".join(str(m.get("content", "")) for m in messages))

    @staticmethod
    def _estimate_tokens_text(text: str) -> int:
        return max(1, math.ceil(len(text) / 4)) if text else 0

    def estimate_cost(self, provider: str, input_tokens: int, output_tokens: int) -> float:
        if provider == "strong":
            in_rate = float(getattr(self.settings, "strong_model_input_cost_per_1k", 0.0))
            out_rate = float(getattr(self.settings, "strong_model_output_cost_per_1k", 0.0))
        else:
            in_rate = float(getattr(self.settings, "local_model_input_cost_per_1k", 0.0))
            out_rate = float(getattr(self.settings, "local_model_output_cost_per_1k", 0.0))
        return round((input_tokens / 1000) * in_rate + (output_tokens / 1000) * out_rate, 8)

    def _record_invocation(self, **payload: Any) -> None:
        """Persist telemetry while remaining compatible with older DB adapters."""
        record = {
            "id": f"mi-{uuid.uuid4().hex}",
            "session_id": payload.get("session_id"),
            "task": payload.get("task", "unknown"),
            "provider": payload.get("provider", "unknown"),
            "model": payload.get("model", "unknown"),
            "latency_ms": payload.get("latency_ms"),
            "status": payload.get("status", "error"),
            "fallback_reason": payload.get("fallback_reason"),
            "input_tokens": payload.get("input_tokens"),
            "output_tokens": payload.get("output_tokens"),
            "cost_usd": payload.get("cost_usd"),
            "attempt": payload.get("attempt"),
        }
        try:
            self.db.save_model_invocation(record)
        except Exception:
            # Telemetry must never make an interview request fail while a
            # legacy schema is being migrated.
            return

    @staticmethod
    def _error_name(exc: Exception, status_code: int | None) -> str:
        if status_code:
            return f"http_{status_code}"
        if isinstance(exc, TimeoutError) or (httpx is not None and isinstance(exc, httpx.TimeoutException)):
            return "timeout"
        message = str(exc).strip().replace("\n", " ")
        return message[:120] if message else type(exc).__name__
