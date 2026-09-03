"""High-value smoke tests for the Django workspace routes.

These tests intentionally avoid asserting business values. Their job is to catch
broken URL wiring, import errors and template/rendering failures across the
large multi-app workspace before deployment.
"""

from __future__ import annotations

import re

from django.test import TestCase
from django.urls import URLPattern, URLResolver, get_resolver


_CONVERTER_RE = re.compile(r"<(?:(?P<converter>[^:>]+):)?(?P<name>[^>]+)>")


def _concrete_route(route: str) -> str | None:
    """Turn a simple Django route into a harmless GET path.

    Regex-based URL patterns are skipped because they cannot be safely reduced
    to one generic value without knowing their application's contract.
    """
    if route.startswith("^"):
        return None

    def replace(match: re.Match[str]) -> str:
        converter = match.group("converter") or "str"
        return {
            "int": "1",
            "slug": "smoke-test",
            "uuid": "00000000-0000-0000-0000-000000000001",
            "path": "smoke-test",
            "str": "smoke-test",
        }.get(converter, "smoke-test")

    return "/" + _CONVERTER_RE.sub(replace, route).lstrip("/")


def _collect(patterns, prefix: str = "") -> list[str]:
    paths: list[str] = []
    for pattern in patterns:
        if isinstance(pattern, URLResolver):
            child_prefix = prefix + str(pattern.pattern)
            if child_prefix.startswith("^") or "\\" in child_prefix:
                continue
            paths.extend(_collect(pattern.url_patterns, child_prefix))
            continue
        if isinstance(pattern, URLPattern):
            route = _concrete_route(prefix + str(pattern.pattern))
            if route:
                paths.append(route)
    return paths


class WorkspaceRouteSmokeTests(TestCase):
    """Ensure representative GET requests do not crash the Django app."""

    EXTERNAL_CONFIGURATION_ROUTES = {
        "/brokers/connect/",
        "/forgot-password/",
        "/login/",
        "/register/",
        "/reset-password/smoke-test/",
        "/verify-email/",
    }

    def test_workspace_get_routes_do_not_return_server_errors(self):
        paths = sorted(set(_collect(get_resolver().url_patterns)))
        self.assertTrue(paths, "No Django URL patterns were discovered")

        failures: list[str] = []
        for path in paths:
            response = self.client.get(path, follow=False)
            if response.status_code >= 500 and path not in self.EXTERNAL_CONFIGURATION_ROUTES:
                failures.append(f"{response.status_code} GET {path}")

        self.assertFalse(
            failures,
            "Workspace routes returned server errors:\n" + "\n".join(failures),
        )
