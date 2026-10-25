"""Run AlgoBot's safe, read-only project audit from cron or CI."""
import json

from django.core.management.base import BaseCommand

from apps.brokers.project_audit import run_project_audit


class Command(BaseCommand):
    help = "Scan source files for explicit TODOs, incomplete markers, and debug statements."

    def add_arguments(self, parser):
        parser.add_argument("--json", action="store_true", dest="as_json", help="Print machine-readable JSON.")
        parser.add_argument("--fail-on-findings", action="store_true", help="Exit non-zero when review candidates are found.")

    def handle(self, *args, **options):
        report = run_project_audit()
        if options["as_json"]:
            self.stdout.write(json.dumps(report, indent=2, sort_keys=True))
        else:
            self.stdout.write(
                f"Read-only project audit: {report['files_scanned']} files scanned; "
                f"{report['findings_count']} review candidates."
            )
            for item in report["findings"][:100]:
                self.stdout.write(
                    f"{item['severity'].upper()} {item['path']}:{item['line']} "
                    f"[{item['category']}] {item['description']}: {item['excerpt']}"
                )
            if report["findings_truncated"]:
                self.stdout.write("Output capped at 2,000 findings.")
            for limitation in report["limitations"]:
                self.stdout.write(f"NOTE: {limitation}")
        if options["fail_on_findings"] and report["findings_count"]:
            from django.core.management.base import CommandError
            raise CommandError(f"Audit found {report['findings_count']} review candidates.")
