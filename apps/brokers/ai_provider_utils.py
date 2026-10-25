"""Shared configurable AI provider routing, retry, and health-check helpers.

Secrets are read only from environment variables or Django settings. Diagnostics
intentionally contain provider names and status categories, never headers or keys.
"""
from __future__ import annotations

import os
import time
from typing import Any

import requests
from django.conf import settings

PROVIDER_SPECS = (
    ("openai", "OPENAI_API_KEY", "OPENAI_BASE_URL", "OPENAI_PROJECT_MANAGER_MODEL", "https://api.openai.com/v1", "gpt-4.1", "responses"),
    ("nvidia", "NVIDIA_API_KEY", "NVIDIA_BASE_URL", "NVIDIA_MODEL", "https://integrate.api.nvidia.com/v1", "meta/llama-3.3-70b-instruct", "chat"),
    ("openrouter", "OPENROUTER_API_KEY", "OPENROUTER_BASE_URL", "OPENROUTER_MODEL", "https://openrouter.ai/api/v1", "openai/gpt-oss-20b", "chat"),
    ("groq", "GROQ_API_KEY", "GROQ_BASE_URL", "GROQ_MODEL", "https://api.groq.com/openai/v1", "llama-3.3-70b-versatile", "chat"),
    ("gemini", "GEMINI_API_KEY", "GEMINI_BASE_URL", "GEMINI_MODEL", "https://generativelanguage.googleapis.com/v1beta/openai", "gemini-2.5-flash", "chat"),
    ("cerebras", "CEREBRAS_API_KEY", "CEREBRAS_BASE_URL", "CEREBRAS_MODEL", "https://api.cerebras.ai/v1", "llama-3.3-70b", "chat"),
)
TRANSIENT_STATUSES = {408, 425, 429, 500, 502, 503, 504}
PERMANENT_STATUSES = {400, 401, 402, 403, 404, 405, 410, 422}


def _setting(name: str, default: str = "") -> str:
    return str(os.environ.get(name) or getattr(settings, name, "") or default).strip()


def configured_providers(include_openai: bool = True) -> list[dict[str, str]]:
    """Return configured providers in priority order; never log or expose keys."""
    providers = []
    for name, key_name, base_name, model_name, default_base, default_model, api_style in PROVIDER_SPECS:
        if name == "openai" and not include_openai:
            continue
        key = _setting(key_name)
        if not key:
            continue
        base = _setting(base_name, default_base).rstrip("/")
        model_default = _setting("OPENAI_PROJECT_MANAGER_MODEL", default_model) if name == "openai" else default_model
        model = _setting(model_name, model_default)
        endpoint = base + ("/responses" if api_style == "responses" else "/chat/completions")
        providers.append({"name": name, "key": key, "base_url": base, "url": endpoint, "model": model, "api_style": api_style})
    return providers


def request_with_retry(method: str, url: str, *, headers: dict[str, str] | None = None,
                       json: dict[str, Any] | None = None, timeout: int = 60,
                       max_retries: int = 2, session: Any = requests) -> requests.Response:
    """Retry only transient transport/server/rate-limit failures with bounded backoff."""
    last_error = None
    for attempt in range(max_retries + 1):
        try:
            response = session.request(method, url, headers=headers, json=json, timeout=timeout)
            if response.status_code not in TRANSIENT_STATUSES or attempt >= max_retries:
                return response
            retry_after = response.headers.get("Retry-After", "")
            try:
                delay = min(8.0, max(0.0, float(retry_after)))
            except (TypeError, ValueError):
                delay = min(4.0, 0.5 * (2 ** attempt))
        except requests.RequestException as exc:
            last_error = exc
            if attempt >= max_retries:
                raise
            delay = min(4.0, 0.5 * (2 ** attempt))
        time.sleep(delay)
    if last_error:
        raise last_error
    raise requests.RequestException("Provider request failed")


def safe_failure(provider_name: str, response: requests.Response | None = None,
                 error: Exception | None = None) -> str:
    """A concise, credential-free diagnostic suitable for logs and user errors."""
    if response is not None:
        status = response.status_code
        if status == 429:
            return f"{provider_name}: HTTP 429 (rate limit/quota; skipped)"
        if status in {401, 403}:
            return f"{provider_name}: HTTP {status} (credentials/access; skipped)"
        if status in {402}:
            return f"{provider_name}: HTTP 402 (account balance/quota; skipped)"
        if status in {404, 410}:
            return f"{provider_name}: HTTP {status} (endpoint/model unavailable; skipped)"
        return f"{provider_name}: HTTP {status}"
    if isinstance(error, requests.RequestException):
        return f"{provider_name}: network/timeout failure"
    return f"{provider_name}: invalid or empty provider response"


def check_provider_health(provider: dict[str, str], timeout: int = 10) -> dict[str, str]:
    """Check endpoint/key/model access with a lightweight models-list request."""
    url = provider["base_url"].rstrip("/") + "/models"
    try:
        response = requests.get(url, headers={"Authorization": f"Bearer {provider['key']}"}, timeout=timeout)
        if response.ok:
            return {"provider": provider["name"], "status": "reachable", "detail": "Endpoint accepted credentials"}
        return {"provider": provider["name"], "status": "unavailable", "detail": safe_failure(provider["name"], response)}
    except requests.RequestException as exc:
        return {"provider": provider["name"], "status": "unavailable", "detail": safe_failure(provider["name"], error=exc)}


def provider_health_report(timeout: int = 10) -> list[dict[str, str]]:
    """Return safe health statuses for every configured provider."""
    return [check_provider_health(provider, timeout=timeout) for provider in configured_providers()]
