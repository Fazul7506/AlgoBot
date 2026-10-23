#!/usr/bin/env python3
"""Generate a conservative per-file reference inventory for AlgoBot.

Usage: python scripts/repository_file_audit.py [--output audit-output/repository-file-reference-audit.csv]
This is a candidate detector, not an automatic deletion tool. Django, Celery,
templates, migrations, deployment and externally invoked files need runtime-aware
review before removal.
"""
from __future__ import annotations

import argparse
import csv
import re
import subprocess
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEXT_SUFFIXES = {
    ".py", ".html", ".htm", ".js", ".mjs", ".cjs", ".ts", ".tsx", ".jsx",
    ".css", ".scss", ".json", ".toml", ".ini", ".cfg", ".yml", ".yaml",
    ".txt", ".md", ".sh", ".ps1", ".sql", ".xml", ".env", ".example",
}
RUNTIME_NAMES = {
    "manage.py", "Procfile", "render.yaml", "requirements.txt", "Dockerfile",
    "Makefile", "pyproject.toml", "setup.cfg", "tox.ini",
}


def tracked_paths() -> list[str]:
    result = subprocess.run(
        ["git", "ls-files", "-z"], cwd=ROOT, check=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    return sorted(p.decode() for p in result.stdout.split(b"\0") if p)


def source_text(path: Path) -> str | None:
    if path.suffix.lower() not in TEXT_SUFFIXES and path.name not in RUNTIME_NAMES:
        return None
    try:
        data = path.read_bytes()
        if b"\0" in data or len(data) > 2_000_000:
            return None
        return data.decode("utf-8", errors="replace")
    except OSError:
        return None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="audit-output/repository-file-reference-audit.csv")
    args = parser.parse_args()
    paths = tracked_paths()
    sources = {p: value for p in paths if (value := source_text(ROOT / p)) is not None}
    corpus = "\n".join(f"\n# SOURCE:{name}\n{text}" for name, text in sources.items())
    rows = []
    for rel in paths:
        path = ROOT / rel
        name = path.name
        exact_refs: list[str] = []
        filename_refs: list[str] = []
        module_refs: list[str] = []
        if rel in corpus:
            exact_refs = [s for s, body in sources.items() if s != rel and rel in body.replace("\\", "/")]
        if len(name) >= 4 and name in corpus:
            pattern = re.compile(r"(?<![A-Za-z0-9_.-])" + re.escape(name) + r"(?![A-Za-z0-9_.-])")
            filename_refs = [s for s, body in sources.items() if s != rel and pattern.search(body)]
        if rel.endswith(".py") and rel.startswith(("apps/", "config/", "deriv_platform/")):
            module = rel[:-3].replace("/", ".")
            if module in corpus:
                module_refs = [s for s, body in sources.items() if s != rel and module in body]
        refs = sorted(set(exact_refs + filename_refs + module_refs))
        if "/migrations/" in rel or rel.startswith("migrations/"):
            decision, risk, basis = "RETAIN_MIGRATION_REVIEW", "critical", "Migration graph and deployed database state must be checked."
        elif name in RUNTIME_NAMES or rel.startswith((".github/", "config/", "deriv_platform/", "apps/")):
            decision, risk, basis = "RETAIN_RUNTIME_REVIEW", "high", "Framework, deployment, dynamic import, task, URL or discovery entry point."
        elif refs:
            decision, risk, basis = "RETAIN_REFERENCED", "medium", "Static path/name/module references found; confirm semantic reachability."
        else:
            decision, risk, basis = "CANDIDATE_MANUAL_REVIEW", "unknown", "No static references found; not proof of dead code or safe deletion."
        rows.append({
            "path": rel,
            "bytes": path.stat().st_size if path.exists() else 0,
            "exact_path_reference_files": len(set(exact_refs)),
            "filename_reference_files": len(set(filename_refs)),
            "module_reference_files": len(set(module_refs)),
            "reference_files": ";".join(refs),
            "decision": decision,
            "risk": risk,
            "decision_basis": basis,
        })
    output = (ROOT / args.output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    counts = Counter(row["decision"] for row in rows)
    print(f"Tracked paths: {len(paths)}; text sources scanned: {len(sources)}")
    for decision, count in sorted(counts.items()):
        print(f"{decision}: {count}")
    print(f"Report: {output.relative_to(ROOT)}")
    print("Candidates require manual framework, runtime, deployment and data checks; no files are deleted.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
