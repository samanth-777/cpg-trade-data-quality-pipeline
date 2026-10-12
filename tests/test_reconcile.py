"""Unit tests for the reconciliation 5% variance flag."""

from __future__ import annotations

import sqlite3

from pathlib import Path

THRESHOLD = 0.05
SQL_PATH = Path(__file__).resolve().parents[1] / "sql" / "reconcile.sql"


def flag_sql() -> str:
    """Return the after-cleaning flag rule used by sql/reconcile.sql."""
    text = SQL_PATH.read_text(encoding="utf-8")
    start = text.index("END AS flagged_before")
    flagged = text[start:]
    flagged = flagged[flagged.index("CASE"):]
    flagged = flagged[: flagged.index("END AS flagged") + len("END")]
    if "__THRESHOLD__" not in flagged:
        raise AssertionError("The reconciliation flag rule no longer uses __THRESHOLD__")
    return flagged.replace("__THRESHOLD__", f"{THRESHOLD:.6f}")


def flagged_rows(rows: list[tuple]) -> list[sqlite3.Row]:
    """Load distributor, SKU, and week rows and apply the flag rule."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute(
        """
        CREATE TABLE reconciliation (
            distributor_id TEXT,
            sku_id TEXT,
            week TEXT,
            internal_volume REAL,
            feed_volume REAL,
            variance REAL
        )
        """
    )
    conn.executemany(
        """
        INSERT INTO reconciliation (
            distributor_id, sku_id, week, internal_volume, feed_volume, variance
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        rows,
    )
    statement = f"SELECT distributor_id, sku_id, week, {flag_sql()} AS flagged FROM reconciliation"
    found = conn.execute(statement).fetchall()
    conn.close()
    return found


def test_variance_flag_thresholds():
    """4% stays clear, 6% flags, exactly 5% stays clear, and a zero-internal gap flags."""
    rows = flagged_rows(
        [
            ("D01", "100", "2024-01-01", 100.0, 104.0, 4.0),
            ("D01", "200", "2024-01-01", 100.0, 106.0, 6.0),
            ("D02", "300", "2024-01-08", 100.0, 105.0, 5.0),
            ("D03", "ZZ1", "2024-01-15", 0.0, 0.02, 0.02),
            ("D03", "ZZ2", "2024-01-15", 0.0, 0.005, 0.005),
        ]
    )
    by_sku = {row["sku_id"]: row["flagged"] for row in rows}
    assert by_sku["100"] == 0
    assert by_sku["200"] == 1
    assert by_sku["300"] == 0
    assert by_sku["ZZ1"] == 1
    assert by_sku["ZZ2"] == 0
