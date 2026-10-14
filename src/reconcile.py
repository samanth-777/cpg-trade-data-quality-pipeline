"""Reconcile cleaned distributor feeds to the internal weekly book.

Cleaning keeps one row per week, account, and SKU, maps distributor item
codes back to the internal SKU, and drops negative volumes. The report
compares variance before that cleaning with variance after it.
"""

from __future__ import annotations

import csv
import re
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
    """Write absolute variance, flagged rate, and the signed variance note."""
    internal = float(summary["internal_volume"])
    before = float(summary["feed_before"])
    after = float(summary["feed_after"])
    signed_before = (before - internal) / internal
    signed_after = (after - internal) / internal
    abs_before = float(summary["abs_before"]) / internal
    abs_after = float(summary["abs_after"]) / internal
    line_count = int(summary["line_count"])
    flagged_before = int(summary["flagged_before"])
    flagged_after = int(summary["flagged_after"])
    explained = int(summary["explained_after"])
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
        "Total absolute variance percent is the sum of absolute liter gaps divided by internal liters. Flagged rate is flagged lines divided by lines compared.",
        "",
        f"Lines compared: {line_count:,}. Internal liters: {internal:,.2f}.",
        "",
        "| Stage | Absolute variance | Flagged lines | Flagged rate |",
        "| --- | ---: | ---: | ---: |",
        (
            f"| Before cleaning | {abs_before:.2%} | {flagged_before:,} | "
            f"{percent(flagged_before, line_count)} |"
        ),
        (
            f"| After cleaning | {abs_after:.2%} | {flagged_after:,} | "
            f"{percent(flagged_after, line_count)} |"
        ),
        "",
        (
            f"Signed net variance, feed liters minus internal liters divided by internal liters, "
            f"was {signed_before:.2%} before cleaning and {signed_after:.2%} after cleaning."
        ),
        "",
        "## Why signed variance rose",
        "",
        (
            "Missing weeks and unmapped codes are unrecoverable from the feed. "
            "Duplicate copies had been offsetting those gaps, so removing the copies makes the signed shortfall larger. "
            "Absolute variance and the flagged line count fall because those extra copies are no longer counted as gaps."
        ),
        "",
        (
            f"After cleaning, {percent(explained, flagged_after)} of flagged variances have an explained "
            "root cause. Explained causes are Duplicate, Missing Week, Unmapped Code, Unit/Format Issue, and Timing. "
            "Unknown remains on uniform volume shifts and on any other gap the tags do not cover."
        ),
        "",
        "## Root cause of flagged lines after cleaning",
        "",
        "| Root cause | Flagged lines | Share of flagged |",
        "| --- | ---: | ---: |",
    ]
    for row in causes:
        count = int(row["lines"])
        lines.append(f"| {row['root_cause']} | {count:,} | {percent(count, flagged_after)} |")
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def refresh_detection_report(path: Path, distortion_rows: list[sqlite3.Row], threshold: float) -> tuple[int, int, int, int, int]:
    """Add reconciliation-stage detection and an overall rate across both stages."""
    text = path.read_text(encoding="utf-8")
    scorecard_at = text.index("## Scorecard")
    scorecard = text[scorecard_at:]
    table_rows = re.findall(
        r"^\| ([a-z_]+) \| (\d+) \| (\d+) \| ([0-9.]+)% \|$",
        text[:scorecard_at],
        flags=re.M,
    )
    if not table_rows:
        raise RuntimeError(f"Validation detection table is missing from {path}")
    validation_injected = sum(int(injected) for _, injected, _, _ in table_rows)
    validation_caught = sum(int(caught) for _, _, caught, _ in table_rows)
    distortion_validation_caught = 0
    for defect_type, _injected, caught, _rate in table_rows:
        if defect_type == "volume_distortion":
            distortion_validation_caught = int(caught)
    recon_injected = len(distortion_rows)
    recon_caught = sum(int(row["caught"]) for row in distortion_rows)
    overall_caught = validation_caught - distortion_validation_caught + recon_caught
    overall_rate = 100 * overall_caught / validation_injected if validation_injected else 0
    recon_rate = 100 * recon_caught / recon_injected if recon_injected else 0
    validation_rate = 100 * validation_caught / validation_injected if validation_injected else 0
    header = [
        "# Detection results",
        "",
        "Injected events are rows in `defect_log.csv`. Validation and reconciliation are scored separately, then combined.",
        "",
        "## Validation-stage detection",
        "",
        "An event is caught at this stage when validation writes an exception for the same distributor and week.",
        "",
        "| Defect type | Injected | Caught | Detection rate |",
        "| --- | ---: | ---: | ---: |",
    ]
    for defect_type, injected, caught, rate in table_rows:
        header.append(f"| {defect_type} | {int(injected)} | {int(caught)} | {float(rate):.2f}% |")
    header.extend(
        [
            "",
            (
                f"Validation stage caught {validation_caught} of {validation_injected} injected events "
                f"({validation_rate:.2f}%)."
            ),
            "",
            "Volume distortion is not caught here. A uniform 8 to 15 percent move still looks like a normal number, so it does not trip duplicates, mapping, sign, parse, or lateness checks.",
            "",
            "## Reconciliation-stage detection",
            "",
            (
                "Volume distortion is compared after cleaning at distributor and week. "
                "Feed liters and internal liters are summed for that distributor week. "
                f"The event is caught when the absolute variance percent is over {threshold:.0%}."
            ),
            "",
            "| Defect type | Injected | Caught | Detection rate |",
            "| --- | ---: | ---: | ---: |",
            f"| volume_distortion | {recon_injected} | {recon_caught} | {recon_rate:.2f}% |",
            "",
            "## Overall detection",
            "",
            (
                "An event counts as caught when either stage catches it. "
                f"Overall, {overall_caught} of {validation_injected} injected events "
                f"({overall_rate:.2f}%) were caught."
            ),
            "",
            "",
        ]
    )
    path.write_text("\n".join(header) + scorecard, encoding="utf-8")
    return validation_caught, validation_injected, recon_caught, recon_injected, overall_caught


def main() -> None:
    """Build the reconciliation, export it, and write the results note."""
    cfg = common.load_config()
    logger = common.get_logger("reconcile")
    threshold = float(cfg["thresholds"]["variance_pct"])
    sql = split_named_sql((common.ROOT / "sql" / "reconcile.sql").read_text(encoding="utf-8"))
    threshold_sql = f"{threshold:.6f}"
    recon_sql = sql["build_recon"].replace("__THRESHOLD__", threshold_sql)
    distortion_sql = sql["distortion_weeks"].replace("__THRESHOLD__", threshold_sql)
    if "__THRESHOLD__" in recon_sql or "__THRESHOLD__" in distortion_sql:
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
                COUNT(*) AS line_count,
                SUM(internal_volume) AS internal_volume,
                SUM(feed_volume_before) AS feed_before,
                SUM(feed_volume) AS feed_after,
                SUM(ABS(variance_before)) AS abs_before,
                SUM(ABS(variance)) AS abs_after,
                SUM(flagged_before) AS flagged_before,
                SUM(flagged) AS flagged_after,
                SUM(CASE WHEN flagged = 1 AND root_cause NOT IN ('', 'Unknown') THEN 1 ELSE 0 END) AS explained_after,
                SUM(CASE WHEN flagged_before = 1 AND root_cause_before NOT IN ('', 'Unknown') THEN 1 ELSE 0 END) AS explained_before
            FROM reconciliation
            """
        ).fetchone()
        distortion_rows = conn.execute(distortion_sql).fetchall()
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
    detection_path = common.resolve(cfg["paths"]["detection_report"])
    validation_caught, validation_injected, recon_caught, recon_injected, overall_caught = refresh_detection_report(
        detection_path, distortion_rows, threshold
    )
    sample_dir = common.ROOT / "docs" / "sample_output"
    sample_dir.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(top_path, sample_dir / "top_discrepancies.csv")

    internal = float(summary["internal_volume"])
    before = float(summary["feed_before"])
    after = float(summary["feed_after"])
    line_count = int(summary["line_count"])
    flagged_before = int(summary["flagged_before"])
    flagged_after = int(summary["flagged_after"])
    print("")
    print("Reconciliation summary")
    print(f"Lines compared: {exported:,}")
    print(f"Absolute variance before cleaning: {float(summary['abs_before']) / internal:.2%}")
    print(f"Absolute variance after cleaning: {float(summary['abs_after']) / internal:.2%}")
    print(f"Flagged lines before cleaning: {flagged_before:,} ({percent(flagged_before, line_count)})")
    print(f"Flagged lines after cleaning: {flagged_after:,} ({percent(flagged_after, line_count)})")
    print(f"Signed variance before cleaning: {(before - internal) / internal:.2%}")
    print(f"Signed variance after cleaning: {(after - internal) / internal:.2%}")
    explained = int(summary["explained_after"])
    print(f"Flagged lines with an explained root cause: {explained:,} ({percent(explained, flagged_after)})")
    print(f"Validation-stage detection: {validation_caught} of {validation_injected}")
    print(f"Reconciliation-stage volume_distortion: {recon_caught} of {recon_injected}")
    print(f"Overall detection: {overall_caught} of {validation_injected}")
    print("Root causes after cleaning:")
    for row in causes:
        print(f"  {row['root_cause']}: {int(row['lines']):,}")
    print(f"Top discrepancies: {top_count}")
    print(f"Report: {report_path}")


if __name__ == "__main__":
    main()
