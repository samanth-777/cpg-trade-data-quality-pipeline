"""Validate staged feeds and score each distributor.

Exceptions land in SQLite and data/output/exceptions.csv. The scorecard
rates completeness, uniqueness, validity, and timeliness. Detection results
compare those exceptions with the injected defect log.
"""

from __future__ import annotations

import shutil
import sqlite3
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common  # noqa: E402

SEVERITY_ORDER = {"High": 0, "Medium": 1, "Low": 2}
DEFECT_CHECKS = {
    "duplicate_rows": "duplicates",
    "missing_weeks": "missing_weeks",
    "unmapped_sku": "unmapped_sku",
    "negative_volume": "negative_volume",
    "mixed_date_format": "parse_failure",
    "late_file": "late_file",
    "volume_distortion": None,
}


def split_named_sql(sql_text: str) -> list[tuple[str, str]]:
    """Split a SQL file into named statements."""
    sections: list[tuple[str, str]] = []
    name = None
    buffer: list[str] = []
    for line in sql_text.splitlines():
        if line.startswith("-- name:"):
            if name and "".join(buffer).strip():
                sections.append((name, "\n".join(buffer).strip().rstrip(";")))
            name = line.split(":", 1)[1].strip()
            buffer = []
        else:
            buffer.append(line)
    if name and "".join(buffer).strip():
        sections.append((name, "\n".join(buffer).strip().rstrip(";")))
    return sections


def query_frame(conn: sqlite3.Connection, sql: str, params: dict) -> pd.DataFrame:
    """Run one parameterized query and return a DataFrame."""
    return pd.read_sql_query(sql, conn, params=params)


def add_check(frame: pd.DataFrame, check_name: str, severity: str, description) -> pd.DataFrame:
    """Attach the exception columns shared by every check."""
    if frame.empty:
        return pd.DataFrame(columns=["distributor_id", "week", "check_name", "issue_description", "row_count", "severity"])
    output = frame.copy()
    output["check_name"] = check_name
    output["severity"] = severity
    output["issue_description"] = description(output) if callable(description) else description
    output["row_count"] = output["row_count"].astype(int)
    return output[["distributor_id", "week", "check_name", "issue_description", "row_count", "severity"]]


def clamp_score(value: float) -> float:
    """Keep a dimension score inside 0 to 100."""
    return round(min(100.0, max(0.0, value)), 2)


def build_exceptions(result: dict[str, pd.DataFrame], std_mult: float, timeliness_days: int) -> pd.DataFrame:
    """Turn check results into the exceptions grain."""
    parts = [
        add_check(
            result["duplicate_weeks"],
            "duplicates",
            "High",
            lambda frame: frame.apply(
                lambda row: (
                    f"Duplicate week, account, and SKU keys. {int(row['row_count']):,} extra rows "
                    f"across {int(row['duplicate_keys']):,} keys."
                ),
                axis=1,
            ),
        ),
        add_check(
            result["missing_weeks"],
            "missing_weeks",
            "High",
            lambda frame: frame["row_count"].map(
                lambda count: (
                    f"No feed rows for a week the internal book contains. "
                    f"{int(count):,} internal rows are uncovered."
                )
            ),
        ),
        add_check(
            result["unmapped_sku"],
            "unmapped_sku",
            "High",
            lambda frame: frame["row_count"].map(
                lambda count: f"SKU code is not on the item master. {int(count):,} rows."
            ),
        ),
        add_check(
            result["unmapped_account"],
            "unmapped_account",
            "High",
            lambda frame: frame["row_count"].map(
                lambda count: f"Account code is not on the account master. {int(count):,} rows."
            ),
        ),
        add_check(
            result["negative_volume"],
            "negative_volume",
            "High",
            lambda frame: frame["row_count"].map(
                lambda count: f"Volume in liters is negative. {int(count):,} rows."
            ),
        ),
        add_check(
            result["zero_volume"],
            "zero_volume",
            "Low",
            lambda frame: frame["row_count"].map(
                lambda count: f"Volume in liters is zero. {int(count):,} rows."
            ),
        ),
        add_check(
            result["outlier_volume"],
            "outlier_volume",
            "Medium",
            lambda frame: frame["row_count"].map(
                lambda count: (
                    f"Volume is more than {std_mult:g} population standard deviations "
                    f"above the positive-volume mean for that SKU. {int(count):,} rows."
                )
            ),
        ),
        add_check(
            result["parse_failures"],
            "parse_failure",
            "High",
            lambda frame: frame.apply(
                lambda row: f"Rows failed parsing ({row['reasons']}). {int(row['row_count']):,} rows.",
                axis=1,
            ),
        ),
        add_check(
            result["late_files"],
            "late_file",
            "Medium",
            lambda frame: frame.apply(
                lambda row: (
                    f"File {row['source_file']} was received on {row['received_date']}, "
                    f"{int(row['lag_days'])} days after week {row['week']}. "
                    f"The SLA is {timeliness_days} days."
                ),
                axis=1,
            ),
        ),
    ]
    exceptions = pd.concat([part for part in parts if not part.empty], ignore_index=True)
    exceptions["severity_rank"] = exceptions["severity"].map(SEVERITY_ORDER)
    exceptions = exceptions.sort_values(
        ["severity_rank", "distributor_id", "week", "check_name"]
    ).drop(columns=["severity_rank"])
    return exceptions.reset_index(drop=True)


def build_scorecard(result: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Score each distributor from 0 to 100 on four dimensions."""
    loaded = result["loaded_totals"].set_index("distributor_id")
    expected = result["expected_weeks"].set_index("distributor_id")
    extra = result["duplicate_extra"].set_index("distributor_id") if not result["duplicate_extra"].empty else pd.DataFrame()
    invalid = result["invalid_rows"].set_index("distributor_id") if not result["invalid_rows"].empty else pd.DataFrame()
    rejected = result["reject_totals"].set_index("distributor_id") if not result["reject_totals"].empty else pd.DataFrame()
    files = result["file_counts"].set_index("distributor_id")
    rows = []
    for distributor_id in sorted(loaded.index):
        loaded_rows = int(loaded.loc[distributor_id, "loaded_rows"])
        present_weeks = int(loaded.loc[distributor_id, "present_weeks"])
        expected_weeks = int(expected.loc[distributor_id, "expected_weeks"])
        extra_rows = int(extra.loc[distributor_id, "extra_rows"]) if distributor_id in extra.index else 0
        invalid_rows = int(invalid.loc[distributor_id, "invalid_rows"]) if distributor_id in invalid.index else 0
        rejected_rows = int(rejected.loc[distributor_id, "rejected_rows"]) if distributor_id in rejected.index else 0
        file_count = int(files.loc[distributor_id, "files"])
        late_files = int(files.loc[distributor_id, "late_files"])
        completeness = clamp_score(100 * present_weeks / expected_weeks if expected_weeks else 0)
        uniqueness = clamp_score(100 * (1 - extra_rows / loaded_rows) if loaded_rows else 0)
        denominator = loaded_rows + rejected_rows
        validity = clamp_score(100 * (1 - (invalid_rows + rejected_rows) / denominator) if denominator else 0)
        timeliness = clamp_score(100 * (1 - late_files / file_count) if file_count else 0)
        overall = clamp_score((completeness + uniqueness + validity + timeliness) / 4)
        rows.append(
            {
                "distributor_id": distributor_id,
                "completeness": completeness,
                "uniqueness": uniqueness,
                "validity": validity,
                "timeliness": timeliness,
                "overall": overall,
                "loaded_rows": loaded_rows,
                "rejected_rows": rejected_rows,
                "expected_weeks": expected_weeks,
                "present_weeks": present_weeks,
                "duplicate_extra_rows": extra_rows,
                "invalid_rows": invalid_rows,
                "late_files": late_files,
                "files": file_count,
            }
        )
    return pd.DataFrame(rows)


def build_detection(defect_log: pd.DataFrame, exceptions: pd.DataFrame) -> pd.DataFrame:
    """Compare injected defect events with the exceptions that caught them."""
    caught_keys = set(
        zip(exceptions["distributor_id"], exceptions["week"].astype(str), exceptions["check_name"])
    )
    rows = []
    for defect_type, group in defect_log.groupby("defect_type", sort=True):
        check_name = DEFECT_CHECKS.get(defect_type)
        injected = len(group)
        if check_name is None:
            caught = 0
        else:
            caught = sum(
                (row.distributor, str(row.week), check_name) in caught_keys
                for row in group.itertuples(index=False)
            )
        rows.append(
            {
                "defect_type": defect_type,
                "injected": injected,
                "caught": caught,
                "detection_rate": round(100 * caught / injected, 2) if injected else 0,
            }
        )
    return pd.DataFrame(rows)


def write_detection_report(path: Path, detection: pd.DataFrame, scorecard: pd.DataFrame) -> None:
    """Write the detection narrative with the live rates."""
    lines = [
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
    for row in detection.itertuples(index=False):
        lines.append(
            f"| {row.defect_type} | {int(row.injected)} | {int(row.caught)} | {row.detection_rate:.2f}% |"
        )
    total_injected = int(detection["injected"].sum())
    total_caught = int(detection["caught"].sum())
    overall = 100 * total_caught / total_injected if total_injected else 0
    lines.extend(
        [
            "",
            (
                f"Validation stage caught {total_caught} of {total_injected} injected events "
                f"({overall:.2f}%)."
            ),
            "",
            "Volume distortion is not caught here. A uniform 8 to 15 percent move still looks like a normal number, so it does not trip duplicates, mapping, sign, parse, or lateness checks.",
            "",
            "## Reconciliation-stage detection",
            "",
            "Written by src/reconcile.py after the feed is compared with the internal book.",
            "",
            "## Overall detection",
            "",
            "Written by src/reconcile.py across both stages.",
            "",
            "## Scorecard",
            "",
            "Scores run from 0 to 100. Overall is the unweighted mean of completeness, uniqueness, validity, and timeliness.",
            "",
            "| Distributor | Completeness | Uniqueness | Validity | Timeliness | Overall |",
            "| --- | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for row in scorecard.itertuples(index=False):
        lines.append(
            f"| {row.distributor_id} | {row.completeness:.2f} | {row.uniqueness:.2f} | "
            f"{row.validity:.2f} | {row.timeliness:.2f} | {row.overall:.2f} |"
        )
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    """Run validation, write the scorecard, and compare it with the defect log."""
    cfg = common.load_config()
    logger = common.get_logger("validate")
    params = {
        "start": cfg["date_range"]["start"],
        "end": cfg["date_range"]["end"],
        "std_mult": float(cfg["thresholds"]["outlier_std"]),
        "timeliness_days": int(cfg["thresholds"]["timeliness_days"]),
    }
    sql_path = common.ROOT / "sql" / "validate.sql"
    conn = common.connect(common.resolve(cfg["paths"]["database"]))
    try:
        conn.execute("DROP TABLE IF EXISTS file_manifest")
        manifest = pd.read_csv(common.resolve(cfg["paths"]["file_manifest"]))
        manifest.to_sql("file_manifest", conn, index=False)
        result = {}
        for name, sql in split_named_sql(sql_path.read_text(encoding="utf-8")):
            logger.info("Running check %s", name)
            result[name] = query_frame(conn, sql, params)
        exceptions = build_exceptions(
            result,
            params["std_mult"],
            params["timeliness_days"],
        )
        scorecard = build_scorecard(result)
        defect_log = pd.read_csv(common.resolve(cfg["paths"]["defect_log"]))
        detection = build_detection(defect_log, exceptions)
        conn.execute("DROP TABLE IF EXISTS exceptions")
        conn.execute("DROP TABLE IF EXISTS dq_scorecard")
        exceptions.to_sql("exceptions", conn, index=False)
        scorecard.to_sql("dq_scorecard", conn, index=False)
        conn.commit()
    finally:
        conn.close()

    output_dir = common.resolve(cfg["paths"]["output_dir"])
    output_dir.mkdir(parents=True, exist_ok=True)
    exceptions_path = common.resolve(cfg["paths"]["exceptions_csv"])
    scorecard_path = common.resolve(cfg["paths"]["scorecard_csv"])
    report_path = common.resolve(cfg["paths"]["detection_report"])
    exceptions.to_csv(exceptions_path, index=False)
    scorecard.to_csv(scorecard_path, index=False)
    write_detection_report(report_path, detection, scorecard)
    sample_dir = common.ROOT / "docs" / "sample_output"
    sample_dir.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(exceptions_path, sample_dir / "exceptions.csv")
    shutil.copyfile(scorecard_path, sample_dir / "dq_scorecard.csv")

    print("")
    print("Validation summary")
    print(f"Exceptions: {len(exceptions):,}")
    print(scorecard[["distributor_id", "completeness", "uniqueness", "validity", "timeliness", "overall"]].to_string(index=False))
    print("")
    print("Validation-stage detection")
    print(detection.to_string(index=False))
    print(f"Report: {report_path}")


if __name__ == "__main__":
    main()
