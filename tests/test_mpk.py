import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from ttpkgUnpacker.model.mpk import MPK, MPKParseError

REPO_ROOT = Path(__file__).resolve().parents[1]
SAMPLE_PACKAGE = REPO_ROOT / "ttpkgUnpacker" / "js" / "038d897.ttpkg.js"
SAMPLE_GAME_PACKAGE = REPO_ROOT.parent / "sample" / "8862e65.pkg"
MAIN_SCRIPT = REPO_ROOT / "ttpkgUnpacker" / "main.py"


class MPKTests(unittest.TestCase):
    def test_sample_package_parses(self):
        with open(SAMPLE_PACKAGE, "rb") as package_io:
            mpk = MPK.load(package_io)
            self.assertEqual(len(mpk.files), 30)

            first_file = mpk.file(0)
            self.assertEqual(first_file["name"], "app-config.json")
            self.assertEqual(first_file["offset"], 1323)
            self.assertEqual(first_file["data_size"], 1948)
            self.assertTrue(mpk.data(0).startswith(b'{"appId"'))

    @unittest.skipUnless(SAMPLE_GAME_PACKAGE.exists(), "game sample is not available")
    def test_ttks_encrypted_game_package_parses(self):
        with open(SAMPLE_GAME_PACKAGE, "rb") as package_io:
            mpk = MPK.load(package_io)
            self.assertEqual(len(mpk.files), 358)
            self.assertEqual(mpk.package_info["variant"], "ttks-encrypted")
            self.assertEqual(mpk.package_info["header_metadata"]["__ttks"], "a3a12fff342554ec2d66750c42939f9c")

            self.assertEqual(mpk.file(0)["name"], "app-config.json")
            self.assertEqual(mpk.file(59)["name"], "main.js")
            self.assertEqual(mpk.file(356)["name"], "src/project.js")
            self.assertEqual(mpk.file(357)["name"], "src/settings.js")
            self.assertEqual(mpk.file(320)["name"], "res/raw-assets/a5/a5d9af2b-e574-463d-966b-b27c09100cd8.png")
            self.assertEqual(mpk.file(0)["offset"], 20759)
            self.assertEqual(mpk.file(0)["data_size"], 142)

    def test_invalid_magic_raises_clear_error(self):
        from io import BytesIO

        with self.assertRaises(MPKParseError):
            MPK.load(BytesIO(b"NOTP"))

    def test_cli_unpacks_sample_package(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            result = subprocess.run(
                [sys.executable, str(MAIN_SCRIPT), str(SAMPLE_PACKAGE), "-o", temp_dir],
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            unpack_root = Path(temp_dir) / f"{SAMPLE_PACKAGE.name}_unpack"
            self.assertTrue((unpack_root / "app-config.json").exists())
            self.assertTrue((unpack_root / "app.json").exists())
            self.assertTrue((unpack_root / "pages" / "index" / "index.js").exists())
            self.assertTrue((unpack_root / "pages" / "index" / "index.json").exists())
            self.assertTrue((unpack_root / "unpack-report.json").exists())
            self.assertTrue((unpack_root / "unpack-report.md").exists())

    def test_cli_accepts_directory_input(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            result = subprocess.run(
                [sys.executable, str(MAIN_SCRIPT), str(SAMPLE_PACKAGE.parent), "-o", temp_dir],
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            unpack_root = Path(temp_dir) / f"{SAMPLE_PACKAGE.name}_unpack"
            self.assertTrue((unpack_root / "utils" / "utils.js").exists())

    @unittest.skipUnless(SAMPLE_GAME_PACKAGE.exists(), "game sample is not available")
    def test_cli_unpacks_ttks_encrypted_game_package(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            result = subprocess.run(
                [sys.executable, str(MAIN_SCRIPT), str(SAMPLE_GAME_PACKAGE), "-o", temp_dir],
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            unpack_root = Path(temp_dir) / f"{SAMPLE_GAME_PACKAGE.name}_unpack"
            self.assertTrue((unpack_root / "app-config.json").exists())
            self.assertTrue((unpack_root / "main.js").exists())
            self.assertTrue((unpack_root / "src" / "project.js").exists())
            self.assertTrue((unpack_root / "unpack-report.json").exists())
            report = json.loads((unpack_root / "unpack-report.json").read_text(encoding="utf-8"))
            self.assertEqual(report["package_variant"], "ttks-encrypted")
            self.assertEqual(report["file_count"], 358)
            self.assertIn("raw-assets", report["tree"])
            self.assertIsNone(report["recovered_files"]["app_json"])

    @unittest.skipUnless(SAMPLE_GAME_PACKAGE.exists(), "game sample is not available")
    def test_cli_directory_output_avoids_same_name_collisions(self):
        sample_root = SAMPLE_GAME_PACKAGE.parent
        with tempfile.TemporaryDirectory() as temp_dir:
            result = subprocess.run(
                [sys.executable, str(MAIN_SCRIPT), str(sample_root), "-o", temp_dir],
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            unpack_dirs = sorted(path for path in Path(temp_dir).iterdir() if path.is_dir())
            self.assertEqual(len(unpack_dirs), 2)
            for unpack_dir in unpack_dirs:
                self.assertTrue((unpack_dir / "unpack-report.json").exists())


if __name__ == "__main__":
    unittest.main()
