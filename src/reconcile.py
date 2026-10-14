"""Reconcile cleaned distributor feeds to the internal weekly book.

Cleaning keeps one row per week, account, and SKU, maps distributor item
codes back to the internal SKU, and drops negative volumes. The report
compares variance before that cleaning with variance after it.
"""

from __future__ import annotations

import csv
import shutil
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common  # noqa: E402

EXPORT_COLUMNS = [
    "distributor_id",
    "sku_id",
    "week",
    "internal_volume",
    "feed_volume",
    "variance",
    "variance_pct",
    "flagged",
    "root_cause",
]


def split_named_sql(sql_text: str) -> dict[str, str]:
    """Split a SQL file into named script blocks."""
    sections: dict[str, str] = {}
    name = None
    buffer: list[str] = []
    for line in sql_text.splitlines():
        if line.startswith("-- name:"):
            if name and "".join(buffer).strip():
                sections[name] = "\n".join(buffer).strip()
            name = line.split(":", 1)[1].strip()
            buffer = []
        else:
            buffer.append(line)
    if name and "".join(buffer).strip():
        sections[name] = "\n".join(buffer).strip()
    return sections


def export_query(conn: sqlite3.Connection, sql: str, path: Path) -> int:
    """Stream a query to CSV and return the row count."""
    cursor = conn.execute(sql)
    headers = [item[0] for item in cursor.description]
    path.parent.mkdir(parents=True, exist_ok=True)
    written = 0
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(headers)
        while True:
            batch = cursor.fetchmany(50000)
            if not batch:
                break
            writer.writerows(batch)
            written += len(batch)
    return written


def percent(numerator: float, denominator: float) -> str:
    """Format a ratio as a percent with two decimals."""
    if not denominator:
        return "0.00%"
    return f"{(numerator / denominator) * 100:.2f}%"


def write_report(path: Path, summary: sqlite3.Row, causes: list[sqlite3.Row], threshold: float) -> None:
    """Write the before and after variance narrative."""
    internal = float(summary["internal_volume"])
    before = float(summary["feed_before"])
    after = float(summary["feed_after"])
    before_pct = (before - internal) / internal
    after_pct = (after - internal) / internal
    flagged_before = int(summary["flagged_before"])
    flagged_after = int(summary["flagged_after"])
    explained = int(summary["explained_after"])
    explained_before = int(summary["explained_before"])
    lines = [
        "# Reconciliation results",
        "",
        (
            f"Feeds are compared with internal weekly volume at distributor, SKU, and week. "
            f"A line is flagged when the absolute variance percent is over {threshold:.0%}."
        ),
        "",
        "## Before and after cleaning",
        "",
        "Cleaning keeps one copy of a duplicate key, maps distributor SKU codes back to the internal item, and drops negative volumes.",
        "",
        "| Stage | Feed liters | Internal liters | Overall variance | Flagged lines | Explained flagged lines |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
        (
            f"| Before cleaning | {before:,.2f} | {internal:,.2f} | {before_pct:.2%} | "
            f"{flagged_before:,} | {explained_before:,} ({percent(explained_before, flagged_before)}) |"
        ),
        (
            f"| After cleaning | {after:,.2f} | {internal:,.2f} | {after_pct:.2%} | "
            f"{flagged_after:,} | {explained:,} ({percent(explained, flagged_after)}) |"
        ),
        "",
        (
            f"After cleaning, {percent(explained, flagged_after)} of flagged variances have an explained "
            "root cause. Explained causes are Duplicate, Missing Week, Unmapped Code, Unit/Format Issue, and Timing. "
            "Unknown remains on uniform volume shifts and on any other gap the tags do not cover."
        ),
        "",
        "Flagged lines fell after cleaning because duplicate keys were collapsed. Overall variance moved further from zero because those extra copies had been offsetting missing weeks, rejected rows, and downward volume shifts.",
        "",
        "## Root cause of flagged lines after cleaning",
        "",
        "| Root cause | Flagged lines |",
        "| --- | ---: |",
    ]
    for row in causes:
        lines.append(f"| {row['root_cause']} | {int(row['lines']):,} |")
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    """Build the reconciliation, export it, and write the results note."""
    cfg = common.load_config()
    logger = common.get_logger("reconcile")
    threshold = float(cfg["thresholds"]["variance_pct"])
    sql = split_named_sql((common.ROOT / "sql" / "reconcile.sql").read_text(encoding="utf-8"))
    recon_sql = sql["build_recon"].replace("__THRESHOLD__", f"{threshold:.6f}")
    if "__THRESHOLD__" in recon_sql:
        raise RuntimeError("Variance threshold was not applied to the reconciliation SQL")
    conn = common.connect(common.resolve(cfg["paths"]["database"]))
    try:
        conn.execute("PRAGMA temp_store = MEMORY")
        conn.execute("PRAGMA cache_size = -400000")
        logger.info("Aggregating internal and feed volumes")
        conn.executescript(sql["build_aggs"])
        logger.info("Comparing feeds with the internal book")
        conn.executescript(recon_sql)
        summary = conn.execute(
            """
            SELECT
                SUM(internal_volume) AS internal_volume,
                SUM(feed_volume_before) AS feed_before,
                SUM(feed_volume) AS feed_after,
                SUM(flagged_before) AS flagged_before,
                SUM(flagged) AS flagged_after,
                SUM(CASE WHEN flagged = 1 AND root_cause NOT IN ('', 'Unknown') THEN 1 ELSE 0 END) AS explained_after,
                SUM(CASE WHEN flagged_before = 1 AND root_cause_before NOT IN ('', 'Unknown') THEN 1 ELSE 0 END) AS explained_before
            FROM reconciliation
            """
        ).fetchone()
        causes = conn.execute(
            """
            SELECT CASE WHEN root_cause = '' THEN 'Not flagged' ELSE root_cause END AS root_cause,
                   COUNT(*) AS lines
            FROM reconciliation
            WHERE flagged = 1
            GROUP BY root_cause
            ORDER BY lines DESC
            """
        ).fetchall()
        output_dir = common.resolve(cfg["paths"]["output_dir"])
        output_dir.mkdir(parents=True, exist_ok=True)
        recon_path = common.resolve(cfg["paths"]["reconciliation_csv"])
        top_path = common.resolve(cfg["paths"]["top_discrepancies_csv"])
        logger.info("Exporting reconciliation")
        exported = export_query(
            conn,
            f"""
            SELECT {", ".join(EXPORT_COLUMNS)}
            FROM reconciliation
            ORDER BY distributor_id, week, sku_id
            """,
            recon_path,
        )
        top_count = export_query(
            conn,
            f"""
            SELECT {", ".join(EXPORT_COLUMNS)}
            FROM reconciliation
            WHERE flagged = 1
            ORDER BY ABS(variance) DESC
            LIMIT 25
            """,
            top_path,
        )
    finally:
        conn.close()

    report_path = common.resolve(cfg["paths"]["reconciliation_report"])
    write_report(report_path, summary, causes, threshold)
    sample_dir = common.ROOT / "docs" / "sample_output"
    sample_dir.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(top_path, sample_dir / "top_discrepancies.csv")

    internal = float(summary["internal_volume"])
    before = float(summary["feed_before"])
    after = float(summary["feed_after"])
    print("")
    print("Reconciliation summary")
    print(f"Lines compared: {exported:,}")
    print(f"Overall variance before cleaning: {(before - internal) / internal:.2%}")
    print(f"Flagged lines before cleaning: {int(summary['flagged_before']):,}")
    print(f"Overall variance after cleaning: {(after - internal) / internal:.2%}")
    print(f"Flagged lines after cleaning: {int(summary['flagged_after']):,}")
    explained = int(summary["explained_after"])
    flagged = int(summary["flagged_after"])
    print(f"Flagged lines with an explained root cause: {explained:,} ({percent(explained, flagged)})")
    print("Root causes after cleaning:")
    for row in causes:
        print(f"  {row['root_cause']}: {int(row['lines']):,}")
    print(f"Top discrepancies: {top_count}")
    print(f"Report: {report_path}")


if __name__ == "__main__":
    main()
