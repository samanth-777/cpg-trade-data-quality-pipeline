"""Write an executive alert when a distributor week is outside the variance rule.

A distributor is included when any week exceeds the configured variance
threshold, or when validation recorded a High exception. Findings are grouped
into pricing and volume, timeliness, and master data.
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common  # noqa: E402

BUCKETS = {
    "Pricing/Volume shifts": ("negative_volume", "outlier_volume", "parse_failure"),
    "Timeliness": ("late_file", "missing_weeks"),
    "Master Data Mismatch": ("unmapped_sku", "unmapped_account", "duplicates"),
}


def week_breaches(conn: sqlite3.Connection, threshold: float) -> list[sqlite3.Row]:
    """Return distributor weeks whose absolute variance percent is over the threshold."""
    return conn.execute(
        """
        WITH weeks AS (
            SELECT
                distributor_id,
                week,
                SUM(internal_volume) AS internal_volume,
                SUM(feed_volume) AS feed_volume
            FROM reconciliation
            GROUP BY distributor_id, week
        )
        SELECT
            distributor_id,
            week,
            internal_volume,
            feed_volume,
            CASE
                WHEN ABS(internal_volume) < 0.0001 THEN NULL
                ELSE (feed_volume - internal_volume) / internal_volume
            END AS variance_pct
        FROM weeks
        WHERE (
            ABS(internal_volume) < 0.0001
            AND ABS(feed_volume - internal_volume) >= 0.01
        ) OR (
            ABS(internal_volume) >= 0.0001
            AND ABS((feed_volume - internal_volume) / internal_volume) > ?
        )
        ORDER BY distributor_id, week
        """,
        (threshold,),
    ).fetchall()


def bucket_rows(conn: sqlite3.Connection, checks: tuple[str, ...]) -> list[sqlite3.Row]:
    """Summarize exception checks for one operational bucket."""
    placeholders = ", ".join("?" for _ in checks)
    return conn.execute(
        f"""
        SELECT distributor_id, check_name, COUNT(*) AS events, SUM(row_count) AS rows_affected
        FROM exceptions
        WHERE check_name IN ({placeholders})
        GROUP BY distributor_id, check_name
        ORDER BY distributor_id, check_name
        """,
        checks,
    ).fetchall()


def format_pct(value) -> str:
    """Format a variance ratio, or a blank when the internal week is empty."""
    if value is None:
        return ""
    return f"{float(value):.2%}"


def write_summary(path: Path, threshold: float, breaches, buckets, unit_rows, unknown_rows) -> None:
    """Write the executive markdown summary."""
    distributors = sorted({row["distributor_id"] for row in breaches})
    lines = [
        "# Alert summary",
        "",
        (
            f"A distributor is included when any cleaned week has an absolute variance over {threshold:.0%}, "
            "or when validation recorded a High exception."
        ),
        "",
        "## Weeks over the variance threshold",
        "",
    ]
    if not breaches:
        lines.append("No distributor week is over the threshold.")
        lines.append("")
    else:
        lines.extend(
            [
                "| Distributor | Week | Internal liters | Feed liters | Variance |",
                "| --- | --- | ---: | ---: | ---: |",
            ]
        )
        for row in breaches:
            lines.append(
                f"| {row['distributor_id']} | {row['week']} | {row['internal_volume']:,.2f} | "
                f"{row['feed_volume']:,.2f} | {format_pct(row['variance_pct'])} |"
            )
        lines.append("")
        lines.append(
            "Distributors with at least one week over the threshold: " + ", ".join(distributors) + "."
        )
        lines.append("")
    for title, rows in buckets.items():
        lines.extend([f"## {title}", ""])
        if not rows:
            lines.append("None.")
            lines.append("")
            continue
        lines.extend(
            [
                "| Distributor | Check | Events | Rows |",
                "| --- | --- | ---: | ---: |",
            ]
        )
        for row in rows:
            lines.append(
                f"| {row['distributor_id']} | {row['check_name']} | {int(row['events']):,} | "
                f"{int(row['rows_affected']):,} |"
            )
        lines.append("")
    lines.extend(
        [
            "Unit or format gaps are reconciliation lines, not validation checks.",
            "",
            "| Distributor | Flagged lines | Absolute liters |",
            "| --- | ---: | ---: |",
        ]
    )
    if not unit_rows:
        lines.append("| None | 0 | 0.00 |")
    for row in unit_rows:
        lines.append(
            f"| {row['distributor_id']} | {int(row['lines']):,} | {float(row['absolute_liters']):,.2f} |"
        )
    lines.extend(
        [
            "",
            "Unknown lines on the injected volume-shift weeks:",
            "",
            "| Distributor | Week | Flagged lines | Absolute liters |",
            "| --- | --- | ---: | ---: |",
        ]
    )
    if not unknown_rows:
        lines.append("| None |  | 0 | 0.00 |")
    for row in unknown_rows:
        lines.append(
            f"| {row['distributor_id']} | {row['week']} | {int(row['lines']):,} | "
            f"{float(row['absolute_liters']):,.2f} |"
        )
    lines.append("")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    """Read the latest pipeline tables and write the alert summary."""
    cfg = common.load_config()
    logger = common.get_logger("alerts")
    threshold = float(cfg["thresholds"]["variance_pct"])
    conn = common.connect(common.resolve(cfg["paths"]["database"]))
    try:
        breaches = week_breaches(conn, threshold)
        buckets = {title: bucket_rows(conn, checks) for title, checks in BUCKETS.items()}
        unit_rows = conn.execute(
            """
            SELECT distributor_id, COUNT(*) AS lines, SUM(ABS(variance)) AS absolute_liters
            FROM reconciliation
            WHERE flagged = 1 AND root_cause = 'Unit/Format Issue'
            GROUP BY distributor_id
            ORDER BY distributor_id
            """
        ).fetchall()
        unknown_rows = conn.execute(
            """
            SELECT r.distributor_id, r.week, COUNT(*) AS lines, SUM(ABS(r.variance)) AS absolute_liters
            FROM reconciliation AS r
            INNER JOIN defect_log AS d
                ON d.distributor = r.distributor_id
               AND d.week = r.week
               AND d.defect_type = 'volume_distortion'
            WHERE r.flagged = 1 AND r.root_cause = 'Unknown'
            GROUP BY r.distributor_id, r.week
            ORDER BY r.distributor_id, r.week
            """
        ).fetchall()
    finally:
        conn.close()
    path = common.resolve(cfg["paths"]["alert_summary"])
    write_summary(path, threshold, breaches, buckets, unit_rows, unknown_rows)
    named = sorted({row["distributor_id"] for row in breaches})
    logger.info("Weeks over the threshold: %s", len(breaches))
    logger.info("Distributors over the threshold: %s", ", ".join(named) if named else "none")
    logger.info("Alert summary: %s", path)


if __name__ == "__main__":
    main()
