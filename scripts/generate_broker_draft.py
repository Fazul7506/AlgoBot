#!/usr/bin/env python3
"""Generate an untrusted broker draft into the allowlisted review directory.

This script never imports or executes generated adapter code and never registers
or enables a broker. Only explicitly allowlisted regular files may be written.
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "deriv_platform.settings")

import django

django.setup()

from apps.brokers.integration_agent import BrokerIntegrationAgent, BrokerIntegrationAgentError
from apps.brokers.integration_validation import validate_broker_draft

SLUG_RE = re.compile(r"^[a-z][a-z0-9_]{1,47}$")
ALLOWED = {"adapter.py", "test_adapter_contract.py", "README.md"}
ROOT = Path("apps/brokers/generated_drafts")


def main() -> int:
    slug = os.environ.get("BROKER_SLUG", "")
    provider = os.environ.get("BROKER_PROVIDER_NAME", "")
    docs = os.environ.get("BROKER_API_DOCS", "")
    if not SLUG_RE.fullmatch(slug):
        print("Invalid broker slug.", file=sys.stderr)
        return 2
    if not provider.strip() or len(provider.strip()) > 120:
        print("Provider name must contain 1-120 characters.", file=sys.stderr)
        return 2
    if len(docs) < 80 or len(docs) > 60_000:
        print("API documentation must contain 80-60000 characters.", file=sys.stderr)
        return 2

    target = ROOT / slug
    if target.exists() or target.is_symlink():
        print("Candidate directory already exists; refusing to overwrite it.", file=sys.stderr)
        return 2

    try:
        draft = BrokerIntegrationAgent().generate(
            broker_slug=slug, provider_name=provider, api_docs=docs
        )
        payload = draft.as_dict()
    except BrokerIntegrationAgentError as exc:
        print(f"Broker draft generation failed: {exc}", file=sys.stderr)
        return 1

    files = payload.get("draft_files")
    if not isinstance(files, list) or not files:
        print("Model returned no draft files.", file=sys.stderr)
        return 1
    seen: set[str] = set()
    for item in files:
        if not isinstance(item, dict) or item.get("path") not in ALLOWED:
            print("Model returned a disallowed draft file.", file=sys.stderr)
            return 1
        path = item["path"]
        if path in seen or not isinstance(item.get("content"), str):
            print("Model returned duplicate paths or invalid file content.", file=sys.stderr)
            return 1
        seen.add(path)
    if "adapter.py" not in seen or "test_adapter_contract.py" not in seen:
        print("Draft must include adapter.py and test_adapter_contract.py.", file=sys.stderr)
        return 1

    report = validate_broker_draft(files)
    if not report.get("passed"):
        print("Static validation failed; generated source will not be written.")
        for error in report.get("errors", []):
            print(f"- {error}")
        return 1

    target.mkdir(parents=True, exist_ok=False)
    try:
        for item in files:
            destination = target / item["path"]
            if destination.parent != target or destination.name not in ALLOWED:
                raise ValueError("Draft path escaped the allowlisted directory.")
            with destination.open("x", encoding="utf-8", newline="\n") as stream:
                stream.write(item["content"])
        summary = (
            f"# {provider} adapter draft\n\n"
            f"Candidate slug: `{slug}`\n\n"
            "This directory contains untrusted AI-generated code. It has not been "
            "registered, enabled, deployed, or executed by the application. "
            "Review every line. Passing static checks is not a security guarantee.\n\n"
            "Before any activation, use a reviewed provider-specific harness against "
            "a verified demo account to test authentication, account identity, market "
            "data, order submission, cancellation/close semantics, fills, and ambiguous "
            "execution reconciliation. Never blindly retry an ambiguous order.\n"
        )
        if "README.md" not in seen:
            with (target / "README.md").open("x", encoding="utf-8", newline="\n") as stream:
                stream.write(summary)
    except (OSError, ValueError) as exc:
        for child in target.iterdir():
            child.unlink(missing_ok=True)
        target.rmdir()
        print(f"Unable to safely write draft: {exc}", file=sys.stderr)
        return 1

    print(f"Generated and statically validated draft at {target}.")
    print("Generated source was not imported or executed in the application process.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
