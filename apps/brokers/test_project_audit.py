from pathlib import Path
from tempfile import TemporaryDirectory

from apps.brokers.project_audit import run_project_audit


def test_project_audit_reports_review_candidates_without_mutating_files():
    with TemporaryDirectory() as temporary:
        root = Path(temporary)
        source = root / "module.py"
        source.write_text("# TODO: replace stub\nbreakpoint()\n", encoding="utf-8")
        secret = root / ".env"
        secret.write_text("API_KEY=never-read-this", encoding="utf-8")
        before = source.read_bytes()

        report = run_project_audit(root)

        assert report["mode"] == "read_only"
        assert report["files_scanned"] == 1
        assert report["findings_count"] == 2
        assert source.read_bytes() == before
        assert all(item["path"] == "module.py" for item in report["findings"])


def test_project_audit_skips_generated_and_vendor_directories():
    with TemporaryDirectory() as temporary:
        root = Path(temporary)
        generated = root / "node_modules" / "vendor.py"
        generated.parent.mkdir()
        generated.write_text("TODO", encoding="utf-8")

        report = run_project_audit(root)

        assert report["files_scanned"] == 0
        assert report["findings_count"] == 0
