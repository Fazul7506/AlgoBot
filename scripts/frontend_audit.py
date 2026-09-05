#!/usr/bin/env python3
"""Static, dependency-light audit for AlgoBot's HTML/CSS/JS surface.

The audit fails only on high-confidence defects: missing local static assets,
missing template parents/includes, unbalanced CSS braces, or JavaScript that
Node cannot parse. Duplicate IDs/assets remain advisory because templates can
legitimately render repeated fragments at runtime.
"""
from __future__ import annotations

import hashlib
import re
import shutil
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE_ROOT = ROOT / "templates"
STATIC_ROOT = ROOT / "static"

STATIC_REF_RE = re.compile(r"\{%\s*static\s+[\"']([^\"']+)[\"']\s*%\}")
EXTENDS_RE = re.compile(r"\{%\s*extends\s+[\"']([^\"']+)[\"']\s*%\}")
INCLUDE_RE = re.compile(r"\{%\s*include\s+[\"']([^\"']+)[\"']")
ID_RE = re.compile(r"\bid=[\"']([^\"']+)[\"']")


def files(root: Path, suffix: str):
    return sorted(path for path in root.rglob(f"*{suffix}") if path.is_file())


def text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def static_path_exists(ref: str) -> bool:
    clean = ref.split("?", 1)[0].lstrip("/")
    return (STATIC_ROOT / clean).is_file()


def css_braces_balanced(content: str) -> bool:
    content = re.sub(r"/\*.*?\*/", "", content, flags=re.S)
    depth = 0
    quote = None
    escaped = False
    for char in content:
        if escaped:
            escaped = False
            continue
        if char == "\\":
            escaped = True
            continue
        if quote:
            if char == quote:
                quote = None
            continue
        if char in {"'", '"'}:
            quote = char
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth < 0:
                return False
    return depth == 0 and quote is None


def main() -> int:
    findings: list[str] = []
    templates = files(TEMPLATE_ROOT, ".html")
    css_files = files(STATIC_ROOT, ".css")
    js_files = files(STATIC_ROOT, ".js")
    duplicate_ids: defaultdict[str, list[str]] = defaultdict(list)

    for path in templates:
        content = text(path)
        rel = path.relative_to(ROOT).as_posix()
        for element_id in ID_RE.findall(content):
            duplicate_ids[element_id].append(rel)
        for ref in STATIC_REF_RE.findall(content):
            if not static_path_exists(ref):
                findings.append(f"ERROR missing static asset: {rel} -> {ref}")
        for target in EXTENDS_RE.findall(content):
            if not (TEMPLATE_ROOT / target).is_file():
                findings.append(f"ERROR missing template parent: {rel} -> {target}")
        for target in INCLUDE_RE.findall(content):
            if not (TEMPLATE_ROOT / target).is_file():
                findings.append(f"ERROR missing template include: {rel} -> {target}")

    for path in css_files:
        if not css_braces_balanced(text(path)):
            findings.append(f"ERROR unbalanced CSS braces: {path.relative_to(ROOT)}")

    hashes: defaultdict[str, list[str]] = defaultdict(list)
    for path in css_files:
        hashes[hashlib.sha256(path.read_bytes()).hexdigest()].append(str(path.relative_to(ROOT)))
    for paths in hashes.values():
        if len(paths) > 1:
            findings.append("WARN exact duplicate CSS files: " + ", ".join(paths))

    node = shutil.which("node")
    if node:
        for path in js_files:
            result = subprocess.run(
                [node, "--check", str(path)],
                cwd=ROOT,
                text=True,
                capture_output=True,
            )
            if result.returncode:
                detail = (result.stderr or result.stdout).strip().splitlines()[-1] if (result.stderr or result.stdout) else "syntax error"
                findings.append(f"ERROR JavaScript parse failure: {path.relative_to(ROOT)} -> {detail}")
    else:
        print("WARN node is unavailable; JavaScript syntax validation was skipped.")

    for path in js_files:
        stripped = re.sub(r"/\*.*?\*/", "", text(path), flags=re.S)
        stripped = re.sub(r"//.*", "", stripped).strip()
        if not stripped:
            findings.append(f"WARN comment-only JS file: {path.relative_to(ROOT)}")

    for element_id, locations in sorted(duplicate_ids.items()):
        counts = Counter(locations)
        for location, count in counts.items():
            if count > 1:
                findings.append(f"WARN duplicate HTML id '{element_id}' appears {count} times in {location}")

    for path in templates:
        content = text(path)
        for label, regex in (
            ("CSS", re.compile(r"static\s+[\"']([^\"']+\.css)(?:\?[^\"']*)?[\"']")),
            ("JS", re.compile(r"static\s+[\"']([^\"']+\.js)(?:\?[^\"']*)?[\"']")),
        ):
            counts = Counter(regex.findall(content))
            for ref, count in counts.items():
                if count > 1:
                    findings.append(f"WARN duplicate {label} include ({count}x) in {path.relative_to(ROOT)}: {ref}")

    print("AlgoBot frontend audit")
    print(f"templates={len(templates)} css={len(css_files)} js={len(js_files)}")
    errors = [item for item in findings if item.startswith("ERROR")]
    if findings:
        print("Findings:")
        for finding in findings:
            print(finding)
    else:
        print("No static frontend findings detected.")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
