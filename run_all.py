"""Run the trade data quality pipeline in order.

Each step is a standalone script under src/. This runner uses the same
Python interpreter that launched it, so the active virtual environment
is the one that executes every stage.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent

STEPS = [
    "src/pull_iowa.py",
    "src/profile.py",
    "src/build_reference.py",
    "src/simulate_feeds.py",
    "src/ingest.py",
    "src/validate.py",
    "src/reconcile.py",
    "src/build_excel.py",
]


def main() -> None:
    """Execute each pipeline script and stop on the first failure."""
    for step in STEPS:
        path = ROOT / step
        if not path.exists():
            print(f"Missing pipeline step: {path}", file=sys.stderr)
            sys.exit(1)
        print(f"\n=== Running {step} ===")
        subprocess.run([sys.executable, str(path)], cwd=ROOT, check=True)
    print("\nPipeline finished.")


if __name__ == "__main__":
    main()
