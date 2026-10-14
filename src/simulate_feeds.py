"""Build simulated distributor feeds from the internal weekly book.

Counties are assigned to eight distributors so volume is balanced. Each
distributor gets its own file layout. Defects are injected with the
configured random seed and written to the defect log.
"""

from __future__ import annotations

import math
import random
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import xlsxwriter

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common  # noqa: E402

DISTRIBUTORS = [f"D{i:02d}" for i in range(1, 9)]


def assign_distributors(conn, reference_dir: Path) -> pd.DataFrame:
    """Give each county to the distributor with the least volume so far."""
    counties = pd.read_sql_query(
        """
        SELECT a.county, t.territory_id, ROUND(SUM(w.volume_liters), 4) AS volume_liters
        FROM internal_weekly AS w
        INNER JOIN dim_account AS a ON a.account_id = w.account_id
        INNER JOIN dim_territory AS t ON t.territory_id = a.territory_id
        GROUP BY a.county, t.territory_id
        ORDER BY volume_liters DESC, a.county
        """,
        conn,
    )
    loads = {dist: 0.0 for dist in DISTRIBUTORS}
    assigned = []
    for row in counties.itertuples(index=False):
        distributor = min(loads, key=lambda dist: (loads[dist], dist))
        loads[distributor] += float(row.volume_liters)
        assigned.append(
            {
                "distributor_id": distributor,
                "territory_id": row.territory_id,
                "county": row.county,
                "volume_liters": float(row.volume_liters),
            }
        )
    mapping = pd.DataFrame(assigned)
    conn.execute("DROP TABLE IF EXISTS distributor_map")
    mapping.to_sql("distributor_map", conn, index=False)
    conn.execute("CREATE INDEX idx_distributor_map_county ON distributor_map (county)")
    conn.commit()
    target = reference_dir / "distributor_map.csv"
    mapping.to_csv(target, index=False)
    return mapping


def week_lists(conn) -> dict[str, list[str]]:
    """Return sorted week starts present for each distributor."""
    frame = pd.read_sql_query(
        """
        SELECT m.distributor_id, w.week_start
        FROM internal_weekly AS w
        INNER JOIN dim_account AS a ON a.account_id = w.account_id
        INNER JOIN distributor_map AS m ON m.county = a.county
        GROUP BY m.distributor_id, w.week_start
        ORDER BY m.distributor_id, w.week_start
        """,
        conn,
    )
    return {
        dist: group["week_start"].tolist()
        for dist, group in frame.groupby("distributor_id", sort=True)
    }


def load_distributor(conn, distributor_id: str) -> pd.DataFrame:
    """Load one distributor's week, account, and SKU book."""
    frame = pd.read_sql_query(
        """
        SELECT
            w.week_start,
            w.account_id,
            w.sku_id,
            w.volume_liters,
            w.bottles,
            w.dollars
        FROM internal_weekly AS w
        INNER JOIN dim_account AS a ON a.account_id = w.account_id
        INNER JOIN distributor_map AS m ON m.county = a.county
        WHERE m.distributor_id = ?
        """,
        conn,
        params=(distributor_id,),
    )
    frame["account_id"] = frame["account_id"].astype(str)
    frame["sku_id"] = frame["sku_id"].astype(str)
    frame["week_start"] = frame["week_start"].astype(str)
    return frame


def choose_missing_weeks(weeks: list[str], rng: random.Random, sim: dict) -> list[str]:
    """Pick a consecutive block of weeks to drop."""
    length = rng.randint(int(sim["missing_week_min"]), int(sim["missing_week_max"]))
    start = rng.randrange(0, len(weeks) - length + 1)
    return weeks[start : start + length]


def choose_shifts(available: dict[str, list[str]], rng: random.Random, sim: dict) -> dict[tuple[str, str], float]:
    """Pick distributor weeks and a scale factor 8 to 15 percent up or down."""
    pairs = [(dist, week) for dist, weeks in available.items() for week in weeks]
    picked = rng.sample(pairs, int(sim["volume_shift_events"]))
    shifts = {}
    for distributor_id, week in picked:
        direction = rng.choice([-1, 1])
        magnitude = rng.uniform(float(sim["volume_shift_min"]), float(sim["volume_shift_max"]))
        shifts[(distributor_id, week)] = 1 + direction * magnitude
    return shifts


def sample_positions(rng: random.Random, count: int, rate: float) -> list[int]:
    """Choose a deterministic sample of row positions."""
    wanted = int(round(count * rate))
    if wanted <= 0:
        raise RuntimeError(f"Sample rate {rate} produced no rows from {count}")
    return rng.sample(range(count), wanted)


def log_flag(records: list[dict], distributor_id: str, frame: pd.DataFrame, flag: str, defect_type: str) -> None:
    """Append one defect row per week for rows where flag is true."""
    grouped = frame.loc[frame[flag]].groupby("week_start", sort=True).size()
    for week, rows in grouped.items():
        records.append(
            {
                "distributor": distributor_id,
                "week": week,
                "defect_type": defect_type,
                "rows_affected": int(rows),
            }
        )


def python_value(value):
    """Convert pandas or numpy scalars to values xlsxwriter can write."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    if hasattr(value, "item"):
        return value.item()
    return value


def write_delimited(frame: pd.DataFrame, path: Path, delimiter: str) -> None:
    """Write a CSV or pipe file."""
    frame.to_csv(path, index=False, sep=delimiter)


def write_xlsx(frame: pd.DataFrame, path: Path) -> None:
    """Write one Excel file in constant memory mode."""
    workbook = xlsxwriter.Workbook(path, {"constant_memory": True})
    sheet = workbook.add_worksheet("Weekly")
    for column, name in enumerate(frame.columns):
        sheet.write(0, column, name)
    for row_number, row in enumerate(frame.itertuples(index=False, name=None), start=1):
        sheet.write_row(row_number, 0, [python_value(value) for value in row])
    workbook.close()


def render_feed(frame: pd.DataFrame, distributor_id: str, spec: dict, sim: dict) -> pd.DataFrame:
    """Turn the internal grain into the distributor's columns and units."""
    unit = float(spec["liters_per_reported_unit"])
    dates = pd.to_datetime(frame["week_start"])
    rendered_dates = dates.dt.strftime(spec["date_format"])
    if "is_mixed" in frame.columns and bool(frame["is_mixed"].any()):
        alternate = dates.dt.strftime(sim["mixed_date_format"])
        rendered_dates = rendered_dates.where(~frame["is_mixed"].to_numpy(), alternate)
    accounts = frame["account_id"].astype(str)
    skus = frame["sku_out"].astype(str)
    if spec["use_crosswalk"]:
        accounts = accounts + "   "
        skus = skus + "  "
    columns = spec["columns"]
    output = pd.DataFrame(
        {
            columns["distributor_id"]: distributor_id,
            columns["week_start"]: rendered_dates,
            columns["account_id"]: accounts,
            columns["sku_id"]: skus,
            columns["volume"]: frame["volume_liters"] / unit,
            columns["bottles"]: frame["bottles"].round().astype(int),
            columns["dollars"]: frame["dollars"].round(2),
        }
    )
    return output


def write_feed_files(frame: pd.DataFrame, distributor_id: str, spec: dict, feeds_dir: Path, sim: dict) -> list[tuple[Path, int]]:
    """Write one distributor feed, splitting Excel files that would pass 1M rows."""
    kind = spec["kind"]
    written = []
    if kind == "xlsx":
        max_rows = int(sim["xlsx_max_rows"])
        parts = max(1, math.ceil(len(frame) / max_rows))
        for index in range(parts):
            chunk = frame.iloc[index * max_rows : (index + 1) * max_rows]
            if parts == 1:
                path = feeds_dir / f"{distributor_id}_weekly.xlsx"
            else:
                path = feeds_dir / f"{distributor_id}_weekly_part{index + 1:02d}.xlsx"
            write_xlsx(chunk, path)
            written.append((path, len(chunk)))
        return written
    suffix = ".txt" if spec["delimiter"] == "|" else ".csv"
    path = feeds_dir / f"{distributor_id}_weekly{suffix}"
    write_delimited(frame, path, spec["delimiter"])
    written.append((path, len(frame)))
    return written


def received_date(week_start: str, lag_days: int) -> str:
    """Return the file receipt date as an ISO date."""
    start = datetime.strptime(week_start, "%Y-%m-%d").date()
    return (start + timedelta(days=lag_days)).isoformat()


def main() -> None:
    """Assign distributors, write feeds, and print the defect summary."""
    cfg = common.load_config()
    sim = cfg["simulation"]
    logger = common.get_logger("simulate_feeds")
    rng = random.Random(int(cfg["random_seed"]))
    reference_dir = common.resolve(cfg["paths"]["reference_dir"])
    feeds_dir = common.resolve(cfg["paths"]["feeds_dir"])
    feeds_dir.mkdir(parents=True, exist_ok=True)
    for existing in feeds_dir.iterdir():
        if existing.is_file():
            existing.unlink()

    conn = common.connect(common.resolve(cfg["paths"]["database"]))
    try:
        mapping = assign_distributors(conn, reference_dir)
        weeks = week_lists(conn)
        missing = {
            distributor_id: choose_missing_weeks(weeks[distributor_id], rng, sim)
            for distributor_id in sim["missing_week_distributors"]
        }
        available = {
            distributor_id: [week for week in week_values if week not in set(missing.get(distributor_id, []))]
            for distributor_id, week_values in weeks.items()
        }
        shifts = choose_shifts(available, rng, sim)
        logger.info("Missing weeks: %s", missing)
        logger.info("Volume shifts: %s", {f"{dist}|{week}": round(factor, 4) for (dist, week), factor in shifts.items()})

        defect_records: list[dict] = []
        crosswalk_rows: list[dict] = []
        manifest_rows: list[dict] = []
        feed_counts = {}

        for distributor_id in DISTRIBUTORS:
            logger.info("Building feed %s", distributor_id)
            frame = load_distributor(conn, distributor_id)
            spec = cfg["feeds"][distributor_id]
            if distributor_id in missing:
                dropped = frame[frame["week_start"].isin(missing[distributor_id])]
                for week, rows in dropped.groupby("week_start").size().items():
                    defect_records.append(
                        {
                            "distributor": distributor_id,
                            "week": week,
                            "defect_type": "missing_weeks",
                            "rows_affected": int(rows),
                        }
                    )
                frame = frame[~frame["week_start"].isin(missing[distributor_id])].copy()
            else:
                frame = frame.copy()

            frame["volume_liters"] = frame["volume_liters"].astype(float)
            frame["bottles"] = frame["bottles"].astype(float)
            frame["dollars"] = frame["dollars"].astype(float)
            frame["is_shifted"] = False
            for (dist, week), factor in shifts.items():
                if dist != distributor_id:
                    continue
                mask = frame["week_start"] == week
                frame.loc[mask, "volume_liters"] = frame.loc[mask, "volume_liters"] * factor
                frame.loc[mask, "bottles"] = frame.loc[mask, "bottles"] * factor
                frame.loc[mask, "dollars"] = frame.loc[mask, "dollars"] * factor
                frame.loc[mask, "is_shifted"] = True

            frame["is_negative"] = False
            if distributor_id in sim["negative_distributors"]:
                positions = sample_positions(rng, len(frame), float(sim["negative_rate"]))
                indexer = frame.index[positions]
                frame.loc[indexer, "volume_liters"] = -frame.loc[indexer, "volume_liters"].abs()
                frame.loc[indexer, "is_negative"] = True

            prefix = "D07" if distributor_id == "D07" else "D08"
            if spec["use_crosswalk"]:
                frame["sku_out"] = prefix + frame["sku_id"]
                for sku_id in sorted(frame["sku_id"].unique()):
                    crosswalk_rows.append(
                        {
                            "distributor_id": distributor_id,
                            "dist_sku": prefix + sku_id,
                            "sku_id": sku_id,
                        }
                    )
            else:
                frame["sku_out"] = frame["sku_id"]

            frame["is_unmapped"] = False
            if distributor_id in sim["unmapped_distributors"]:
                positions = sample_positions(rng, len(frame), float(sim["unmapped_rate"]))
                indexer = frame.index[positions]
                codes = [f"ZZ{number:07d}" for number in range(1, len(positions) + 1)]
                frame.loc[indexer, "sku_out"] = codes
                frame.loc[indexer, "is_unmapped"] = True

            frame["is_mixed"] = False
            if distributor_id in sim["mixed_date_distributors"]:
                positions = sample_positions(rng, len(frame), float(sim["mixed_date_rate"]))
                frame.loc[frame.index[positions], "is_mixed"] = True

            frame["is_extra"] = False
            if distributor_id in sim["duplicate_distributors"]:
                positions = sample_positions(rng, len(frame), float(sim["duplicate_rate"]))
                extras = frame.iloc[positions].copy()
                extras["is_extra"] = True
                frame = pd.concat([frame, extras], ignore_index=True)

            log_flag(defect_records, distributor_id, frame, "is_shifted", "volume_distortion")
            log_flag(defect_records, distributor_id, frame, "is_negative", "negative_volume")
            log_flag(defect_records, distributor_id, frame, "is_unmapped", "unmapped_sku")
            log_flag(defect_records, distributor_id, frame, "is_mixed", "mixed_date_format")
            log_flag(defect_records, distributor_id, frame, "is_extra", "duplicate_rows")

            rendered = render_feed(frame, distributor_id, spec, sim)
            paths = write_feed_files(rendered, distributor_id, spec, feeds_dir, sim)
            feed_counts[distributor_id] = len(rendered)
            max_week = max(frame["week_start"])
            for path, row_count in paths:
                manifest_rows.append(
                    {
                        "file_name": path.name,
                        "distributor_id": distributor_id,
                        "row_count": row_count,
                        "max_week_start": max_week,
                    }
                )
            logger.info("%s rows written: %s", distributor_id, f"{len(rendered):,}")

        late_indexes = set(rng.sample(range(len(manifest_rows)), int(sim["late_file_count"])))
        manifest = []
        for index, row in enumerate(manifest_rows):
            late = index in late_indexes
            lag = int(sim["late_lag_days"] if late else sim["on_time_lag_days"])
            received = received_date(row["max_week_start"], lag)
            manifest.append(
                {
                    "file_name": row["file_name"],
                    "distributor_id": row["distributor_id"],
                    "row_count": int(row["row_count"]),
                    "max_week_start": row["max_week_start"],
                    "received_date": received,
                    "is_late": int(late),
                }
            )
            if late:
                defect_records.append(
                    {
                        "distributor": row["distributor_id"],
                        "week": row["max_week_start"],
                        "defect_type": "late_file",
                        "rows_affected": int(row["row_count"]),
                    }
                )

        manifest_frame = pd.DataFrame(manifest).sort_values("file_name")
        defect_frame = pd.DataFrame(defect_records).sort_values(["distributor", "defect_type", "week"])
        crosswalk = pd.DataFrame(crosswalk_rows).drop_duplicates().sort_values(["distributor_id", "sku_id"])

        manifest_path = common.resolve(cfg["paths"]["file_manifest"])
        defect_path = common.resolve(cfg["paths"]["defect_log"])
        crosswalk_path = common.resolve(cfg["paths"]["sku_crosswalk"])
        manifest_frame.to_csv(manifest_path, index=False)
        defect_frame.to_csv(defect_path, index=False)
        crosswalk.to_csv(crosswalk_path, index=False)
        conn.execute("DROP TABLE IF EXISTS defect_log")
        conn.execute("DROP TABLE IF EXISTS sku_crosswalk")
        defect_frame.to_sql("defect_log", conn, index=False)
        crosswalk.to_sql("sku_crosswalk", conn, index=False)
        conn.commit()
    finally:
        conn.close()

    summary = (
        defect_frame.groupby("defect_type", as_index=False)
        .agg(events=("week", "size"), rows_affected=("rows_affected", "sum"))
        .sort_values("defect_type")
    )
    print("")
    print("Distributor feed summary")
    volumes = mapping.groupby("distributor_id")["volume_liters"].sum().sort_index()
    for distributor_id, volume in volumes.items():
        print(f"{distributor_id}: {volume:,.0f} liters, {feed_counts[distributor_id]:,} feed rows")
    print("")
    print("Defect summary")
    print(f"{'defect_type':<22} {'events':>8} {'rows_affected':>14}")
    for row in summary.itertuples(index=False):
        print(f"{row.defect_type:<22} {int(row.events):>8,} {int(row.rows_affected):>14,}")
    print(f"Late files: {int(manifest_frame['is_late'].sum())}")
    print(f"Manifest: {manifest_path}")
    print(f"Defect log: {defect_path}")
    print(f"SKU crosswalk: {crosswalk_path}")


if __name__ == "__main__":
    main()
