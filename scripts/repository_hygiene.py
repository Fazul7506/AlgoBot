"""Repository hygiene audit for canonical source ownership.

The audit is intentionally conservative: it reports exact duplicate assets and
likely unreferenced source files, but does not delete framework-discovered
Django entrypoints or migrations automatically.
"""

from __future__ import annotations

import hashlib
import os
import subprocess
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TRACKED = subprocess.check_output(
    ["git", "ls-files"], cwd=ROOT, text=True
).splitlines()

SKIP_PARTS = {".git", "__pycache__", "node_modules", ".venv", "venv"}
DUPLICATE_EXTENSIONS = {".css", ".html", ".js", ".py"}


def files_for(ext: str) -> list[Path]:
    return [
        ROOT / p
        for p in TRACKED
        if Path(p).suffix.lower() == ext
        and not any(part in SKIP_PARTS for part in Path(p).parts)
    ]


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def duplicate_groups(paths: list[Path]) -> list[list[Path]]:
    by_hash: dict[str, list[Path]] = defaultdict(list)
    for path in paths:
        by_hash[digest(path)].append(path)
    return [group for group in by_hash.values() if len(group) > 1]


def git_references(token: str, excluding: Path) -> bool:
    result = subprocess.run(
        ["git", "grep", "-F", "--", token],
        cwd=ROOT,
        text=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    if result.returncode not in (0, 1):
        return False
    # A token can occur only in its own filename/path and still be reported by
    # git grep; callers separately guard against that false positive.
    result = subprocess.run(
        ["git", "grep", "-l", "-F", "--", token],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    return any(Path(line.strip()) != excluding for line in result.stdout.splitlines())


def report_duplicates() -> int:
    failures = 0
    for ext in sorted(DUPLICATE_EXTENSIONS):
        groups = duplicate_groups(files_for(ext))
        if not groups:
            print(f"OK duplicate scan {ext}: no exact duplicates")
            continue
        print(f"DUPLICATE GROUPS {ext}: {len(groups)}")
        for group in groups:
            for path in group:
                print(f"  {path.relative_to(ROOT)}")
        failures += len(groups)
    return failures


def report_unreferenced() -> None:
    print("LIKELY UNREFERENCED CANDIDATES (review before deletion):")
    for ext in (".css", ".html", ".js"):
        for path in files_for(ext):
            rel = path.relative_to(ROOT).as_posix()
            basename = path.name
            if basename in {"base.html"}:
                continue
            if not git_references(basename, path):
                print(f"  {rel}")

    framework_entrypoints = {
        "manage.py", "wsgi.py", "asgi.py", "apps.py", "admin.py",
        "models.py", "migrations.py", "urls.py", "consumers.py",
        "routing.py", "serializers.py",
    }
    for path in files_for(".py"):
        rel = path.relative_to(ROOT).as_posix()
        if path.name in framework_entrypoints or path.name == "__init__.py":
            continue
        if "migrations" in path.parts:
            continue
        module = rel[:-3].replace("/", ".")
        if module.endswith(".__init__"):
            continue
        tokens = {rel, module, path.name}
        if not any(git_references(token, path) for token in tokens):
            print(f"  {rel}")


def report_migration_duplicates() -> int:
    paths = [p for p in files_for(".py") if "migrations" in p.parts]
    groups = duplicate_groups(paths)
    if not groups:
        print("OK migration duplicate scan: no exact duplicate migration files")
        return 0
    print(f"DUPLICATE MIGRATION GROUPS: {len(groups)}")
    for group in groups:
        for path in group:
            print(f"  {path.relative_to(ROOT)}")
    return len(groups)


if __name__ == "__main__":
    print("=== AlgoBot repository hygiene ===")
    duplicate_failures = report_duplicates()
    migration_failures = report_migration_duplicates()
    report_unreferenced()
    if duplicate_failures or migration_failures:
        raise SystemExit(1)
    print("=== hygiene duplicate checks passed ===")
