#!/usr/bin/env python3
"""Static, dependency-free audit for AlgoBot's HTML/CSS/JS surface.

The audit intentionally reports high-confidence findings only. It never deletes
files automatically because semantic reachability cannot be proven reliably
from static text alone.
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
CSS_SELECTOR_RE = re.compile(r"(?:^|\})\s*([^@{}][^{}]*)\{")


def files(root: Path, suffix: str):
    return sorted(p for p in root.rglob(f"*{suffix}") if p.is_file())


def text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def main() -> int:
    findings: list[str] = []
    templates = files(TEMPLATE_ROOT, ".html")
    css_files = files(STATIC_ROOT, ".css")
    js_files = files(STATIC_ROOT, ".js")

    referenced_css: Counter[str] = Counter()
    referenced_js: Counter[str] = Counter()
    duplicate_ids: defaultdict[str, list[str]] = defaultdict(list)

    for path in templates:
        content = text(path)
        for ref in CSS_REF_RE.findall(content):
            referenced_css[ref] += 1
        for ref in JS_REF_RE.findall(content):
            referenced_js[ref] += 1
        for element_id in ID_RE.findall(content):
            duplicate_ids[element_id].append(str(path.relative_to(ROOT)))

    for element_id, locations in sorted(duplicate_ids.items()):
        # IDs may repeat across independent templates; flag only duplicates
        # within the same template where they are unambiguously invalid HTML.
        counts = Counter(locations)
        for location, count in counts.items():
            if count > 1:
                findings.append(f"ERROR duplicate HTML id '{element_id}' appears {count} times in {location}")

    # Exact duplicate stylesheet payloads are safe, high-confidence duplication.
    hashes: defaultdict[str, list[str]] = defaultdict(list)
    for path in css_files:
        hashes[hashlib.sha256(path.read_bytes()).hexdigest()].append(str(path.relative_to(ROOT)))
    for paths in hashes.values():
        if len(paths) > 1:
            findings.append("WARN exact duplicate CSS files: " + ", ".join(paths))

    # Comment-only JS is almost always dead scaffolding. Report rather than delete.
    for path in js_files:
        stripped = re.sub(r"/\*.*?\*/", "", text(path), flags=re.S)
        stripped = re.sub(r"//.*", "", stripped).strip()
        if not stripped:
            findings.append(f"WARN comment-only JS file: {path.relative_to(ROOT)}")

    # Detect duplicate static references in the same template.
    for path in templates:
        content = text(path)
        for label, regex in (("CSS", CSS_REF_RE), ("JS", JS_REF_RE)):
            refs = regex.findall(content)
            counts = Counter(refs)
            for ref, count in counts.items():
                if count > 1:
                    findings.append(f"WARN duplicate {label} include ({count}x) in {path.relative_to(ROOT)}: {ref}")

    print("AlgoBot frontend audit")
    print(f"templates={len(templates)} css={len(css_files)} js={len(js_files)}")
    if findings:
        for finding in findings:
            print(finding)
    else:
        print("No high-confidence hygiene findings detected.")

    # Only duplicate IDs are hard errors; advisory hygiene findings should not
    # block deployments until reviewed semantically.
    return 1 if any(line.startswith("ERROR ") for line in findings) else 0


if __name__ == "__main__":
    sys.exit(main())
