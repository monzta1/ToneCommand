"""New design is a frontend reset, never a device write."""
from pathlib import Path
import shutil
import subprocess


def test_new_design_ui_behavior():
    node = shutil.which("node")
    assert node, "Node.js is required to validate the shipped UI reset"
    result = subprocess.run(
        [node, "--test", str(Path(__file__).with_name("new_design_behavior.cjs"))],
        capture_output=True, text=True, encoding="utf-8", timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
