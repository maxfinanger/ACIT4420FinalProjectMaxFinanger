"""Delivery checks: what a user sees contains only task messages, and the program
works from any folder and with odd input."""
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
FORBIDDEN = re.compile(r"Phase|README|docs/|TODO|decision D\d|skeleton|Next:", re.I)
SEARCH = ["--destination", "Malaga", "--from", "2026-07-12", "--to", "2026-07-14",
          "--budget", "50", "--max-transfers", "1", "--changeable"]


def run_main(args, cwd=ROOT, stdin=None, env_extra=None):
    import os
    env = dict(os.environ, BUSBIDDER_SEED="1", **(env_extra or {}))
    return subprocess.run([sys.executable, str(ROOT / "main.py"), *args], cwd=cwd, input=stdin,
                          capture_output=True, text=True, env=env, timeout=120)


@pytest.mark.parametrize("args", [
    [], ["--help"], ["--version"], SEARCH, SEARCH + ["--compare-profiles"],
    SEARCH + ["--profile", "business_traveller", "--preferred-departure", "08:00"],
    SEARCH + ["--weights", "price=100"], ["--show-bookings"],
    ["--destination", "Atlantis", "--from", "2026-07-12", "--to", "2026-07-14", "--budget", "50"],
    ["--offers", "data/offers_invalid.csv"], ["--offers", "nope.csv"],
])
def test_no_development_wording_in_output(args, tmp_path):
    r = run_main(args + ["--bookings", str(tmp_path / "b.json")] if "--show-bookings" in args
                 or "--destination" in args else args)
    assert not FORBIDDEN.search(r.stdout + r.stderr), r.stdout + r.stderr


def test_interactive_has_no_development_wording():
    r = run_main(["--interactive"], stdin="7\n0\n")
    assert r.returncode == 0
    assert not FORBIDDEN.search(r.stdout + r.stderr), r.stdout


def test_works_from_another_folder(tmp_path):
    r = run_main(SEARCH + ["--bookings", str(tmp_path / "b.json")], cwd=tmp_path)
    assert r.returncode == 0 and "RANKING" in r.stdout


@pytest.mark.parametrize("bad", [["--budget", "nan"], ["--budget", "inf"], ["--max-hours", "nan"]])
def test_non_finite_numbers_are_refused(bad):
    r = run_main(["--destination", "Malaga", "--from", "2026-07-12", "--to", "2026-07-14"] + bad)
    assert r.returncode == 2 and "Traceback" not in r.stderr


def test_empty_destination_is_an_error_not_unset():
    r = run_main(["--destination", "", "--from", "2026-07-12", "--to", "2026-07-14", "--budget", "5"])
    assert r.returncode == 2 and "Traceback" not in r.stderr


def test_version():
    assert run_main(["--version"]).stdout.startswith("BusBidder Spain ")


def test_ascii_console_does_not_crash():
    r = run_main(SEARCH, env_extra={"PYTHONIOENCODING": "ascii"})
    assert r.returncode == 0 and "Traceback" not in r.stderr
