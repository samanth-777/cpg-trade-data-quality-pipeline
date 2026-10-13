"""Build internal master data and the weekly book of record.

Store names, item descriptions, and counties keep their most frequent
non-blank value. dim_calendar covers the configured date window. internal_weekly
is the source of truth at week, account, and SKU, net of return lines.
"""

from __future__ import annotations

import csv
import sqlite3
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common  # noqa: E402


def split_named_sql(sql_text: str) -> list[tuple[str, str]]:
    """Split a SQL file into named script blocks."""
    sections: list[tuple[str, str]] = []
    name = None
    buffer: list[str] = []
    for line in sql_text.splitlines():
        if line.startswith("-- name:"):
            if name and "".join(buffer).strip():
                sections.append((name, "\n".join(buffer).strip()))
            name = line.split(":", 1)[1].strip()
            buffer = []
        else:
            buffer.append(line)
    if name and "".join(buffer).strip():
        sections.append((name, "\n".join(buffer).strip()))
    return sections


def parse_iso_date(value: str) -> date:
    """Parse a YYYY-MM-DD config date."""
    return datetime.strptime(value, "%Y-%m-%d").date()


def build_calendar(conn: sqlite3.Connection, start: date, end: date) -> int:
    """Load one row per day with ISO week, Monday week start, month, and quarter."""
    conn.execute("DROP TABLE IF EXISTS dim_calendar")
    conn.execute(
        """
        CREATE TABLE dim_calendar (
            date TEXT PRIMARY KEY,
            iso_week TEXT NOT NULL,
            week_start TEXT NOT NULL,
            month TEXT NOT NULL,
            quarter TEXT NOT NULL
        )
        """
    )
    rows = []
    cursor = start
    while cursor <= end:
        iso = cursor.isocalendar()
        week_start = cursor - timedelta(days=cursor.weekday())
        quarter = ((cursor.month - 1) // 3) + 1
        rows.append(
            (
                cursor.isoformat(),
                f"{iso.year}-W{iso.week:02d}",
                week_start.isoformat(),
                f"{cursor.year}-{cursor.month:02d}",
                f"{cursor.year}Q{quarter}",
            )
        )
        cursor += timedelta(days=1)
    conn.executemany(
        """
        INSERT INTO dim_calendar (date, iso_week, week_start, month, quarter)
        VALUES (?, ?, ?, ?, ?)
        """,
        rows,
    )
    conn.execute("CREATE INDEX idx_dim_calendar_week ON dim_calendar (week_start)")
    conn.commit()
    return len(rows)


def export_table(conn: sqlite3.Connection, table: str, path: Path) -> int:
    """Write a SQLite table to CSV and return the data row count."""
    cursor = conn.execute(f"SELECT * FROM {table}")
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


def scalar(conn: sqlite3.Connection, sql: str) -> int:
    """Return one integer query result."""
    return int(conn.execute(sql).fetchone()[0])


def main() -> None:
    """Create the reference tables, export them, and print a summary."""
    cfg = common.load_config()
    logger = common.get_logger("build_reference")
    db_path = common.resolve(cfg["paths"]["database"])
    sql_path = common.ROOT / "sql" / "reference.sql"
    reference_dir = common.resolve(cfg["paths"]["reference_dir"])
    reference_dir.mkdir(parents=True, exist_ok=True)
    start = parse_iso_date(cfg["date_range"]["start"])
    end = parse_iso_date(cfg["date_range"]["end"])

    conn = common.connect(db_path)
    try:
        conn.execute("PRAGMA temp_store = MEMORY")
        conn.execute("PRAGMA cache_size = -200000")
        conn.execute("PRAGMA synchronous = OFF")
        for name, script in split_named_sql(sql_path.read_text(encoding="utf-8")):
            logger.info("Building %s", name)
            conn.executescript(script)
            logger.info("%s has %s rows", name, f"{common.table_count(conn, name):,}")
        logger.info("Building dim_calendar")
        calendar_rows = build_calendar(conn, start, end)
        logger.info("dim_calendar has %s rows", f"{calendar_rows:,}")
        conn.execute("PRAGMA synchronous = NORMAL")
        conn.commit()

        orphan_accounts = scalar(
            conn,
            """
            SELECT COUNT(*) FROM (
                SELECT account_id FROM internal_weekly
                EXCEPT
                SELECT account_id FROM dim_account
            )
            """,
        )
        orphan_skus = scalar(
            conn,
            """
            SELECT COUNT(*) FROM (
                SELECT sku_id FROM internal_weekly
                EXCEPT
                SELECT sku_id FROM dim_sku
            )
            """,
        )
        if orphan_accounts or orphan_skus:
            raise RuntimeError(
                f"Weekly rows point at {orphan_accounts} unknown accounts "
                f"and {orphan_skus} unknown SKUs"
            )
        multi_desc = scalar(
            conn,
            """
            SELECT COUNT(*) FROM (
                SELECT itemno
                FROM source_sales
                GROUP BY itemno
                HAVING COUNT(DISTINCT im_desc) > 1
            )
            """,
        )
        multi_name = scalar(
            conn,
            """
            SELECT COUNT(*) FROM (
                SELECT store
                FROM source_sales
                GROUP BY store
                HAVING COUNT(DISTINCT name) > 1
            )
            """,
        )
        exports = {}
        for table in ("dim_sku", "dim_account", "dim_territory", "dim_calendar", "internal_weekly"):
            target = reference_dir / f"{table}.csv"
            count = export_table(conn, table, target)
            exports[table] = (count, target.stat().st_size)
            logger.info("Wrote %s (%s rows)", target.name, f"{count:,}")
    finally:
        conn.close()

    logger.info("Reference table summary")
    logger.info("SKUs where the description was chosen from multiple values: %s", f"{multi_desc:,}")
    logger.info("Accounts where the name was chosen from multiple spellings: %s", f"{multi_name:,}")
    for table, (count, size) in exports.items():
        logger.info("%s: %s rows, %.2f MB", table, f"{count:,}", size / (1024 * 1024))


if __name__ == "__main__":
    main()
