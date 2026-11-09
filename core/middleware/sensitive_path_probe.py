"""Reject automated secret/configuration probes before application middleware.

AlgoBot is not a generic file server. Requests for dotfiles, credentials,
deployment manifests, debug consoles, and common framework secret paths must
never reach admin routing, authentication, session handling, or business views.
"""
from __future__ import annotations

from django.http import HttpResponseNotFound


class SensitivePathProbeMiddleware:
    """Short-circuit common secret/configuration reconnaissance with a 404."""

    _ALLOWED_HIDDEN_SEGMENTS = {".well-known"}
    _SENSITIVE_FILENAMES = {
        "dockerfile",
        "docker-compose.yml",
        "docker-compose.yaml",
        "composer.json",
        "composer.lock",
        "package-lock.json",
        "yarn.lock",
        "pnpm-lock.yaml",
        "sentry.properties",
        "server-info",
        "phpinfo",
        "phpinfo.php",
        "info.php",
        "actuator",
        "appsettings.json",
        "appsettings.production.json",
        "appsettings.development.json",
        "database.sql",
        "credentials",
        "credentials.ini",
        "credentials.json",
        "secrets.json",
        "auth.json",
        "config.env",
        "config.yaml",
        "config.yml",
        "config.php",
        "config.json",
        "runtime-config.js",
        "env",
        "env.txt",
        "env.js",
    }
    _SENSITIVE_PREFIXES = (
        "/.git/",
        "/.aws/",
        "/.docker/",
        "/.cursor/",
        "/.claude/",
        "/.ssh/",
        "/.config/",
        "/.npm/",
        "/.vscode/",
        "/_profiler/",
        "/actuator/",
        "/api/actuator/",
        "/vendor/composer/",
        "/storage/logs/",
    )

    def __init__(self, get_response):
        self.get_response = get_response

    @classmethod
    def is_probe(cls, path: str) -> bool:
        normalized = (path or "/").split("?", 1)[0].lower()
        if normalized.startswith(cls._SENSITIVE_PREFIXES):
            return True

        segments = [segment for segment in normalized.split("/") if segment]
        if any(
            segment.startswith(".") and segment not in cls._ALLOWED_HIDDEN_SEGMENTS
            for segment in segments
        ):
            return True
        if any(segment in cls._SENSITIVE_FILENAMES for segment in segments):
            return True
        return False

    def __call__(self, request):
        if not self.is_probe(request.path_info):
            return self.get_response(request)

        response = HttpResponseNotFound()
        response["Cache-Control"] = "no-store"
        response["X-Content-Type-Options"] = "nosniff"
        return response
