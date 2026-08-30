#!/usr/bin/env python3
"""Static, dependency-free audit for AlgoBot's HTML/CSS/JS surface.

The audit reports high-confidence hygiene findings. It never deletes files
because semantic reachability cannot be proven reliably from static text alone.
"""
from __future__ import annotations

import hashlib
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE_ROOT = ROOT / "templates"
STATIC_ROOT = ROOT / "static"

CSS_REF_RE = re.compile(r"static\s+'([^']+\.css)(?:\?[^']*)?'")
JS_REF_RE = re.compile(r"static\s+'([^']+\.js)(?:\?[^']*)?'")
ID_RE = re.compile(r"\bid=[\"']([^\"']+)[\"']")


def files(root: Path, suffix: str):
    return sorted(path for path in root.rglob(f"*{suffix}") if path.is_file())


def text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def main() -> int:
    findings: list[str] = []
    templates = files(TEMPLATE_ROOT, ".html")
    css_files = files(STATIC_ROOT, ".css")
    js_files = files(STATIC_ROOT, ".js")
    duplicate_ids: defaultdict[str, list[str]] = defaultdict(list)

    for path in templates:
        content = text(path)
        for element_id in ID_RE.findall(content):
            duplicate_ids[element_id].append(str(path.relative_to(ROOT)))

    for element_id, locations in sorted(duplicate_ids.items()):
        counts = Counter(locations)
        for location, count in counts.items():
            if count > 1:
                findings.append(f"WARN duplicate HTML id '{element_id}' appears {count} times in {location}")

    hashes: defaultdict[str, list[str]] = defaultdict(list)
    for path in css_files:
        hashes[hashlib.sha256(path.read_bytes()).hexdigest()].append(str(path.relative_to(ROOT)))
    for paths in hashes.values():
        if len(paths) > 1:
            findings.append("WARN exact duplicate CSS files: " + ", ".join(paths))

    for path in js_files:
        stripped = re.sub(r"/\*.*?\*/", "", text(path), flags=re.S)
        stripped = re.sub(r"//.*", "", stripped).strip()
        if not stripped:
            findings.append(f"WARN comment-only JS file: {path.relative_to(ROOT)}")

    for path in templates:
        content = text(path)
        for label, regex in (("CSS", CSS_REF_RE), ("JS", JS_REF_RE)):
            counts = Counter(regex.findall(content))
            for ref, count in counts.items():
                if count > 1:
                    findings.append(f"WARN duplicate {label} include ({count}x) in {path.relative_to(ROOT)}: {ref}")

    print("AlgoBot frontend audit")
    print(f"templates={len(templates)} css={len(css_files)} js={len(js_files)}")
    if findings:
        print("Findings:")
        for finding in findings:
            print(finding)
    else:
        print("No high-confidence hygiene findings detected.")

    # Findings remain advisory until each candidate is verified against runtime
    # usage. This prevents a static heuristic from breaking production pages.
    return 0


if __name__ == "__main__":
    sys.exit(main())
