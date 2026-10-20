"""Entry point:  python main.py   (see  python main.py --help)"""
import sys

from busbidder.cli import run


def _tolerate_unprintable_characters() -> None:
    """A console that cannot show a character prints '?' instead of crashing."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")
        except (AttributeError, ValueError):
            pass


if __name__ == "__main__":
    _tolerate_unprintable_characters()
    raise SystemExit(run())
