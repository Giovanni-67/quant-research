"""Build a real wheel, extract its installed layout, invoke its declared entry point."""
from pathlib import Path
import configparser
import subprocess
import sys
import tempfile
import unittest
import zipfile

PROJECT = Path(__file__).resolve().parents[1]


class PackagingTests(unittest.TestCase):
    def test_wheel_entry_point_demo_works_outside_checkout(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            # Use an isolated source copy so running tests cannot leave build state
            # in the user's project or race with subsequent development.
            import shutil
            checkout = root / "checkout"
            checkout.mkdir()
            shutil.copyfile(PROJECT / "pyproject.toml", checkout / "pyproject.toml")
            shutil.copytree(PROJECT / "src", checkout / "src", ignore=shutil.ignore_patterns("__pycache__", "*.egg-info"))
            built = subprocess.run([sys.executable, "-m", "pip", "wheel", "--no-deps", "--no-build-isolation",
                                    "--no-index", "--wheel-dir", str(root / "wheels"), str(checkout)],
                                   text=True, capture_output=True)
            self.assertEqual(built.returncode, 0, built.stdout + built.stderr)
            wheel = next((root / "wheels").glob("*.whl"))
            site = root / "installed"
            with zipfile.ZipFile(wheel) as archive:
                for resource in ('dashboard.html','dashboard.css','dashboard.js'):
                    self.assertIn('quant_research/resources/'+resource,archive.namelist())
                archive.extractall(site)
                entries = configparser.ConfigParser()
                name = next(n for n in archive.namelist() if n.endswith("entry_points.txt"))
                entries.read_string(archive.read(name).decode())
            self.assertEqual(entries["console_scripts"]["quant-research"], "quant_research.cli:main")
            code = ('import sys;sys.path.insert(0,sys.argv[1]);'
                    'from quant_research.cli import main;'
                    'sys.argv=["quant-research","demo","--output","runs"];main()')
            smoke = subprocess.run([sys.executable, "-I", "-c", code, str(site)], cwd=root, text=True, capture_output=True)
            self.assertEqual(smoke.returncode, 0, smoke.stdout + smoke.stderr)
            self.assertEqual(len(list((root / "runs").glob("*/report.html"))), 1)


if __name__ == "__main__": unittest.main()
