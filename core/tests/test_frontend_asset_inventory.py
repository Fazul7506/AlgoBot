from __future__ import annotations

import hashlib
import re
from pathlib import Path


def test_inventory_for_cleanup():
    root = Path(__file__).resolve().parents[2]
    source_roots = [root / "templates", root / "static", root / "apps", root / "core", root / "config"]
    sources = [p for base in source_roots if base.exists() for p in base.rglob("*") if p.is_file() and p.suffix in {".html", ".js", ".css", ".py"}]
    corpus = "\n".join(p.read_text(encoding="utf-8", errors="ignore") for p in sources)
    report = []
    for label, base, suffix in (("templates", root / "templates", ".html"), ("js", root / "static" / "js", ".js"), ("css", root / "static" / "css", ".css")):
        files = sorted(p for p in base.rglob("*") if p.is_file() and p.suffix == suffix) if base.exists() else []
        hashes = {}
        for p in files:
            hashes.setdefault(hashlib.sha256(p.read_bytes()).hexdigest(), []).append(p.relative_to(root).as_posix())
            if p.stat().st_size <= 256:
                report.append(f"SMALL {p.relative_to(root)} bytes={p.stat().st_size}")
        for paths in hashes.values():
            if len(paths) > 1:
                report.append("DUPLICATE " + " | ".join(paths))
        if label == "templates":
            refs = set(re.findall(r"(?:extends|include)\s+[\"']([^\"']+\.html)[\"']", corpus))
            refs.update(re.findall(r"(?:render|render_to_string|TemplateResponse)\([^\n]*?[\"']([^\"']+\.html)[\"']", corpus))
            for p in files:
                if p.name not in refs and p.relative_to(root).as_posix() not in refs:
                    report.append(f"UNREFERENCED_CANDIDATE {p.relative_to(root)}")
        else:
            refs = set(re.findall(rf"(?:static/)?(?:{label}/)?([^\"'\\) ]+{re.escape(suffix)})", corpus))
            for p in files:
                if p.name not in refs and p.relative_to(root).as_posix() not in refs:
                    report.append(f"UNREFERENCED_CANDIDATE {p.relative_to(root)}")
    if report:
        raise AssertionError("\n".join(["FRONTEND CLEANUP AUDIT"] + report))
