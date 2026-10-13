"""Load distributor feeds into a standard staging table.

Each file is read with the feed settings in config.yaml. Dates that do not
match the file's format, and values that are not numeric, go to stg_rejects.
Volume reported in cases is converted back to liters.
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common  # noqa: E402

STANDARD_COLUMNS = [
    "distributor_id",
    "week_start",
    "account_id",
    "sku_id",
    "volume_liters",
    "bottles",
    "dollars",
    "source_file",
    "load_ts",
]
REJECT_COLUMNS = [
    "distributor_id",
    "source_file",
    "row_number",
    "reject_reason",
    "raw_week",
    "raw_account",
    "raw_sku",
    "raw_volume",
    "raw_bottles",
    "raw_dollars",
]


def read_feed(path: Path, spec: dict) -> pd.DataFrame:
    """Read one feed as text so trailing spaces and date strings stay intact."""
    if spec["kind"] == "xlsx":
        frame = pd.read_excel(path, dtype=str, keep_default_na=False)
    else:
        frame = pd.read_csv(
            path,
            sep=spec["delimiter"],
            dtype=str,
            keep_default_na=False,
            encoding="utf-8",
        )
    frame.columns = [str(column).strip() for column in frame.columns]
    return frame


def parse_file(frame: pd.DataFrame, path: Path, spec: dict, crosswalk: pd.DataFrame, load_ts: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Standardize one feed and separate rows that fail parsing."""
    columns = spec["columns"]
    missing = [header for header in columns.values() if header not in frame.columns]
    if missing:
        raise RuntimeError(f"{path.name} is missing columns {missing}")
    working = frame.rename(columns={header: logical for logical, header in columns.items()}).copy()
    if spec["strip_strings"]:
        for column in ("distributor_id", "week_start", "account_id", "sku_id"):
            working[column] = working[column].str.strip()
    parsed_week = pd.to_datetime(working["week_start"], format=spec["date_format"], errors="coerce")
    volume = pd.to_numeric(working["volume"], errors="coerce")
    bottles = pd.to_numeric(working["bottles"], errors="coerce")
    dollars = pd.to_numeric(working["dollars"], errors="coerce")
    reason = pd.Series("", index=working.index, dtype="object")
    reason = reason.mask(parsed_week.isna(), reason + "invalid date; ")
    reason = reason.mask(volume.isna(), reason + "invalid volume; ")
    reason = reason.mask(bottles.isna(), reason + "invalid bottles; ")
    reason = reason.mask(dollars.isna(), reason + "invalid dollars; ")
    reason = reason.mask(working["account_id"].str.strip().eq(""), reason + "blank account; ")
    reason = reason.mask(working["sku_id"].str.strip().eq(""), reason + "blank sku; ")
    reason = reason.str.removesuffix("; ").str.strip()
    failed = reason.ne("")
    rejects = pd.DataFrame(
        {
            "distributor_id": working.loc[failed, "distributor_id"].str.strip(),
            "source_file": path.name,
            "row_number": working.index[failed] + 2,
            "reject_reason": reason.loc[failed],
            "raw_week": working.loc[failed, "week_start"],
            "raw_account": working.loc[failed, "account_id"],
            "raw_sku": working.loc[failed, "sku_id"],
            "raw_volume": working.loc[failed, "volume"],
            "raw_bottles": working.loc[failed, "bottles"],
            "raw_dollars": working.loc[failed, "dollars"],
        }
    )
    good = working.loc[~failed].copy()
    good["account_id"] = good["account_id"].str.strip()
    good["sku_id"] = good["sku_id"].str.strip()
    good["distributor_id"] = good["distributor_id"].str.strip()
    good["week_start"] = parsed_week.loc[good.index].dt.strftime("%Y-%m-%d")
    good["volume_liters"] = volume.loc[good.index] * float(spec["liters_per_reported_unit"])
    good["bottles"] = bottles.loc[good.index]
    good["dollars"] = dollars.loc[good.index]
    good["source_file"] = path.name
    good["load_ts"] = load_ts
    if spec["use_crosswalk"] and not good.empty:
        lookup = crosswalk.rename(columns={"sku_id": "internal_sku", "dist_sku": "sku_id"})
        good = good.merge(lookup, on=["distributor_id", "sku_id"], how="left")
        good["sku_id"] = good["internal_sku"].fillna(good["sku_id"])
        good = good.drop(columns=["internal_sku"])
    loaded = good[STANDARD_COLUMNS].copy()
    return loaded, rejects


def insert_frame(conn, table: str, frame: pd.DataFrame) -> None:
    """Append a frame with executemany in chunks."""
    if frame.empty:
        return
    columns = list(frame.columns)
    sql = f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({', '.join('?' for _ in columns)})"
    values = frame.astype(object).where(pd.notna(frame), None)
    for start in range(0, len(values), 100000):
        chunk = values.iloc[start : start + 100000]
        conn.executemany(sql, list(chunk.itertuples(index=False, name=None)))
    conn.commit()


def prepare_tables(conn) -> None:
    """Replace staging and ingestion log tables."""
    conn.execute("DROP TABLE IF EXISTS stg_feeds")
    conn.execute("DROP TABLE IF EXISTS stg_rejects")
    conn.execute("DROP TABLE IF EXISTS ingestion_log")
    conn.execute(
        """
        CREATE TABLE stg_feeds (
            distributor_id TEXT NOT NULL,
            week_start TEXT NOT NULL,
            account_id TEXT NOT NULL,
            sku_id TEXT NOT NULL,
            volume_liters REAL,
            bottles REAL,
            dollars REAL,
            source_file TEXT NOT NULL,
            load_ts TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE stg_rejects (
            distributor_id TEXT,
            source_file TEXT NOT NULL,
            row_number INTEGER NOT NULL,
            reject_reason TEXT NOT NULL,
            raw_week TEXT,
            raw_account TEXT,
            raw_sku TEXT,
            raw_volume TEXT,
            raw_bottles TEXT,
            raw_dollars TEXT
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE ingestion_log (
            file TEXT NOT NULL,
            rows_read INTEGER NOT NULL,
            rows_loaded INTEGER NOT NULL,
            rows_rejected INTEGER NOT NULL,
            received_date TEXT
        )
        """
    )


def main() -> None:
    """Ingest every configured feed and print a per-file table."""
    cfg = common.load_config()
    logger = common.get_logger("ingest")
    feeds_dir = common.resolve(cfg["paths"]["feeds_dir"])
    manifest = pd.read_csv(common.resolve(cfg["paths"]["file_manifest"]))
    received = dict(zip(manifest["file_name"], manifest["received_date"]))
    crosswalk = pd.read_csv(
        common.resolve(cfg["paths"]["sku_crosswalk"]),
        dtype=str,
        keep_default_na=False,
    )
    load_ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    conn = common.connect(common.resolve(cfg["paths"]["database"]))
    try:
        prepare_tables(conn)
        log_rows = []
        for distributor_id, spec in cfg["feeds"].items():
            paths = sorted(feeds_dir.glob(spec["file_glob"]))
            if not paths:
                raise RuntimeError(f"No files matched {spec['file_glob']} for {distributor_id}")
            for path in paths:
                logger.info("Reading %s", path.name)
                raw = read_feed(path, spec)
                loaded, rejects = parse_file(raw, path, spec, crosswalk, load_ts)
                if len(raw) != len(loaded) + len(rejects):
                    raise RuntimeError(f"{path.name} split {len(loaded)} + {len(rejects)} from {len(raw)}")
                insert_frame(conn, "stg_feeds", loaded[STANDARD_COLUMNS])
                insert_frame(conn, "stg_rejects", rejects[REJECT_COLUMNS])
                log_rows.append(
                    {
                        "file": path.name,
                        "rows_read": len(raw),
                        "rows_loaded": len(loaded),
                        "rows_rejected": len(rejects),
                        "received_date": received.get(path.name),
                    }
                )
                logger.info(
                    "%s read %s, loaded %s, rejected %s",
                    path.name,
                    f"{len(raw):,}",
                    f"{len(loaded):,}",
                    f"{len(rejects):,}",
                )
        log_frame = pd.DataFrame(log_rows)
        insert_frame(conn, "ingestion_log", log_frame)
        conn.execute("CREATE INDEX idx_stg_feeds_dist_week ON stg_feeds (distributor_id, week_start)")
        conn.execute("CREATE INDEX idx_stg_feeds_sku ON stg_feeds (sku_id)")
        conn.execute("CREATE INDEX idx_stg_feeds_account ON stg_feeds (account_id)")
        conn.commit()
    finally:
        conn.close()

    logger.info("Ingestion summary")
    display = log_frame.copy()
    for column in ("rows_read", "rows_loaded", "rows_rejected"):
        display[column] = display[column].map(lambda value: f"{int(value):,}")
    logger.info("\n%s", display.to_string(index=False))
    logger.info(
        f"Total read {log_frame['rows_read'].sum():,}, "
        f"loaded {log_frame['rows_loaded'].sum():,}, "
        f"rejected {log_frame['rows_rejected'].sum():,}"
    )


if __name__ == "__main__":
    main()
