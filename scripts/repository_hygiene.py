"""Repository hygiene audit for canonical source ownership.

Exact duplicate source/assets and known retired runtime references are hard
failures. Dead-code reporting is conservative and understands Python imports,
Django entrypoints, tests, management commands, and migrations.
"""

from __future__ import annotations

import ast
import hashlib
from collections import defaultdict
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
TRACKED = [Path(p) for p in subprocess.check_output(["git", "ls-files"], cwd=ROOT, text=True).splitlines()]
SKIP_PARTS = {".git", "__pycache__", "node_modules", ".venv", "venv", "staticfiles"}
DUPLICATE_EXTENSIONS = {".css", ".html", ".js", ".py"}
RETIRED_RUNTIME_PATTERNS = (
    "mission-control",
    "alert_center",
    "/api/broker-accounts/",
    "normalizeLegacyNavigation",
    "AlgoBotStateManager",
    "apps.ai_engine.calibration",
    "apps.ai_engine.confidence",
    "apps.ai_engine.optimizer",
    "apps.ai_engine.recommendation",
    "apps.ai_engine.regime",
    "trading.ai.",
    "trading.models.",
    "trading.services.",
    "trading.strategies.",
    "from trading import",
    "import trading",
)
FRAMEWORK_ENTRYPOINTS = {
    "manage.py", "wsgi.py", "asgi.py", "apps.py", "admin.py", "models.py",
    "urls.py", "consumers.py", "routing.py", "tasks.py",
}


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
    for rel in TRACKED:
        if any(part in SKIP_PARTS for part in rel.parts):
            continue
        path = ROOT / rel
        try:
            loaded[path] = path.read_text(encoding="utf-8")
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


def module_name(path: Path) -> str:
    return ".".join(path.relative_to(ROOT).with_suffix("").parts)


def resolve_module(name: str) -> Path | None:
    candidate = ROOT.joinpath(*name.split("."))
    py = candidate.with_suffix(".py")
    if py.exists():
        return py
    init = candidate / "__init__.py"
    if init.exists():
        return init
    return None


def resolve_import(source: Path, imported: str, level: int) -> Path | None:
    current = module_name(source).split(".")
    if source.name != "__init__.py":
        current = current[:-1]
    if level:
        base = current[: max(0, len(current) - level + 1)]
        name = ".".join(base + ([imported] if imported else []))
    else:
        name = imported
    return resolve_module(name) if name else None


def python_import_graph() -> dict[Path, set[Path]]:
    graph: dict[Path, set[Path]] = {p: set() for p in files_for(".py")}
    known = set(graph)
    for source in graph:
        try:
            tree = ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
        except (SyntaxError, OSError, UnicodeDecodeError):
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    target = resolve_module(alias.name)
                    if target in known:
                        graph[source].add(target)
            elif isinstance(node, ast.ImportFrom):
                target = resolve_import(source, node.module or "", node.level)
                if target in known:
                    graph[source].add(target)
    return graph


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

    graph = python_import_graph()
    referenced = {target for imports in graph.values() for target in imports}
    for path in files_for(".py"):
        rel = path.relative_to(ROOT).as_posix()
        if path.name == "__init__.py" or "migrations" in path.parts:
            continue
        if path.name in FRAMEWORK_ENTRYPOINTS or "tests" in path.parts or path.name.startswith("test_"):
            continue
        if path not in referenced:
            print(f"  {rel}")


def report_retired_runtime_references() -> int:
    failures = 0
    texts = load_text_files()
    print("RETIRED/CANONICAL RUNTIME VIOLATIONS:")
    for path, text in texts.items():
        if path == Path(__file__) or "migrations" in path.parts or path.suffix.lower() not in DUPLICATE_EXTENSIONS:
            continue
        # The package being retired is intentionally scanned only for deletion
        # completeness; references inside it do not block canonical runtime.
        # References from every other source file remain hard failures.
        if "trading" in path.relative_to(ROOT).parts:
            continue
        for pattern in RETIRED_RUNTIME_PATTERNS:
            if pattern.lower() in text.lower():
                print(f"  {path.relative_to(ROOT)} -> {pattern}")
                failures += 1
                break
    return failures


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
    retired_failures = report_retired_runtime_references()
    report_unreferenced()
    if duplicate_failures or migration_failures or retired_failures:
        raise SystemExit(1)
    print("=== hygiene duplicate and canonical checks passed ===")
