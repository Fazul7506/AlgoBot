#!/usr/bin/env python3
"""Generate a conservative, per-tracked-file reference inventory for AlgoBot.

This tool intentionally does not delete files. It combines repository-wide text
references with framework/deployment risk rules and emits a CSV for review. A
zero text-reference count is a candidate signal, never proof of dead code.
"""
from __future__ import annotations
import csv, re, subprocess
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "audit-output" / "repository-file-reference-audit.csv"
SKIP_DIRS = {".git", ".venv", "venv", "node_modules", "__pycache__", ".pytest_cache"}
TEXT_SUFFIXES = {".py", ".html", ".htm", ".js", ".mjs", ".cjs", ".ts", ".tsx", ".jsx", ".css", ".scss", ".json", ".toml", ".ini", ".cfg", ".yml", ".yaml", ".txt", ".md", ".sh", ".ps1", ".sql", ".xml", ".env", ".example"}
DYNAMIC_ROOTS = ("apps/", "config/", "core/", "services/", "urls/", "deriv_platform/", "templates/", "static/", "scripts/", "deploy/", ".github/", "migrations/", "tests/")
HIGH_RISK_NAMES = {"manage.py", "Procfile", "render.yaml", "requirements.txt", "pyproject.toml", "setup.cfg", "tox.ini", "Dockerfile", "Makefile"}


def tracked_files() -> list[str]:
    result = subprocess.run(["git", "ls-files", "-z"], cwd=ROOT, check=True, stdout=subprocess.PIPE)
    return sorted(p.decode() for p in result.stdout.split(b"\0") if p)


def read_text(path: Path) -> str | None:
    if path.suffix.lower() not in TEXT_SUFFIXES and path.name not in HIGH_RISK_NAMES:
        return None
    try:
        data = path.read_bytes()
        if b"\0" in data or len(data) > 2_000_000:
            return None
        return data.decode("utf-8", errors="replace")
    except OSError:
        return None


def main() -> int:
    paths = tracked_files()
    contents: dict[str, str] = {}
    for rel in paths:
        value = read_text(ROOT / rel)
        if value is not None:
            contents[rel] = value
    corpus = "\n".join(f"\n# SOURCE:{name}\n{text}" for name, text in contents.items())
    rows = []
    for rel in paths:
        path = ROOT / rel
        name = path.name
        stem = path.stem
        # Count independent source files containing the path or its filename/stem.
        exact_path_refs = []
        filename_refs = []
        # Cheap corpus prefilter avoids scanning every source for every path.
        if rel in corpus:
            exact_path_refs = [source for source, body in contents.items() if source != rel and rel in body.replace("\\", "/")]
        if name and len(name) >= 4 and name in corpus:
            pattern = re.compile(r"(?<![A-Za-z0-9_.-])" + re.escape(name) + r"(?![A-Za-z0-9_.-])")
            filename_refs = [source for source, body in contents.items() if source != rel and pattern.search(body)]
        if rel.startswith(("apps/", "config/", "core/", "services/", "urls/", "deriv_platform/")) and path.suffix == ".py":
            module = rel[:-3].replace("/", ".")
            if module in corpus:
                module_refs = [source for source, body in contents.items() if source != rel and module in body]
            else:
                module_refs = []
        else:
            module_refs = []
        refs = sorted(set(exact_path_refs + filename_refs + module_refs))
        if rel == "docs/REPOSITORY_DEAD_CODE_AUDIT.md":
            decision, risk, reason = "REMOVE_DOCUMENTATION", "low", "Superseded by generated per-file audit output and PR description; user requested removal after audit."
        elif name in HIGH_RISK_NAMES or rel.startswith((".github/", "config/", "core/", "services/", "urls/", "deploy/", "scripts/", "deriv_platform/", "apps/", "tests/")) or "/tests/" in rel or name.startswith("test_"):
            decision, risk, reason = "RETAIN_REVIEW_REFERENCES", "high", "Framework/runtime/deployment entry point; static text references cannot establish reachability."
        elif rel.endswith(("/migrations/",)) or "/migrations/" in rel or re.search(r"(^|/)migrations?(_|/|\.)", rel):
            decision, risk, reason = "RETAIN_MIGRATION_REVIEW", "critical", "Migration history/schema dependencies require database-state and migration-graph validation."
        elif refs:
            decision, risk, reason = "RETAIN_REFERENCED", "medium", "Found repository text/module references; inspect reference semantics before any consolidation."
        else:
            decision, risk, reason = "CANDIDATE_MANUAL_REVIEW", "unknown", "No static filename/path/module reference found; dynamic imports, framework discovery, external use, or binary/runtime use may exist. Not safe to auto-delete."
        rows.append({"path": rel, "file_type": path.suffix or "[no extension]", "bytes": path.stat().st_size if path.exists() else 0, "exact_path_reference_files": len(set(exact_path_refs)), "filename_reference_files": len(set(filename_refs)), "module_reference_files": len(set(module_refs)), "reference_files": ";".join(refs), "decision": decision, "risk": risk, "decision_basis": reason})
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()), lineterminator="\n")
        writer.writeheader(); writer.writerows(rows)
    counts = Counter(row["decision"] for row in rows)
    print(f"tracked_files={len(paths)} text_sources_scanned={len(contents)} report={OUTPUT.relative_to(ROOT)}")
    for key, value in sorted(counts.items()): print(f"{key}={value}")
    print("NOTE: candidate rows are not deletion approvals; dynamic and external references require manual validation.")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
