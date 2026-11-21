"""The one command that must pass before every push, and the one CI runs.

    python scripts/check.py

Runs lint, format check, type check, data check, tests and the end-to-end pipeline.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PY = sys.executable

STEPS: list[tuple[str, list[str]]] = [
    ("lint", [PY, "-m", "ruff", "check", "."]),
    ("format", [PY, "-m", "ruff", "format", "--check", "."]),
    ("types", [PY, "-m", "mypy"]),
    ("data", [PY, "scripts/check_data.py"]),
    ("tests", [PY, "-m", "pytest", "-q"]),
    ("pipeline", [PY, "-m", "ap.orchestrator.run"]),
]


def main() -> int:
    for name, cmd in STEPS:
        print(f"\n== {name} ==", flush=True)
        if subprocess.run(cmd, cwd=ROOT).returncode != 0:
            print(f"\ncheck FAILED at: {name}", file=sys.stderr)
            if name == "format":
                print("Fix with: python -m ruff format .", file=sys.stderr)
            return 1
    print("\ncheck passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
