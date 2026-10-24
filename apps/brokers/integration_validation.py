"""Static preflight checks for AI-generated broker integration drafts.

This is a defense-in-depth review aid, not a sandbox and not proof of safety.
Never execute generated code solely because this validator passes.
"""
from __future__ import annotations

import ast
import re
from typing import Any

MAX_FILE_CHARS = 100_000
FORBIDDEN_IMPORT_ROOTS = {
    "subprocess", "ctypes", "pickle", "marshal", "pty", "telnetlib", "ftplib",
}
FORBIDDEN_CALLS = {"eval", "exec", "compile", "__import__", "breakpoint"}
SECRET_PATTERNS = (
    re.compile(r"(?i)-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(r"(?i)(?:api[_-]?key|client[_-]?secret|access[_-]?token)\s*[:=]\s*['\"][^'\"]{12,}['\"]"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{24,}\b"),
)


def validate_broker_draft(draft_files: list[dict[str, str]]) -> dict[str, Any]:
    """Return blocking errors and review warnings without importing or executing code."""
    errors: list[str] = []
    warnings: list[str] = []
    files: dict[str, str] = {}

    if not isinstance(draft_files, list) or not draft_files:
        return {"passed": False, "errors": ["No draft files supplied."], "warnings": []}

    for index, item in enumerate(draft_files):
        if not isinstance(item, dict):
            errors.append(f"Draft file #{index + 1} is not an object.")
            continue
        path, source = item.get("path"), item.get("content")
        if path not in {"adapter.py", "test_adapter_contract.py", "README.md"}:
            errors.append(f"Disallowed generated path: {path!r}.")
            continue
        if path in files:
            errors.append(f"Duplicate generated path: {path}.")
            continue
        if not isinstance(source, str) or not source.strip():
            errors.append(f"{path} must contain non-empty text.")
            continue
        if len(source) > MAX_FILE_CHARS:
            errors.append(f"{path} exceeds the {MAX_FILE_CHARS}-character limit.")
            continue
        files[path] = source
        for pattern in SECRET_PATTERNS:
            if pattern.search(source):
                errors.append(f"Possible hard-coded credential detected in {path}; remove it and rotate if real.")

    for path in ("adapter.py", "test_adapter_contract.py"):
        source = files.get(path)
        if source is None:
            if path == "adapter.py":
                errors.append("adapter.py is required.")
            else:
                warnings.append("test_adapter_contract.py is missing.")
            continue
        try:
            tree = ast.parse(source, filename=path)
        except SyntaxError as exc:
            errors.append(f"{path} has a Python syntax error at line {exc.lineno}.")
            continue

        if path == "adapter.py":
            imports_base = False
            adapter_subclass = False
            for node in ast.walk(tree):
                if isinstance(node, (ast.Import, ast.ImportFrom)):
                    names = (
                        [alias.name for alias in node.names]
                        if isinstance(node, ast.Import)
                        else [node.module or ""]
                    )
                    for name in names:
                        root = name.split(".", 1)[0]
                        if root in FORBIDDEN_IMPORT_ROOTS:
                            errors.append(f"Forbidden high-risk import {root!r} in adapter.py.")
                        if isinstance(node, ast.ImportFrom):
                            absolute_base_import = name == "apps.brokers.adapters.base"
                            relative_base_import = name == "base" and node.level == 1
                            if (absolute_base_import or relative_base_import) and any(
                                alias.name == "BrokerAdapter" for alias in node.names
                            ):
                                imports_base = True
                if isinstance(node, ast.Call):
                    if isinstance(node.func, ast.Name) and node.func.id in FORBIDDEN_CALLS:
                        errors.append(f"Forbidden dynamic execution call {node.func.id!r} in adapter.py.")
                    if isinstance(node.func, ast.Attribute) and node.func.attr in {"system", "popen", "remove", "unlink", "rmtree"}:
                        errors.append(f"Potentially unsafe call {node.func.attr!r} in adapter.py.")
                if isinstance(node, ast.ClassDef):
                    if node.name.endswith("Adapter") and any(
                        (isinstance(base, ast.Name) and base.id == "BrokerAdapter")
                        or (isinstance(base, ast.Attribute) and base.attr == "BrokerAdapter")
                        for base in node.bases
                    ):
                        adapter_subclass = True
            if not imports_base:
                errors.append("adapter.py must import BrokerAdapter from apps.brokers.adapters.base.")
            if not adapter_subclass:
                errors.append("adapter.py must define an *Adapter class inheriting BrokerAdapter.")
        else:
            # Contract test files are reviewed as source, never imported here.
            if any(isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                   and node.func.id in FORBIDDEN_CALLS for node in ast.walk(tree)):
                errors.append("test_adapter_contract.py contains a forbidden dynamic execution call.")

    if "README.md" not in files:
        warnings.append("README.md is missing; document auth setup, scopes, and sandbox limitations.")
    return {"passed": not errors, "errors": errors, "warnings": warnings}
