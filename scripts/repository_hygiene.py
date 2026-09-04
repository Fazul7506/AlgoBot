"""Repository hygiene audit for canonical source ownership.

The audit is conservative: exact duplicate source/assets are hard failures,
while likely-unreferenced files are reported for deliberate review. Django
framework entrypoints and migration packages are not treated as ordinary dead
files.
"""

from __future__ import annotations

import hashlib
from collections import defaultdict
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
TRACKED = [Path(p) for p in subprocess.check_output(["git", "ls-files"], cwd=ROOT, text=True).splitlines()]
SKIP_PARTS = {".git", "__pycache__", "node_modules", ".venv", "venv", "staticfiles"}
DUPLICATE_EXTENSIONS = {".css", ".html", ".js", ".py"}


def files_for(ext: str) -> list[Path]:
    return [ROOT / p for p in TRACKED if p.suffix.lower() == ext and not any(part in SKIP_PARTS for part in p.parts)]


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def duplicate_groups(paths: list[Path]) -> list[list[Path]]:
    by_hash: dict[str, list[Path]] = defaultdict(list)
    for path in paths:
        by_hash[digest(path)].append(path)
    return [group for group in by_hash.values() if len(group) > 1]


def load_text_files() -> dict[Path, str]:
    loaded: dict[Path, str] = {}
    for path in TRACKED:
        if any(part in SKIP_PARTS for part in path.parts):
            continue
        full = ROOT / path
        try:
            loaded[path] = full.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
    return loaded


def report_duplicates() -> int:
    failures = 0
    for ext in sorted(DUPLICATE_EXTENSIONS):
        paths = [p for p in files_for(ext) if p.name != "__init__.py"]
        groups = duplicate_groups(paths)
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
    texts = load_text_files()
    print("LIKELY UNREFERENCED CANDIDATES (review before deletion):")

    for ext in (".css", ".html", ".js"):
        for path in files_for(ext):
            rel = path.relative_to(ROOT).as_posix()
            if path.name == "base.html":
                continue
            if not any(token in text for other, text in texts.items() if other != path for token in (path.name, rel)):
                print(f"  {rel}")

    framework_entrypoints = {
        "manage.py", "wsgi.py", "asgi.py", "apps.py", "admin.py", "models.py",
        "migrations.py", "urls.py", "consumers.py", "routing.py", "serializers.py",
    }
    for path in files_for(".py"):
        rel = path.relative_to(ROOT).as_posix()
        if path.name in framework_entrypoints or path.name == "__init__.py" or "migrations" in path.parts:
            continue
        module = rel[:-3].replace("/", ".")
        tokens = (rel, module, path.name)
        if not any(token in text for other, text in texts.items() if other != path for token in tokens):
            print(f"  {rel}")


def report_migration_duplicates() -> int:
    paths = [p for p in files_for(".py") if "migrations" in p.parts and p.name != "__init__.py"]
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
