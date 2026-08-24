"""Compile every Django template so deployment cannot ship a broken template."""
import os
import sys
from pathlib import Path

# When a script is executed as ``python scripts/<name>.py``, Python puts the
# scripts directory first on sys.path.  The Django project package lives at
# the repository root, so make the project root explicit instead of relying
# on the runner's working-directory implementation details.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "deriv_platform.settings")

import django
from django.conf import settings
from django.template import TemplateDoesNotExist, engines
from django.template.exceptions import TemplateSyntaxError


def main() -> int:
    django.setup()
    root = Path(settings.BASE_DIR) / "templates"
    templates = sorted(root.rglob("*.html"))
    if not templates:
        print("No templates found under templates/")
        return 1

    engine = engines["django"]
    failures: list[str] = []
    for path in templates:
        name = path.relative_to(root).as_posix()
        try:
            engine.get_template(name)
        except (TemplateDoesNotExist, TemplateSyntaxError) as exc:
            failures.append(f"{name}: {type(exc).__name__}: {exc}")
        except Exception as exc:  # pragma: no cover - deployment guard
            failures.append(f"{name}: {type(exc).__name__}: {exc}")

    if failures:
        print("Template compilation failures:")
        print("\n".join(failures))
        return 1

    print(f"Compiled {len(templates)} Django templates successfully.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
