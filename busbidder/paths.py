"""Where files are found, so the program works from any folder.

Input files (data, config) are looked for in the current folder first and then in the
project folder. Files the program writes (bookings, logs) go to the current folder when
it has the target folder, otherwise to the project folder.
"""
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def find_input(path) -> Path:
    p = Path(path)
    if p.is_absolute() or p.exists():
        return p
    q = PROJECT_ROOT / p
    return q if q.exists() else p


def place_output(path) -> Path:
    p = Path(path)
    if p.is_absolute() or p.parent.exists():
        return p
    return PROJECT_ROOT / p
