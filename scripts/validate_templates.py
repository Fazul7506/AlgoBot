"""Compile every Django template so deployment cannot ship a broken template."""
import os
from pathlib import Path

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
