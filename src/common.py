"""Shared helpers for the trade data quality pipeline.

Every script loads paths, thresholds, and the date window from config.yaml
at the repository root. Nothing in the pipeline hardcodes a data path.
"""

from __future__ import annotations

import logging
import sqlite3
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "config.yaml"


def load_config() -> dict:
    """Return the project config as a dictionary."""
    with CONFIG_PATH.open("r", encoding="utf-8") as handle:
        cfg = yaml.safe_load(handle)
    if not isinstance(cfg, dict):
        raise ValueError(f"Config at {CONFIG_PATH} did not parse to a mapping")
    return cfg


def save_config(cfg: dict) -> None:
    """Write config.yaml back, preserving key order."""
    with CONFIG_PATH.open("w", encoding="utf-8") as handle:
        yaml.safe_dump(cfg, handle, sort_keys=False, default_flow_style=False)


def resolve(path_value: str) -> Path:
    """Resolve a config path against the repository root."""
    path = Path(path_value)
    if path.is_absolute():
        return path
    return ROOT / path


def get_logger(name: str) -> logging.Logger:
    """Configure a stream logger from config.yaml and return it."""
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger
    level_name = "INFO"
    log_format = "%(asctime)s %(levelname)s %(name)s %(message)s"
    if CONFIG_PATH.exists():
        block = load_config().get("logging") or {}
        level_name = str(block.get("level", level_name))
        log_format = str(block.get("format", log_format))
    logger.setLevel(getattr(logging, level_name.upper(), logging.INFO))
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter(log_format))
    logger.addHandler(handler)
    logger.propagate = False
    return logger


def connect(db_path: Path) -> sqlite3.Connection:
    """Open SQLite with row access and a few load-friendly pragmas."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def table_count(conn: sqlite3.Connection, table: str) -> int:
    """Return the row count for a table, or 0 if the table is missing."""
    found = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table,),
    ).fetchone()
    if found is None:
        return 0
    return int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
