"""Static frontend guards for production Django templates and JavaScript assets."""
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE_ROOT = ROOT / "templates"
STATIC_JS = ROOT / "static" / "js"

EXTENDS_RE = re.compile(r"\{\%\s*extends\s+['\"]")
WINDOW_FETCH_ASSIGN_RE = re.compile(r"window\.fetch\s*=")
GENERIC_REQUEST_FAILED_RE = re.compile(r"['\"]Request failed(?:\s*\(|['\"])")


def validate_templates() -> list[str]:
    errors: list[str] = []
    for path in sorted(TEMPLATE_ROOT.rglob("*.html")):
        text = path.read_text(encoding="utf-8")
        match = EXTENDS_RE.search(text)
        if not match:
            continue
        prefix = text[:match.start()]
        stripped = re.sub(r"\{#.*?#\}", "", prefix, flags=re.S).strip()
        if stripped:
            errors.append(f"{path.relative_to(ROOT)}: extends is not the first executable template tag")
    return errors


def validate_static_js() -> list[str]:
    errors: list[str] = []
    fetch_owners: list[str] = []
    for path in sorted(STATIC_JS.rglob("*.js")):
        if path.name.endswith(".min.js"):
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        relative = path.relative_to(ROOT)
        if "<<<<<<<" in text or ">>>>>>>" in text or "=======" in text:
            errors.append(f"{relative}: unresolved merge-conflict marker")
        if WINDOW_FETCH_ASSIGN_RE.search(text):
            fetch_owners.append(str(relative))
        if GENERIC_REQUEST_FAILED_RE.search(text) and str(relative) != "static/js/core/api_client.js":
            errors.append(f"{relative}: generic 'Request failed' message bypasses centralized API error handling")

    if fetch_owners != ["static/js/core/api_client.js"]:
        errors.append("window.fetch must have exactly one owner: static/js/core/api_client.js; found " + ", ".join(fetch_owners))
    return errors


def main() -> int:
    errors = validate_templates() + validate_static_js()
    if errors:
        print("Frontend structure validation failures:")
        print("\n".join(errors))
        return 1
    print("Frontend structure and centralized request-layer validation passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
