"""Build an Excel workbook a reviewer can use without opening the database.

Summary totals use SUMIFS against the weekly table. The sample sheet looks
up SKU and account names with XLOOKUP. The file stays well under 25 MB by
keeping line detail to a 5,000 row sample.
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import xlsxwriter

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common  # noqa: E402

SAMPLE_ROWS = 5000
TOP_ROWS = 25


def sample_modulus(conn: sqlite3.Connection) -> int:
    """Pick a row stride that yields at least the sample size."""
    total = conn.execute("SELECT COUNT(*) FROM reconciliation").fetchone()[0]
    return max(1, int(total / SAMPLE_ROWS))


def load_frames(conn: sqlite3.Connection) -> dict[str, list[sqlite3.Row]]:
    """Load the slices the workbook needs."""
    modulus = sample_modulus(conn)
    sample = conn.execute(
        """
        SELECT distributor_id, week, sku_id, internal_volume, feed_volume, root_cause
        FROM reconciliation
        WHERE rowid % ? = 1
        ORDER BY distributor_id, week, sku_id
        LIMIT ?
        """,
        (modulus, SAMPLE_ROWS),
    ).fetchall()
    conn.execute("DROP TABLE IF EXISTS sample_keys")
    conn.execute(
        """
        CREATE TEMP TABLE sample_keys (
            distributor_id TEXT,
            week TEXT,
            sku_id TEXT
        )
        """
    )
    conn.executemany(
        "INSERT INTO sample_keys (distributor_id, week, sku_id) VALUES (?, ?, ?)",
        [(row["distributor_id"], row["week"], row["sku_id"]) for row in sample],
    )
    accounts = conn.execute(
        """
        SELECT distributor_id, week, sku_id, account_id
        FROM (
            SELECT
                k.distributor_id,
                k.week,
                k.sku_id,
                i.account_id,
                ROW_NUMBER() OVER (
                    PARTITION BY k.distributor_id, k.week, k.sku_id
                    ORDER BY i.volume_liters DESC, i.account_id
                ) AS rn
            FROM sample_keys AS k
            JOIN distributor_map AS m ON m.distributor_id = k.distributor_id
            JOIN dim_account AS a ON a.county = m.county
            JOIN internal_weekly AS i
                ON i.account_id = a.account_id
               AND i.week_start = k.week
               AND i.sku_id = k.sku_id
        )
        WHERE rn = 1
        """
    ).fetchall()
    account_lookup = {
        (row["distributor_id"], row["week"], row["sku_id"]): row["account_id"]
        for row in accounts
    }
    weekly = conn.execute(
        """
        SELECT
            distributor_id,
            week,
            ROUND(SUM(internal_volume), 4) AS internal_liters,
            ROUND(SUM(feed_volume), 4) AS feed_liters
        FROM reconciliation
        GROUP BY distributor_id, week
        ORDER BY distributor_id, week
        """
    ).fetchall()
    top = conn.execute(
        """
        SELECT distributor_id, sku_id, week, internal_volume, feed_volume,
               variance, variance_pct, flagged, root_cause
        FROM reconciliation
        WHERE flagged = 1
        ORDER BY ABS(variance) DESC
        LIMIT ?
        """,
        (TOP_ROWS,),
    ).fetchall()
    skus = conn.execute(
        """
        SELECT sku_id, im_desc, category, category_name, pack, bottle_volume_ml, vendor_name
        FROM dim_sku
        ORDER BY sku_id
        """
    ).fetchall()
    accounts_master = conn.execute(
        """
        SELECT account_id, name, city, county, territory_id
        FROM dim_account
        ORDER BY account_id
        """
    ).fetchall()
    distributors = [
        row[0]
        for row in conn.execute(
            "SELECT DISTINCT distributor_id FROM distributor_map ORDER BY distributor_id"
        )
    ]
    return {
        "sample": sample,
        "account_lookup": account_lookup,
        "weekly": weekly,
        "top": top,
        "skus": skus,
        "accounts": accounts_master,
        "distributors": distributors,
    }


def formats(workbook: xlsxwriter.Workbook) -> dict[str, xlsxwriter.format.Format]:
    """Shared cell formats."""
    return {
        "title": workbook.add_format({"bold": True, "font_size": 16, "font_color": "#1F4E79"}),
        "header": workbook.add_format(
            {"bold": True, "bg_color": "#1F4E79", "font_color": "#FFFFFF", "border": 1}
        ),
        "label": workbook.add_format({"bold": True}),
        "number": workbook.add_format({"num_format": "#,##0.00"}),
        "percent": workbook.add_format({"num_format": "0.00%"}),
        "wrap": workbook.add_format({"text_wrap": True, "valign": "top"}),
        "input": workbook.add_format(
            {"bold": True, "bg_color": "#FFF2CC", "border": 1, "align": "center"}
        ),
        "red": workbook.add_format({"bg_color": "#F4CCCC", "num_format": "0.00%"}),
        "amber": workbook.add_format({"bg_color": "#FCE4D6", "num_format": "0.00%"}),
    }


def write_summary(workbook, data, threshold, fmt) -> None:
    """Variance by distributor, with a dropdown and SUMIFS formulas."""
    sheet = workbook.add_worksheet("Summary")
    distributors = data["distributors"]
    for index, distributor in enumerate(distributors):
        sheet.write_string(index, 26, distributor)
    sheet.set_column(26, 26, None, None, {"hidden": True})
    last_list_row = len(distributors)
    workbook.define_name("DistributorList", f"=Summary!$AA$1:$AA${last_list_row}")
    workbook.define_name("VarianceThreshold", "=Summary!$C$5")

    sheet.write(0, 0, "Distributor variance", fmt["title"])
    sheet.write(2, 0, "Distributor", fmt["label"])
    sheet.write_string(2, 2, distributors[0], fmt["input"])
    sheet.data_validation(
        2,
        2,
        2,
        2,
        {"validate": "list", "source": "=DistributorList", "dropdown": True},
    )
    sheet.write(3, 0, "Change the yellow cell to switch distributor. Totals below use SUMIFS.", fmt["wrap"])
    sheet.write(4, 0, "Flag threshold", fmt["label"])
    sheet.write_number(4, 2, threshold, fmt["percent"])

    sheet.write(6, 1, "Internal liters", fmt["label"])
    sheet.write(7, 1, "Feed liters", fmt["label"])
    sheet.write(8, 1, "Variance liters", fmt["label"])
    sheet.write(9, 1, "Variance percent", fmt["label"])
    sheet.write_formula(
        6,
        2,
        '=SUMIFS(WeeklyByDistributor[internal_liters],WeeklyByDistributor[distributor_id],$C$3)',
        fmt["number"],
    )
    sheet.write_formula(
        7,
        2,
        '=SUMIFS(WeeklyByDistributor[feed_liters],WeeklyByDistributor[distributor_id],$C$3)',
        fmt["number"],
    )
    sheet.write_formula(8, 2, "=C8-C7", fmt["number"])
    sheet.write_formula(9, 2, '=IF(C7=0,"",C9/C7)', fmt["percent"])

    sheet.write(11, 0, "All distributors", fmt["title"])
    headers = ["Distributor", "Internal liters", "Feed liters", "Variance liters", "Variance percent"]
    for col, header in enumerate(headers):
        sheet.write(12, col, header, fmt["header"])
    for offset, distributor in enumerate(distributors):
        row = 13 + offset
        excel_row = row + 1
        sheet.write_string(row, 0, distributor)
        sheet.write_formula(
            row,
            1,
            f'=SUMIFS(WeeklyByDistributor[internal_liters],WeeklyByDistributor[distributor_id],A{excel_row})',
            fmt["number"],
        )
        sheet.write_formula(
            row,
            2,
            f'=SUMIFS(WeeklyByDistributor[feed_liters],WeeklyByDistributor[distributor_id],A{excel_row})',
            fmt["number"],
        )
        sheet.write_formula(row, 3, f"=C{excel_row}-B{excel_row}", fmt["number"])
        sheet.write_formula(row, 4, f'=IF(B{excel_row}=0,"",D{excel_row}/B{excel_row})', fmt["percent"])
    sheet.set_column(0, 0, 28)
    sheet.set_column(1, 1, 22)
    sheet.set_column(2, 4, 20)
    sheet.set_row(3, 32)
    sheet.freeze_panes(1, 0)


def write_weekly_compare(workbook, data, fmt) -> int:
    """Write a 5,000 row sample with lookup and variance formulas."""
    sheet = workbook.add_worksheet("Weekly_Compare")
    headers = [
        "distributor_id",
        "week",
        "account_id",
        "sku_id",
        "sku_name",
        "account_name",
        "city",
        "internal_liters",
        "feed_liters",
        "variance_liters",
        "variance_pct",
        "compare_flag",
        "root_cause",
    ]
    for col, header in enumerate(headers):
        sheet.write(0, col, header, fmt["header"])
    lookup = data["account_lookup"]
    for index, row in enumerate(data["sample"], start=1):
        excel_row = index + 1
        account_id = lookup.get((row["distributor_id"], row["week"], row["sku_id"]), "")
        sheet.write_string(index, 0, row["distributor_id"])
        sheet.write_string(index, 1, row["week"])
        sheet.write_string(index, 2, account_id or "")
        sheet.write_string(index, 3, row["sku_id"])
        sheet.write_formula(
            index,
            4,
            f'=XLOOKUP(D{excel_row},SKU_Master!A:A,SKU_Master!B:B,"Not on master")',
        )
        sheet.write_formula(
            index,
            5,
            f'=XLOOKUP(C{excel_row},Account_Master!A:A,Account_Master!B:B,"Not on master")',
        )
        sheet.write_formula(
            index,
            6,
            f'=XLOOKUP(C{excel_row},Account_Master!A:A,Account_Master!C:C,"Not on master")',
        )
        sheet.write_number(index, 7, float(row["internal_volume"]), fmt["number"])
        sheet.write_number(index, 8, float(row["feed_volume"]), fmt["number"])
        sheet.write_formula(index, 9, f"=I{excel_row}-H{excel_row}", fmt["number"])
        sheet.write_formula(index, 10, f'=IF(H{excel_row}=0,"",J{excel_row}/H{excel_row})', fmt["percent"])
        sheet.write_formula(
            index,
            11,
            (
                f'=IF(OR(AND(H{excel_row}=0,ABS(J{excel_row})>=0.01),'
                f'AND(H{excel_row}<>0,ABS(K{excel_row})>VarianceThreshold)),"Review","OK")'
            ),
        )
        sheet.write_string(index, 12, row["root_cause"] or "")
    last = len(data["sample"])
    sheet.autofilter(0, 0, last, len(headers) - 1)
    sheet.freeze_panes(1, 0)
    sheet.set_column(0, 3, 16)
    sheet.set_column(4, 6, 32)
    sheet.set_column(7, 11, 16)
    sheet.set_column(12, 12, 20)
    return last


def write_pivot_ready(workbook, data, fmt) -> int:
    """Write every distributor week as an Excel table for SUMIFS and pivots."""
    sheet = workbook.add_worksheet("Pivot_Ready")
    headers = [
        "distributor_id",
        "week",
        "internal_liters",
        "feed_liters",
        "variance_liters",
        "variance_pct",
    ]
    rows = data["weekly"]
    for index, row in enumerate(rows, start=1):
        excel_row = index + 1
        sheet.write_string(index, 0, row["distributor_id"])
        sheet.write_string(index, 1, row["week"])
        sheet.write_number(index, 2, float(row["internal_liters"]), fmt["number"])
        sheet.write_number(index, 3, float(row["feed_liters"]), fmt["number"])
        sheet.write_formula(index, 4, f"=D{excel_row}-C{excel_row}", fmt["number"])
        sheet.write_formula(index, 5, f'=IF(C{excel_row}=0,"",E{excel_row}/C{excel_row})', fmt["percent"])
    last = len(rows)
    sheet.add_table(
        0,
        0,
        last,
        len(headers) - 1,
        {
            "name": "WeeklyByDistributor",
            "style": "TableStyleMedium2",
            "columns": [{"header": header} for header in headers],
        },
    )
    sheet.freeze_panes(1, 0)
    sheet.set_column(0, 1, 16)
    sheet.set_column(2, 5, 18)
    return last


def write_top(workbook, data, fmt) -> None:
    """Write the 25 largest gaps and color the percent column."""
    sheet = workbook.add_worksheet("Top_Discrepancies")
    headers = [
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
    for col, header in enumerate(headers):
        sheet.write(0, col, header, fmt["header"])
    for index, row in enumerate(data["top"], start=1):
        sheet.write_string(index, 0, row["distributor_id"])
        sheet.write_string(index, 1, row["sku_id"])
        sheet.write_string(index, 2, row["week"])
        sheet.write_number(index, 3, float(row["internal_volume"]), fmt["number"])
        sheet.write_number(index, 4, float(row["feed_volume"]), fmt["number"])
        sheet.write_number(index, 5, float(row["variance"]), fmt["number"])
        if row["variance_pct"] is None:
            sheet.write_blank(index, 6, None, fmt["percent"])
        else:
            sheet.write_number(index, 6, float(row["variance_pct"]), fmt["percent"])
        sheet.write_number(index, 7, int(row["flagged"]))
        sheet.write_string(index, 8, row["root_cause"] or "")
    last = max(len(data["top"]), 1)
    sheet.autofilter(0, 0, last, len(headers) - 1)
    sheet.conditional_format(
        1,
        6,
        last,
        6,
        {"type": "formula", "criteria": "=ABS(G2)>=0.10", "format": fmt["red"]},
    )
    sheet.conditional_format(
        1,
        6,
        last,
        6,
        {
            "type": "formula",
            "criteria": "=AND(ABS(G2)>=0.05,ABS(G2)<0.10)",
            "format": fmt["amber"],
        },
    )
    sheet.freeze_panes(1, 0)
    sheet.set_column(0, 2, 16)
    sheet.set_column(3, 7, 18)
    sheet.set_column(8, 8, 20)


def write_sku_master(workbook, data, fmt) -> int:
    """Write the internal SKU list used by XLOOKUP."""
    sheet = workbook.add_worksheet("SKU_Master")
    headers = ["sku_id", "description", "category", "category_name", "pack", "bottle_ml", "vendor"]
    for col, header in enumerate(headers):
        sheet.write(0, col, header, fmt["header"])
    for index, row in enumerate(data["skus"], start=1):
        sheet.write_string(index, 0, row["sku_id"])
        sheet.write_string(index, 1, row["im_desc"] or "")
        sheet.write_string(index, 2, row["category"] or "")
        sheet.write_string(index, 3, row["category_name"] or "")
        sheet.write_number(index, 4, float(row["pack"] or 0))
        sheet.write_number(index, 5, float(row["bottle_volume_ml"] or 0), fmt["number"])
        sheet.write_string(index, 6, row["vendor_name"] or "")
    sheet.autofilter(0, 0, len(data["skus"]), len(headers) - 1)
    sheet.freeze_panes(1, 0)
    sheet.set_column(0, 0, 14)
    sheet.set_column(1, 1, 42)
    sheet.set_column(2, 3, 28)
    sheet.set_column(4, 6, 16)
    return len(data["skus"])


def write_account_master(workbook, data, fmt) -> int:
    """Write the internal account list used by XLOOKUP."""
    sheet = workbook.add_worksheet("Account_Master")
    headers = ["account_id", "name", "city", "county", "territory_id"]
    for col, header in enumerate(headers):
        sheet.write(0, col, header, fmt["header"])
    for index, row in enumerate(data["accounts"], start=1):
        sheet.write_string(index, 0, row["account_id"])
        sheet.write_string(index, 1, row["name"] or "")
        sheet.write_string(index, 2, row["city"] or "")
        sheet.write_string(index, 3, row["county"] or "")
        sheet.write_string(index, 4, row["territory_id"] or "")
    sheet.autofilter(0, 0, len(data["accounts"]), len(headers) - 1)
    sheet.freeze_panes(1, 0)
    sheet.set_column(0, 0, 14)
    sheet.set_column(1, 1, 42)
    sheet.set_column(2, 4, 18)
    return len(data["accounts"])


def write_readme(workbook, fmt) -> None:
    """Explain the comparison for someone who does not write code."""
    sheet = workbook.add_worksheet("README")
    lines = [
        "How to compare the two datasets",
        "",
        "This workbook compares two views of the same sales. Internal liters come from the Iowa liquor sales book, rolled up by week. Feed liters come from the distributor files after duplicate rows are removed, item codes are mapped, and negative volumes are dropped.",
        "",
        "1. Start on Summary. The yellow cell is a distributor dropdown. Pick D01 through D08.",
        "2. Internal liters, feed liters, and variance percent update with SUMIFS formulas. You do not need to copy values.",
        "3. A variance percent beyond the flag threshold (5%) is large enough to review. The All distributors block shows every distributor with the same formulas.",
        "4. Open Top_Discrepancies for the 25 largest liter gaps. Red means the absolute variance is over 10%. Amber means it is from 5% to 10%.",
        "5. Weekly_Compare is a 5,000 row sample, not the full book. sku_name, account_name, and city are XLOOKUP formulas against SKU_Master and Account_Master. Not on master means the code is missing from the internal list. compare_flag says Review when the sample line crosses the threshold.",
        "6. The account on Weekly_Compare is the store with the most internal liters for that distributor, week, and SKU. Feed liters on that row are the distributor total for the SKU and week, not that store alone.",
        "7. Pivot_Ready is an Excel table with one row per distributor and week. Use Insert, PivotTable if you want a different cut. Summary reads this table.",
        "8. Do not type over formula cells. Filter and sort are safe.",
    ]
    sheet.write(0, 0, lines[0], fmt["title"])
    for index, line in enumerate(lines[1:], start=1):
        sheet.write(index, 0, line, fmt["wrap"])
        sheet.set_row(index, 36)
    sheet.set_column(0, 0, 120)


def main() -> None:
    """Create the variance workbook from the reconciliation tables."""
    cfg = common.load_config()
    logger = common.get_logger("build_excel")
    threshold = float(cfg["thresholds"]["variance_pct"])
    path = common.resolve(cfg["paths"]["excel_workbook"])
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = common.connect(common.resolve(cfg["paths"]["database"]))
    try:
        logger.info("Loading workbook slices")
        data = load_frames(conn)
    finally:
        conn.close()

    workbook = xlsxwriter.Workbook(path, {"nan_inf_to_errors": True})
    fmt = formats(workbook)
    write_summary(workbook, data, threshold, fmt)
    sample_rows = write_weekly_compare(workbook, data, fmt)
    weekly_rows = write_pivot_ready(workbook, data, fmt)
    write_top(workbook, data, fmt)
    sku_rows = write_sku_master(workbook, data, fmt)
    account_rows = write_account_master(workbook, data, fmt)
    write_readme(workbook, fmt)
    workbook.close()

    size = path.stat().st_size
    if size > 25 * 1024 * 1024:
        raise RuntimeError(f"Workbook is {size / 1024 / 1024:.1f} MB, over the 25 MB limit")
    logger.info("Excel workbook")
    logger.info("File: %s", path)
    logger.info("Size: %.2f MB", size / 1024 / 1024)
    logger.info("Weekly_Compare rows: %s", f"{sample_rows:,}")
    logger.info("Pivot_Ready rows: %s", f"{weekly_rows:,}")
    logger.info("SKU_Master rows: %s", f"{sku_rows:,}")
    logger.info("Account_Master rows: %s", f"{account_rows:,}")
    logger.info("Top discrepancies: %s", f"{len(data['top']):,}")


if __name__ == "__main__":
    main()
