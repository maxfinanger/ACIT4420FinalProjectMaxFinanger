"""Regenerate the saved program outputs in docs/examples/ (same text every time).

    python scripts/make_examples.py

The interactive transcript is made by scripts/demo_interactive.py. Bookings go to a temporary
file inside docs/examples that is deleted at the end.
"""
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "examples"
SPEC = ["--destination", "Malaga", "--from", "2026-07-12", "--to", "2026-07-14", "--budget", "50"]
MALAGA = SPEC + ["--max-transfers", "1", "--changeable"]
DEMO_STORE = "docs/examples/demo_bookings.json"


def run(args, seed=None):
    env = dict(os.environ)
    env.pop("BUSBIDDER_SEED", None)
    if seed is not None:
        env["BUSBIDDER_SEED"] = str(seed)
    r = subprocess.run([sys.executable, "main.py", *args], cwd=ROOT, capture_output=True,
                       text=True, encoding="utf-8", env=env)
    return r.stdout + r.stderr


def shown(args, seed=None):
    text = " ".join(f'"{a}"' if " " in a else a for a in args)
    return f"$ {'BUSBIDDER_SEED=%s ' % seed if seed is not None else ''}python main.py {text}\n"


def write(name, text):
    (OUT / name).write_text(text, encoding="utf-8")


def main() -> None:
    write("filter_spec_example.txt", run(MALAGA + ["--preferred-departure", "09:00"]))
    write("filter_no_result.txt", run(["--destination", "Toledo", "--from", "2026-07-12",
                                       "--to", "2026-07-14", "--budget", "3"]))
    write("validation_invalid_file.txt", run(["--offers", "data/offers_invalid.csv"]))
    write("compare_profiles_spec_example.txt", run(MALAGA + ["--compare-profiles"]))
    for profile, pref in (("budget_traveller", "09:00"), ("business_traveller", "08:00"),
                          ("flexible_tourist", "10:00"), ("environment_focused", "09:00")):
        write(f"ranking_{profile}.txt",
              run(MALAGA + ["--preferred-departure", pref, "--profile", profile]))

    store = ROOT / DEMO_STORE
    store.unlink(missing_ok=True)
    steps = [
        (None, MALAGA + ["--book", "1", "--name", "Ana Pérez", "--bookings", DEMO_STORE], 7),
        ("(the same traveller books the same offer again)",
         MALAGA + ["--book", "1", "--name", "ana pérez", "--bookings", DEMO_STORE], 7),
        ("(another traveller books the same offer)",
         MALAGA + ["--book", "OF-1025", "--name", "Eva Larsen", "--bookings", DEMO_STORE], 7),
        ("(a card number typed as a name is refused)",
         MALAGA + ["--book", "1", "--name", "4111 1111 1111 1111", "--bookings", DEMO_STORE], None),
        (None, ["--show-bookings", "--bookings", DEMO_STORE], None),
    ]
    parts = []
    for note, args, seed in steps:
        if note:
            parts.append(f"$ {note}\n")
        parts.append(shown(args, seed) + run(args, seed))
    store.unlink(missing_ok=True)
    write("booking_demo.txt", "\n".join(parts))

    demo = subprocess.run([sys.executable, "scripts/demo_interactive.py"], cwd=ROOT,
                          capture_output=True, text=True, encoding="utf-8")
    write("interactive_session.txt", demo.stdout)


if __name__ == "__main__":
    main()
