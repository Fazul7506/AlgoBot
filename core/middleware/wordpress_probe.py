"""Middleware helpers for low-value automated probes.

AlgoBot is not a WordPress installation or a generic file server. Internet
scanners routinely probe common CMS paths, dotfiles, credentials, deployment
manifests, and debug endpoints. Reject those signatures before session,
authentication, admin routing, or application business logic.
"""
from urllib.parse import unquote

from django.http import HttpResponseNotFound


class WordPressProbeMiddleware:
    """Short-circuit common reconnaissance requests with a uniform 404."""

    _PATH_MARKERS = (
        "/wp-admin/", "/wp-json/", "/wp-includes/", "/wp-content/",
        "/wp/v2/", "/wordpress/wp-", "/blog/wp-",
    )
    _ROOT_MARKERS = ("/wp/", "/wordpress/", "/blog/")
    _ALLOWED_HIDDEN_SEGMENTS = {".well-known"}
    _SENSITIVE_FILENAMES = {
        "dockerfile", "docker-compose.yml", "docker-compose.yaml",
        "composer.json", "composer.lock", "package-lock.json", "yarn.lock",
        "pnpm-lock.yaml", "sentry.properties", "server-info", "phpinfo",
        "phpinfo.php", "info.php", "actuator", "appsettings.json",
        "appsettings.production.json", "appsettings.development.json",
        "database.sql", "credentials", "credentials.ini", "credentials.json",
        "secrets.json", "auth.json", "config.env", "config.yaml", "config.yml",
        "config.php", "config.json", "config.js", "config.production.json",
        "runtime-config.js", "env", "env.txt", "env.js", "env-config.js",
    }
    _SENSITIVE_PREFIXES = (
        "/.git/", "/.aws/", "/.docker/", "/.cursor/", "/.claude/",
        "/.ssh/", "/.config/", "/.npm/", "/.vscode/", "/_profiler/",
        "/actuator/", "/api/actuator/", "/vendor/composer/", "/storage/logs/",
    )

    def __init__(self, get_response):
        self.get_response = get_response

    @classmethod
    def is_sensitive_path(cls, path):
        normalized = (path or "/").split("?", 1)[0].replace("\\", "/").lower()
        for _ in range(3):
            decoded = unquote(normalized)
            if decoded == normalized:
                break
            normalized = decoded
        if normalized.startswith(cls._SENSITIVE_PREFIXES):
            return True
        segments = [segment for segment in normalized.split("/") if segment]
        # This Django deployment has no PHP application. Short-circuit common
        # PHP shell/info probes before sessions, auth and request telemetry.
        if any(segment.endswith(".php") for segment in segments):
            return True
        if any(
            segment.startswith(".") and segment not in cls._ALLOWED_HIDDEN_SEGMENTS
            for segment in segments
        ):
            return True
        return any(segment in cls._SENSITIVE_FILENAMES for segment in segments)

    @classmethod
    def is_probe(cls, request):
        path = (request.path or "/").lower()
        query = (request.META.get("QUERY_STRING") or "").lower()
        method = request.method.upper()

        if cls.is_sensitive_path(path):
            return True
        if any(marker in path for marker in cls._PATH_MARKERS):
            return True
        if any(path == marker or path.startswith(marker) for marker in cls._ROOT_MARKERS):
            return "rest_route=" in query or method != "GET"
        return False

    def __call__(self, request):
        if not self.is_probe(request):
            return self.get_response(request)

        response = HttpResponseNotFound("Not found")
        response["Cache-Control"] = "no-store"
        response["X-Content-Type-Options"] = "nosniff"
        return response


class WordPressProbeLogFilter:
    """Hide known automated reconnaissance 404s from normal application logs."""

    def filter(self, record):
        request = getattr(record, "request", None)
        path = str(getattr(request, "path", "") or "").lower()
        message = str(record.getMessage() or "").lower()
        markers = (
            "/wp-admin/", "/wp-json/", "/wp-includes/", "/wp-content/",
            "/wp/v2/", "/wordpress/wp-", "/blog/wp-",
        )
        if any(marker in path or marker in message for marker in markers):
            return False
        if WordPressProbeMiddleware.is_sensitive_path(path):
            return False
        if "not found:" in message:
            probed_path = message.split("not found:", 1)[1].strip().split()[0]
            if WordPressProbeMiddleware.is_sensitive_path(probed_path):
                return False
        return True
