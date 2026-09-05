#!/usr/bin/env python3
"""Static audit for AlgoBot HTML/CSS/JS assets and template dependencies."""
from __future__ import annotations

import argparse
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
    return sorted(path for path in root.rglob('*' + suffix) if path.is_file())


def text(path: Path) -> str:
    return path.read_text(encoding='utf-8', errors='replace')


def static_path_exists(ref: str) -> bool:
    return (STATIC_ROOT / ref.split('?', 1)[0].lstrip('/')).is_file()


def css_balanced(content: str) -> bool:
    content = re.sub(r'/\*.*?\*/', '', content, flags=re.S)
    depth = 0
    quote = None
    escaped = False
    for char in content:
        if escaped:
            escaped = False
            continue
        if char == '\\':
            escaped = True
            continue
        if quote:
            if char == quote:
                quote = None
            continue
        if char in {"'", '"'}:
            quote = char
        elif char == '{':
            depth += 1
        elif char == '}':
            depth -= 1
            if depth < 0:
                return False
    return depth == 0 and quote is None


def visible_html(content: str) -> str:
    return re.sub(r'<(script|style)\b[^>]*>.*?</\1\s*>', '', content, flags=re.I | re.S)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--strict', action='store_true', help='fail on high-confidence errors')
    args = parser.parse_args()
    findings = []
    templates, css_files, js_files = files(TEMPLATE_ROOT, '.html'), files(STATIC_ROOT, '.css'), files(STATIC_ROOT, '.js')

    for path in templates:
        content = text(path)
        rel = path.relative_to(ROOT).as_posix()
        for ref in STATIC_REF_RE.findall(content):
            if not static_path_exists(ref):
                findings.append(f'ERROR missing static asset: {rel} -> {ref}')
        for target in EXTENDS_RE.findall(content):
            if not (TEMPLATE_ROOT / target).is_file():
                findings.append(f'ERROR missing template parent: {rel} -> {target}')
        for target in INCLUDE_RE.findall(content):
            if not (TEMPLATE_ROOT / target).is_file():
                findings.append(f'ERROR missing template include: {rel} -> {target}')
        for element_id, count in Counter(ID_RE.findall(visible_html(content))).items():
            if count > 1:
                findings.append(f'WARN duplicate literal HTML id {element_id!r} appears {count} times in {rel}')

    for path in css_files:
        if not css_balanced(text(path)):
            findings.append(f'ERROR unbalanced CSS braces: {path.relative_to(ROOT)}')

    hashes = defaultdict(list)
    for path in css_files:
        hashes[hashlib.sha256(path.read_bytes()).hexdigest()].append(str(path.relative_to(ROOT)))
    for paths in hashes.values():
        if len(paths) > 1:
            findings.append('WARN exact duplicate CSS files: ' + ', '.join(paths))

    node = shutil.which('node')
    if node:
        for path in js_files:
            result = subprocess.run([node, '--check', str(path)], cwd=ROOT, text=True, capture_output=True)
            if result.returncode:
                raw = (result.stderr or result.stdout).strip()
                findings.append(f'ERROR JavaScript parse failure: {path.relative_to(ROOT)} -> {raw[-1600:] if raw else "syntax error"}')
    else:
        findings.append('WARN node is unavailable; JavaScript syntax validation was skipped.')

    for path in js_files:
        stripped = re.sub(r'/\*.*?\*/', '', text(path), flags=re.S)
        stripped = re.sub(r'//.*', '', stripped).strip()
        if not stripped:
            findings.append(f'WARN comment-only JS file: {path.relative_to(ROOT)}')

    print('AlgoBot frontend audit')
    print(f'templates={len(templates)} css={len(css_files)} js={len(js_files)} strict={args.strict}')
    for finding in findings:
        print(finding)
    errors = [x for x in findings if x.startswith('ERROR')]
    print(f'errors={len(errors)} warnings={len(findings) - len(errors)}')
    return 1 if args.strict and errors else 0


if __name__ == '__main__':
    sys.exit(main())
