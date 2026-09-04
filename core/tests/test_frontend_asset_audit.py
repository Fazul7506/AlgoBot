from __future__ import annotations

import hashlib
import re
from pathlib import Path


def test_frontend_asset_inventory(capsys):
    root = Path(__file__).resolve().parents[2]
    roots = {
        "templates": root / "templates",
        "js": root / "static" / "js",
        "css": root / "static" / "css",
    }
    source_files = [
        p for base in (root / "templates", root / "static", root / "apps", root / "core", root / "config")
        if base.exists() for p in base.rglob("*") if p.is_file() and p.suffix in {".html", ".js", ".css", ".py"}
    ]
    text = "\n".join(
        p.read_text(encoding="utf-8", errors="ignore") for p in source_files
    )

    print("FRONTEND_ASSET_AUDIT")
    for label, base in roots.items():
        files = sorted(p for p in base.rglob("*") if p.is_file() and p.suffix in {".html", ".js", ".css"})
        print(f"{label}_count={len(files)}")
        hashes = {}
        for p in files:
            digest = hashlib.sha256(p.read_bytes()).hexdigest()
            hashes.setdefault(digest, []).append(p.relative_to(root).as_posix())
            size = p.stat().st_size
            if size <= 256:
                print(f"SMALL {p.relative_to(root)} bytes={size}")
        for paths in hashes.values():
            if len(paths) > 1:
                print("DUPLICATE " + " | ".join(paths))

        if label == "templates":
            patterns = [
                re.compile(r"(?:render|render_to_string|TemplateResponse)\([^\n]*?[\"']([^\"']+\.html)[\"']"),
                re.compile(r"\{\%\s*(?:extends|include)\s+[\"']([^\"']+)[\"']"),
                re.compile(r"[\"'](?:templates/)?([^\"']+\.html)[\"']"),
            ]
        elif label == "js":
            patterns = [re.compile(r"(?:static/)?js/([^\"'\\) ]+\.js)")]
        else:
            patterns = [re.compile(r"(?:static/)?css/([^\"'\\) ]+\.css)")]
        refs = set()
        for pattern in patterns:
            refs.update(pattern.findall(text))
        for p in files:
            rel = p.relative_to(root).as_posix()
            if label == "templates":
                candidates = {rel, p.name}
                referenced = any(c in refs for c in candidates)
            else:
                referenced = p.name in refs or rel in refs
            if not referenced:
                print(f"UNREFERENCED_CANDIDATE {rel}")

    captured = capsys.readouterr().out
    assert "FRONTEND_ASSET_AUDIT" in captured
