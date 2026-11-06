import shutil
import subprocess
from pathlib import Path

from django.test import SimpleTestCase


class TerminalPhaseTwoAssetTests(SimpleTestCase):
    def test_terminal_phase_two_asset_parses_before_it_is_served(self):
        asset = Path("static/js/terminal_phase2.js")
        self.assertTrue(asset.is_file())
        source = asset.read_text(encoding="utf-8")
        self.assertNotIn("\\\\n  function context()", source)
        self.assertIn("body:JSON.stringify(", source)
        self.assertIn("authoritative_account_id:ctx.accountId}})},15000)", source)
        node = shutil.which("node")
        if not node:
            self.skipTest("Node.js is not installed in this test environment")
        result = subprocess.run(
            [node, "--check", str(asset)], capture_output=True, text=True, check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr or result.stdout)
