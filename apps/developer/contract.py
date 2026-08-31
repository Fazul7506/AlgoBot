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
    return re.sub(r"//+", "/", route)


def _walk(patterns, prefix=""):
    for pattern in patterns:
        if isinstance(pattern, URLResolver):
            child_prefix = prefix + str(pattern.pattern)
            yield from _walk(pattern.url_patterns, child_prefix)
        elif isinstance(pattern, URLPattern):
            yield prefix + str(pattern.pattern), pattern


def _serializer_schema(serializer_class: Any) -> dict:
    if not serializer_class:
        return {"type": "object", "additionalProperties": True}
    try:
        serializer = serializer_class()
        properties = {}
        required = []
        for name, field in serializer.fields.items():
            field_type = "string"
            if getattr(field, "child", None):
                field_type = "array"
            elif field.__class__.__name__.lower().endswith("integerfield"):
                field_type = "integer"
            elif field.__class__.__name__.lower().endswith("floatfield") or field.__class__.__name__.lower().endswith("decimalfield"):
                field_type = "number"
            elif field.__class__.__name__.lower().endswith("booleanfield"):
                field_type = "boolean"
            elif field.__class__.__name__.lower().endswith("datetimefield"):
                field_type = "string"
            item = {"type": field_type}
            if field_type == "array":
                item["items"] = {"type": "object"}
            if getattr(field, "allow_null", False):
                item["nullable"] = True
            properties[name] = item
            if not getattr(field, "read_only", False) and not getattr(field, "required", False) is False:
                required.append(name)
        schema = {"type": "object", "properties": properties}
        if required:
            schema["required"] = required
        return schema
    except Exception:
        return {"type": "object", "additionalProperties": True}


def _operation(pattern: URLPattern) -> dict:
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
    permission_classes = getattr(cls, "permission_classes", []) if cls else []
    authenticated = any("IsAuthenticated" in getattr(p, "__name__", str(p)) for p in permission_classes)
    callback_name = getattr(callback, "__name__", cls.__name__ if cls else "endpoint")
    route_name = getattr(pattern, "name", None)
    operation_id = route_name or callback_name
    summary = (callback.__doc__ or "").strip().split("\n")[0] if getattr(callback, "__doc__", None) else operation_id.replace("_", " ").title()
    schema = _serializer_schema(serializer_class)
    response = {"200": {"description": "Successful response", "content": {"application/json": {"schema": schema}}}}

    operation = {
        "operationId": operation_id,
        "summary": summary[:160],
        "responses": response,
        "tags": ["Developer API"],
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
        if not route.startswith("/api/v1/"):
            continue
        if route.endswith("/docs/") or route.endswith("/status/"):
            continue
        operation, methods = _operation(pattern)
        path_item = paths.setdefault(route, {})
        for method in methods:
            path_item[method] = dict(operation)
            path_item[method]["operationId"] = f"{method}_{operation['operationId']}"

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
                "ApiKeyAuth": {"type": "apiKey", "in": "header", "name": "X-API-Key", "description": "Use X-API-Key together with X-API-Secret."},
                "BearerAuth": {"type": "http", "scheme": "bearer", "bearerFormat": "JWT"},
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
