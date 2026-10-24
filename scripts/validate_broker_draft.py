#!/usr/bin/env python3
"""Blocking static gate for untrusted generated broker adapter drafts."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from apps.brokers.integration_validation import validate_broker_draft


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("draft_dir", type=Path, help="Directory containing adapter.py and optional README/tests")
    args = parser.parse_args()
    root = args.draft_dir.resolve()
    if not root.is_dir():
        print(json.dumps({"passed": False, "errors": ["Draft directory does not exist."], "warnings": []}, indent=2))
        return 2

    files = []
    for path in sorted(root.iterdir()):
        if path.is_symlink() or not path.is_file():
            print(json.dumps({"passed": False, "errors": [f"Draft entry must be a regular non-symlink file: {path.name}"], "warnings": []}, indent=2))
            return 2
        try:
            content = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            print(json.dumps({"passed": False, "errors": [f"Cannot read draft file as UTF-8: {path.name}"], "warnings": []}, indent=2))
            return 2
        files.append({"path": path.name, "content": content})

    report = validate_broker_draft(files)
    print(json.dumps(report, indent=2))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
