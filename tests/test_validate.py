"""Unit tests for the validation exception rules."""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import validate  # noqa: E402


def empty_checks() -> dict[str, pd.DataFrame]:
    """Return one empty frame per check build_exceptions expects."""
    blank = pd.DataFrame(columns=["distributor_id", "week", "row_count"])
    return {
        "duplicate_weeks": blank.copy(),
        "missing_weeks": blank.copy(),
        "unmapped_sku": blank.copy(),
        "unmapped_account": blank.copy(),
        "negative_volume": blank.copy(),
        "zero_volume": blank.copy(),
        "outlier_volume": blank.copy(),
        "parse_failures": pd.DataFrame(columns=["distributor_id", "week", "row_count", "reasons"]),
        "late_files": pd.DataFrame(
            columns=["distributor_id", "week", "row_count", "source_file", "received_date", "lag_days"]
        ),
    }


def one_row(check: str, **extra) -> dict[str, pd.DataFrame]:
    """Place a single distributor week into one check and leave the rest empty."""
    result = empty_checks()
    row = {"distributor_id": "D01", "week": "2024-01-01", "row_count": 4, **extra}
    result[check] = pd.DataFrame([row])
    return result


def test_duplicate_weeks_are_high_severity():
    """Extra copies of a week, account, and SKU become a High duplicate exception."""
    exceptions = validate.build_exceptions(
        one_row("duplicate_weeks", duplicate_keys=2),
        std_mult=4,
        timeliness_days=10,
    )
    assert list(exceptions["check_name"]) == ["duplicates"]
    assert list(exceptions["severity"]) == ["High"]
    assert "Duplicate" in exceptions.loc[0, "issue_description"]


def test_missing_weeks_are_high_severity():
    """A week present internally and absent from the feed is a High exception."""
    exceptions = validate.build_exceptions(one_row("missing_weeks"), std_mult=4, timeliness_days=10)
    assert list(exceptions["check_name"]) == ["missing_weeks"]
    assert list(exceptions["severity"]) == ["High"]
    assert "No feed rows" in exceptions.loc[0, "issue_description"]


def test_unmapped_sku_is_high_severity():
    """A SKU missing from the item master is a High exception."""
    exceptions = validate.build_exceptions(one_row("unmapped_sku"), std_mult=4, timeliness_days=10)
    assert list(exceptions["check_name"]) == ["unmapped_sku"]
    assert list(exceptions["severity"]) == ["High"]
    assert "item master" in exceptions.loc[0, "issue_description"]


def test_negative_volume_is_high_severity():
    """Negative liters are a High exception."""
    exceptions = validate.build_exceptions(one_row("negative_volume"), std_mult=4, timeliness_days=10)
    assert list(exceptions["check_name"]) == ["negative_volume"]
    assert list(exceptions["severity"]) == ["High"]
    assert "negative" in exceptions.loc[0, "issue_description"]


def test_empty_checks_produce_no_exceptions():
    """Checks with no rows do not raise and do not invent exceptions."""
    exceptions = validate.build_exceptions(empty_checks(), std_mult=4, timeliness_days=10)
    assert exceptions.empty
