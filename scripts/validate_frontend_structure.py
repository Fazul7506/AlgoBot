"""Static frontend guards for production Django templates and JavaScript assets."""
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE_ROOT = ROOT / "templates"
STATIC_JS = ROOT / "static" / "js"

EXTENDS_RE = re.compile(r"\{\%\s*extends\s+['\"]")
TAG_RE = re.compile(r"\{\%\s*([a-zA-Z_][\w-]*)\b")


def validate_templates() -> list[str]:
    errors: list[str] = []
    for path in sorted(TEMPLATE_ROOT.rglob("*.html")):
        text = path.read_text(encoding="utf-8")
        match = EXTENDS_RE.search(text)
        if not match:
            continue
        prefix = text[:match.start()]
        # Django permits whitespace/comments before extends, but no executable tag.
        stripped = re.sub(r"\{#.*?#\}", "", prefix, flags=re.S).strip()
        if stripped:
            errors.append(
                f"{path.relative_to(ROOT)}: extends is not the first executable template tag"
            )
    return errors


def validate_static_js() -> list[str]:
    errors: list[str] = []
    for path in sorted(STATIC_JS.rglob("*.js")):
        if path.name.endswith(".min.js"):
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        if "<<<<<<<" in text or ">>>>>>>" in text or "=======" in text:
            errors.append(f"{path.relative_to(ROOT)}: unresolved merge-conflict marker")
    return errors


def main() -> int:
    errors = validate_templates() + validate_static_js()
    if errors:
        print("Frontend structure validation failures:")
        print("\n".join(errors))
        return 1
    print("Frontend template ordering and static-JS conflict validation passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
