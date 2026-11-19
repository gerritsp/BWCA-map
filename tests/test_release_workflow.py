import base64
import hashlib
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
VERIFY = ROOT / "deploy" / "verify_csp.py"
RELEASE = ROOT / "deploy" / "release.sh"


class CspVerifierTests(unittest.TestCase):
    def run_verifier(self, html, caddy):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            html_path = directory / "page.html"
            caddy_path = directory / "Caddyfile"
            html_path.write_text(html, encoding="utf-8")
            caddy_path.write_text(caddy, encoding="utf-8")
            return subprocess.run(
                [sys.executable, str(VERIFY), str(html_path), str(caddy_path)],
                check=False,
                capture_output=True,
                text=True,
            )

    def test_accepts_all_inline_script_hashes(self):
        html = '<script src="app.js"></script><script>const safe = true;</script>'
        digest = base64.b64encode(
            hashlib.sha256(b"const safe = true;").digest()
        ).decode("ascii")
        result = self.run_verifier(html, f"script-src 'self' 'sha256-{digest}';")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Verified 1", result.stdout)

    def test_prints_required_hashes_without_a_caddyfile(self):
        with tempfile.TemporaryDirectory() as directory:
            html_path = Path(directory) / "page.html"
            html_path.write_text("<script>ready()</script>", encoding="utf-8")
            result = subprocess.run(
                [sys.executable, str(VERIFY), "--print-hashes", str(html_path)],
                check=False,
                capture_output=True,
                text=True,
            )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertRegex(result.stdout.strip(), r"^'sha256-[A-Za-z0-9+/]+=*'$")

    def test_rejects_a_missing_inline_script_hash(self):
        result = self.run_verifier("<script>changed()</script>", "script-src 'self';")
        self.assertEqual(result.returncode, 1)
        self.assertIn("CSP check failed", result.stderr)
        self.assertIn("sha256-", result.stderr)


class ReleaseScriptTests(unittest.TestCase):
    def test_shell_syntax_and_help(self):
        subprocess.run(["bash", "-n", str(RELEASE)], check=True)
        help_result = subprocess.run(
            ["bash", str(RELEASE), "--help"],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(help_result.returncode, 0, help_result.stderr)
        self.assertIn("deploy/release.sh rollback", help_result.stdout)
        self.assertIn("never invokes sudo", help_result.stdout)

    def test_rollback_swaps_managed_symlinks(self):
        html = "<script>ready()</script>"
        digest = base64.b64encode(
            hashlib.sha256(b"ready()").digest()
        ).decode("ascii")
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            releases = directory / "releases"
            current_release = releases / "current-release"
            previous_release = releases / "previous-release"
            current_release.mkdir(parents=True)
            previous_release.mkdir()
            (current_release / "lake_search.html").write_text(html, encoding="utf-8")
            (previous_release / "lake_search.html").write_text(html, encoding="utf-8")

            web_root = directory / "www" / "bwca"
            web_root.parent.mkdir()
            web_root.symlink_to(current_release)
            previous_link = Path(f"{web_root}.previous")
            previous_link.symlink_to(previous_release)
            caddyfile = directory / "Caddyfile"
            caddyfile.write_text(
                "test.invalid {\n"
                f"    root * {web_root}\n"
                "    header Content-Security-Policy "
                f"\"script-src 'self' 'sha256-{digest}'\"\n"
                "    file_server\n"
                "}\n",
                encoding="utf-8",
            )

            result = subprocess.run(
                [
                    "bash",
                    str(RELEASE),
                    "rollback",
                    "--web-root",
                    str(web_root),
                    "--releases-dir",
                    str(releases),
                    "--caddyfile",
                    str(caddyfile),
                    "--python",
                    sys.executable,
                    "--caddy",
                    "/bin/true",
                ],
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(web_root.resolve(), previous_release.resolve())
            self.assertEqual(previous_link.resolve(), current_release.resolve())


if __name__ == "__main__":
    unittest.main()
