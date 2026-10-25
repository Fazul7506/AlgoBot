"""Read-only repository health checks for the AlgoBot AI manager.

The audit deliberately reports candidates, not facts, for TODOs and placeholders.
It never edits files, executes discovered code, reads secret files, or treats a
catalog entry as proof of live trading readiness.
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EXCLUDED_DIRS = {
    ".git", ".venv", "venv", "node_modules", "__pycache__", "staticfiles",
    "media", "dist", "build", ".next", "coverage",
}
SOURCE_SUFFIXES = {
    ".py", ".html", ".js", ".jsx", ".ts", ".tsx", ".css", ".scss",
    ".json", ".yml", ".yaml", ".toml", ".md", ".sh",
}
SECRET_NAME = re.compile(r"(^|/)(\.env[^/]*|[^/]*(secret|credential|private.key|api[_-]?key|token|password)[^/]*)$", re.I)
PATTERNS = (
    ("todo", re.compile(r"\b(?:TODO|FIXME|XXX)\b", re.I), "review", "Explicit TODO/FIXME marker"),
    ("stub", re.compile(r"\bNotImplementedError\b|\bIMPLEMENT_ME\b|\bYOUR_API_KEY_HERE\b", re.I), "review", "Potential incomplete implementation"),
    ("debug", re.compile(r"\b(?:pdb\.set_trace\(\)|breakpoint\(\)|console\.log\()", re.I), "review", "Debug statement in source"),
)


def iter_source_files(root: Path = ROOT):
    """Yield bounded, secret-safe source paths, skipping generated/vendor trees."""
    count = 0
    for directory, subdirs, filenames in __import__("os").walk(root):
        subdirs[:] = sorted(d for d in subdirs if d not in EXCLUDED_DIRS and not d.startswith(".git"))
        for filename in sorted(filenames):
            path = Path(directory) / filename
            relative = path.relative_to(root).as_posix()
            if path.suffix.lower() not in SOURCE_SUFFIXES or SECRET_NAME.search(relative):
                continue
            if filename.endswith((".min.js", ".map")):
                continue
            yield path
            count += 1
            if count >= 12000:
                return


def run_project_audit(root: Path = ROOT) -> dict:
    """Return a deterministic, read-only source audit report."""
    findings = []
    files_scanned = 0
    for path in iter_source_files(root):
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            continue
        files_scanned += 1
        relative = path.relative_to(root).as_posix()
        for line_number, line in enumerate(text.splitlines(), start=1):
            for category, pattern, severity, description in PATTERNS:
                if pattern.search(line):
                    findings.append({
                        "category": category,
                        "severity": severity,
                        "path": relative,
                        "line": line_number,
                        "description": description,
                        "excerpt": line.strip()[:180],
                    })
    return {
        "status": "completed",
        "mode": "read_only",
        "files_scanned": files_scanned,
        "findings_count": len(findings),
        "findings": findings[:2000],
        "findings_truncated": len(findings) > 2000,
        "limitations": [
            "Static text matches are review candidates, not proof of a defect.",
            "This audit does not run tests, import project modules, contact brokers, or execute code.",
            "Dead-code, security, migration, dependency, and production-readiness checks require separate validation.",
        ],
    }
