"""Authoritative developer API contract builder.

The contract is derived from Django's registered URL patterns at runtime. This
prevents the developer portal from advertising routes that do not exist.
"""
from __future__ import annotations

import re
from typing import Any

from django.urls import URLPattern, URLResolver, get_resolver

HTTP_METHODS = {"get", "post", "put", "patch", "delete", "options", "head"}


def _clean_route(route: str) -> str:
    route = route.replace("^", "").replace("$", "")
    route = route.replace("<int:", "{").replace(">", "}")
    route = re.sub(r"<[^:>]+:", "{", route)
    route = route.replace("<", "{")
    if not route.startswith("/"):
        route = "/" + route
    route = re.sub(r"//+", "/", route)
    # Django commonly names object URL parameters `pk`; expose the stable
    # public API spelling `id` in the generated OpenAPI contract without
    # changing the executable Django route or its view signature.
    route = re.sub(r"\{pk\}", "{id}", route)
    return route


def _walk(patterns, prefix=""):
    for pattern in patterns:
        if isinstance(pattern, URLResolver):
            yield from _walk(pattern.url_patterns, prefix + str(pattern.pattern))
        elif isinstance(pattern, URLPattern):
            yield prefix + str(pattern.pattern), pattern


def _serializer_schema(serializer_class: Any) -> dict:
    if not serializer_class:
        return {"type": "object", "additionalProperties": True}
    try:
        serializer = serializer_class()
        properties, required = {}, []
        for name, field in serializer.fields.items():
            field_name = field.__class__.__name__.lower()
            if getattr(field, "child", None):
                field_type = "array"
            elif "integer" in field_name:
                field_type = "integer"
            elif any(x in field_name for x in ("float", "decimal")):
                field_type = "number"
            elif "boolean" in field_name:
                field_type = "boolean"
            else:
                field_type = "string"
            item = {"type": field_type}
            if field_type == "array":
                item["items"] = {"type": "object"}
            if getattr(field, "allow_null", False):
                item["nullable"] = True
            properties[name] = item
            if getattr(field, "required", False) and not getattr(field, "read_only", False):
                required.append(name)
        schema = {"type": "object", "properties": properties}
        if required:
            schema["required"] = required
        return schema
    except Exception:
        return {"type": "object", "additionalProperties": True}


def _operation(pattern: URLPattern):
    callback = pattern.callback
    cls = getattr(callback, "cls", None)
    actions = getattr(callback, "actions", None) or {}
    methods = sorted(set(actions) & HTTP_METHODS)
    if not methods:
        methods = sorted(set(getattr(callback, "allowed_methods", [])).intersection(HTTP_METHODS))
    if not methods and cls:
        methods = sorted(set(getattr(cls, "http_method_names", [])).intersection(HTTP_METHODS))
    if not methods:
        methods = ["get"]
    serializer_class = getattr(cls, "serializer_class", None) if cls else None
    callback_permissions = getattr(callback, "permission_classes", None)
    class_permissions = getattr(cls, "permission_classes", []) if cls else []
    permission_classes = callback_permissions or class_permissions
    authenticated = any("IsAuthenticated" in getattr(p, "__name__", str(p)) for p in permission_classes)
    callback_name = getattr(callback, "__name__", cls.__name__ if cls else "endpoint")
    operation_id = getattr(pattern, "name", None) or callback_name
    doc = getattr(callback, "__doc__", None) or getattr(cls, "__doc__", "") or ""
    summary = doc.strip().split("\n")[0] or operation_id.replace("_", " ").title()
    schema = _serializer_schema(serializer_class)
    operation = {
        "operationId": operation_id,
        "summary": summary[:160],
        "responses": {
            "200": {
                "description": "Successful response",
                "content": {"application/json": {"schema": schema}},
            }
        },
        "tags": ["AlgoBot API"],
    }
    if authenticated:
        operation["security"] = [{"ApiKeyAuth": []}, {"BearerAuth": []}]
    if any(method in {"post", "put", "patch"} for method in methods):
        operation["requestBody"] = {
            "required": False,
            "content": {"application/json": {"schema": schema}},
        }
    return operation, methods


def build_contract() -> dict:
    paths = {}
    for raw_route, pattern in _walk(get_resolver().url_patterns):
        route = _clean_route(raw_route)
        if not route.startswith("/api/v1/") or route.endswith("/docs/") or route.endswith("/status/"):
            continue
        operation, methods = _operation(pattern)
        path_item = paths.setdefault(route, {})
        for method in methods:
            path_item[method] = {**operation, "operationId": f"{method}_{operation['operationId']}"}
    return {
        "openapi": "3.0.3",
        "info": {
            "title": "AlgoBot Developer API",
            "version": "v1",
            "description": "Authoritative contract generated from registered, executable AlgoBot API routes.",
        },
        "servers": [{"url": "/api/v1"}],
        "security": [{"ApiKeyAuth": []}, {"BearerAuth": []}],
        "components": {
            "securitySchemes": {
                "ApiKeyAuth": {
                    "type": "apiKey",
                    "in": "header",
                    "name": "X-API-Key",
                    "description": "Use X-API-Key together with X-API-Secret.",
                },
                "BearerAuth": {
                    "type": "http",
                    "scheme": "bearer",
                    "bearerFormat": "JWT",
                },
            }
        },
        "x-algobot": {
            "contract_source": "django-urlconf",
            "version_policy": "v1 remains backwards-compatible; breaking changes require v2.",
            "websocket": {
                "market_data": "/ws/market-data/",
                "notifications": "/ws/notifications/",
                "portfolio": "/ws/portfolio/",
                "broker": "/ws/broker/",
                "reconnect": "Exponential backoff with jitter; clients must resubscribe after reconnect.",
            },
            "trading_safety": "Trading routes retain broker, entitlement, risk, freshness, environment and execution gates.",
        },
        "paths": dict(sorted(paths.items())),
    }
