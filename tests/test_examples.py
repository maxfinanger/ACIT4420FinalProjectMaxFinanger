"""The saved outputs in docs/examples must be what the program prints today."""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EX = ROOT / "docs" / "examples"


def test_examples_are_up_to_date(tmp_path):
    before = {p.name: p.read_text(encoding="utf-8") for p in EX.glob("*.txt")}
    r = subprocess.run([sys.executable, "scripts/make_examples.py"], cwd=ROOT,
                       capture_output=True, text=True, timeout=300)
    assert r.returncode == 0, r.stderr
    after = {p.name: p.read_text(encoding="utf-8") for p in EX.glob("*.txt")}
    assert before == after, "run: python scripts/make_examples.py"
    assert not (EX / "demo_bookings.json").exists()


def test_examples_have_no_development_wording():
    for p in EX.glob("*.txt"):
        text = p.read_text(encoding="utf-8")
        assert "Phase" not in text and "See README" not in text, p.name


def test_expected_example_files_exist():
    assert len(list(EX.glob("*.txt"))) == 10
