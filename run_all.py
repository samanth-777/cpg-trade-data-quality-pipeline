"""Run the trade data quality pipeline in order.

Pass --step to run one stage, or --dry-run to list the scripts without
executing them. The active Python interpreter is the one that runs each stage.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))
import common  # noqa: E402

STEPS = [
    ("pull", "src/pull_iowa.py"),
    ("profile", "src/profile.py"),
    ("reference", "src/build_reference.py"),
    ("simulate", "src/simulate_feeds.py"),
    ("ingest", "src/ingest.py"),
    ("validate", "src/validate.py"),
    ("reconcile", "src/reconcile.py"),
    ("excel", "src/build_excel.py"),
]


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse a single step name and the dry-run switch."""
    parser = argparse.ArgumentParser(description="Run the trade data quality pipeline.")
    parser.add_argument(
        "--step",
        choices=[name for name, _path in STEPS],
        help="Run one pipeline step instead of the full sequence.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="List the scripts that would run and do not execute them.",
    )
    return parser.parse_args(argv)


def scripts_for(step: str | None) -> list[str]:
    """Return the script paths for one step, or for the full pipeline."""
    if step is None:
        return [path for _name, path in STEPS]
    return [path for name, path in STEPS if name == step]


def main(argv: list[str] | None = None) -> None:
    """Execute the selected scripts and stop on the first failure."""
    args = parse_args(argv)
    logger = common.get_logger("run_all")
    for step in scripts_for(args.step):
        path = ROOT / step
        if not path.exists():
            logger.error("Missing pipeline step: %s", path)
            sys.exit(1)
        if args.dry_run:
            logger.info("Would run %s", step)
            continue
        logger.info("Running %s", step)
        subprocess.run([sys.executable, str(path)], cwd=ROOT, check=True)
    if args.dry_run:
        logger.info("Dry run finished. No steps were executed.")
    else:
        logger.info("Pipeline finished.")


if __name__ == "__main__":
    main()
