"""Reject common secret/configuration-file probes before the Django stack.

Public web services are continuously scanned for accidentally exposed
credentials and deployment files. These requests are not application routes;
short-circuit them before sessions, authentication, activity tracking, or
business middleware can do work for them.
"""
from __future__ import annotations

from urllib.parse import unquote

from django.http import HttpResponseNotFound


_SENSITIVE_DIRECTORIES = {
    ".aws",
    ".git",
    ".docker",
    ".cursor",
    ".claude",
}

_SENSITIVE_FILES = {
    ".gitlab-ci.yml",
    ".gitmodules",
    ".npmrc",
    ".netrc",
    ".boto",
    ".s3cfg",
    ".htaccess",
    ".htpasswd",
    ".dockerignore",
    "dockerfile",
    "docker-compose.yml",
    "docker-compose.yaml",
    "env",
    "env.txt",
    "env.js",
    "env-config.js",
    "credentials",
    "credentials.ini",
    "credentials.json",
    "database.sql",
    "auth.json",
    "settings.json",
    "secrets.json",
    "sentry.properties",
    "config.env",
    "config.yaml",
    "config.yml",
    "config.php",
    "config.json",
    "config.js",
    "runtime-config.js",
    "info.php",
    "phpinfo",
    "phpinfo.php",
}

_SENSITIVE_PATHS = {
    "/actuator/env",
    "/api/actuator/env",
    "/_profiler/phpinfo",
    "/vendor/composer/installed.json",
    "/storage/logs/laravel.log",
}


class SensitiveFileProbeMiddleware:
    """Return a minimal 404 for well-known secret and server-file probes."""

    def __init__(self, get_response):
        self.get_response = get_response

    @staticmethod
    def is_probe(path: str) -> bool:
        # Decode twice to catch ordinary and double-encoded path traversal
        # spellings without consulting the query string or request body.
        decoded = path or "/"
        for _ in range(2):
            next_value = unquote(decoded)
            if next_value == decoded:
                break
            decoded = next_value

        normalized = decoded.replace("\\", "/").lower()
        segments = [segment for segment in normalized.split("/") if segment]
        if not segments:
            return False

        if any(segment in _SENSITIVE_DIRECTORIES for segment in segments):
            return True

        basename = segments[-1]
        if basename in _SENSITIVE_FILES:
            return True

        # Cover .env, .env.production, .env.backup, .env-example, etc.
        if any(segment.startswith(".env") for segment in segments):
            return True

        # Credential and secret dumps are commonly requested with suffixes.
        if basename.startswith(("credentials.", "secrets.")):
            return True

        # Framework-specific environment/config discovery endpoints.
        if basename.startswith("appsettings.") and basename.endswith(".json"):
            return True

        return "/" + "/".join(segments) in _SENSITIVE_PATHS

    def __call__(self, request):
        if self.is_probe(getattr(request, "path_info", None) or request.path):
            response = HttpResponseNotFound("Not found")
            response["Cache-Control"] = "no-store"
            response["X-Content-Type-Options"] = "nosniff"
            return response
        return self.get_response(request)
