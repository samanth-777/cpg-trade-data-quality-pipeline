"""Profile source_sales and write docs/data_profile.md.

The queries live in sql/profile.sql. This script runs them against the
pipeline database, then writes exact counts, percentages, and a short
list of the five most important issues.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common  # noqa: E402

TEXT_COLUMNS = [
    "invoice_line_no",
    "date",
    "store",
    "name",
    "city",
    "county",
    "category",
    "category_name",
    "vendor_number",
    "vendor_name",
    "itemno",
    "im_desc",
]
NUMERIC_COLUMNS = [
    "pack",
    "bottle_volume_ml",
    "state_bottle_cost",
    "state_bottle_retail",
    "sale_bottles",
    "sale_dollars",
    "sale_liters",
]
WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def split_named_sql(sql_text: str) -> list[tuple[str, str]]:
    """Split a SQL file into (name, statement) pairs marked by `-- name:`."""
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


def rows_to_dicts(cursor) -> list[dict]:
    """Turn a cursor result into a list of dictionaries."""
    columns = [item[0] for item in cursor.description]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]


def one(result: dict[str, list[dict]], name: str) -> dict:
    """Return the single row for a named query."""
    found = result[name]
    if not found:
        raise RuntimeError(f"Query {name} returned no rows")
    return found[0]


def pct(part: float, whole: float) -> str:
    """Format part / whole as a percent with two decimals."""
    if not whole:
        return "0.00%"
    return f"{(part / whole) * 100:.2f}%"


def num(value) -> str:
    """Format an integer with thousands separators."""
    return f"{int(value):,}"


def money(value) -> str:
    """Format a dollar amount, with the sign in front of the symbol."""
    amount = float(value)
    sign = "-" if amount < 0 else ""
    return f"{sign}${abs(amount):,.2f}"


def cell(value) -> str:
    """Make a value safe for a markdown table cell."""
    if value is None:
        return ""
    return str(value).replace("|", "/").replace("\n", " ").strip()


def markdown_table(headers: list[str], records: list[dict]) -> str:
    """Render records as a markdown table."""
    head = "| " + " | ".join(headers) + " |"
    rule = "| " + " | ".join("---" for _ in headers) + " |"
    body = [
        "| " + " | ".join(cell(record.get(header, "")) for header in headers) + " |"
        for record in records
    ]
    return "\n".join([head, rule, *body])


def calendar_finding(stats: dict, missing_weeks: list[dict]) -> str:
    """Describe empty days and empty weeks without overstating a partial week."""
    sentence = (
        f"{num(stats['missing_days'])} of {num(stats['window_days'])} days in the "
        f"window ({pct(stats['missing_days'], stats['window_days'])}) have no sales. "
        f"{num(stats['saturday_gaps'])} of those days are Saturdays and "
        f"{num(stats['sunday_gaps'])} are Sundays. "
    )
    if len(missing_weeks) == 1 and int(missing_weeks[0]["days_in_window"]) == 1:
        week = missing_weeks[0]
        sentence += (
            f"{num(stats['weeks_with_sales'])} of {num(stats['weeks'])} Monday-start weeks "
            "that overlap the window contain at least one sales day. The other week starts "
            f"{week['week_start']} and only includes {week['first_day']} inside the window, "
            "which has no sales."
        )
    elif not missing_weeks:
        sentence += (
            f"All {num(stats['weeks'])} Monday-start weeks that overlap the window "
            "contain at least one sales day."
        )
    else:
        starts = ", ".join(week["week_start"] for week in missing_weeks)
        sentence += (
            f"{num(len(missing_weeks))} of {num(stats['weeks'])} Monday-start weeks "
            f"have no sales: {starts}."
        )
    return sentence


def key_findings(stats: dict, missing_weeks: list[dict]) -> list[str]:
    """Choose the five issues a reviewer should read first."""
    rows = stats["rows"]
    findings = [
        (
            "Bottle cost and bottle retail are empty on every one of the "
            f"{num(rows)} lines. Sale dollars cannot be checked against bottles "
            "times the retail price, because those price fields are not populated "
            "in the public extract."
        ),
        (
            f"{num(stats['all_three_negative'])} lines "
            f"({pct(stats['all_three_negative'], rows)}) are negative on bottles, "
            f"dollars, and liters together, totaling {money(stats['negative_dollars'])}. "
            f"{num(stats['negative_rinv_rows'])} of them use an RINV invoice prefix, "
            "which marks a return. Keeping the negative signs in a volume total "
            "understates what was sold."
        ),
        (
            f"{num(stats['multi_items'])} of {num(stats['items'])} item numbers "
            f"({pct(stats['multi_items'], stats['items'])}) use more than one product "
            f"description. Those items cover {num(stats['multi_item_rows'])} lines "
            f"({pct(stats['multi_item_rows'], rows)}). A single description per item "
            "number will disagree with part of the history."
        ),
        (
            f"{num(stats['multi_stores'])} of {num(stats['stores'])} store numbers "
            f"({pct(stats['multi_stores'], stats['stores'])}) appear under more than "
            f"one name. Those stores cover {num(stats['multi_store_rows'])} lines "
            f"({pct(stats['multi_store_rows'], rows)}). Matching accounts on the name "
            "string will split them."
        ),
        calendar_finding(stats, missing_weeks),
    ]
    return findings


def build_report(cfg: dict, result: dict[str, list[dict]]) -> str:
    """Assemble the profile markdown from query results."""
    overview = one(result, "overview")
    nulls = one(result, "nulls_blanks")
    dupes = one(result, "duplicate_invoices")
    items = one(result, "multi_item_summary")
    stores = one(result, "multi_store_summary")
    categories = one(result, "multi_category_summary")
    quantities = one(result, "nonpositive")
    prices = one(result, "price_check")
    missing_days = result["missing_days"]
    missing_weeks = result["missing_weeks"]
    window_days = int(one(result, "window_days")["window_days"])
    weeks = int(one(result, "week_count")["weeks"])
    rows = int(overview["row_count"])
    weekday_counts = {name: 0 for name in WEEKDAYS}
    for day in missing_days:
        weekday_counts[day["weekday"]] = weekday_counts.get(day["weekday"], 0) + 1
    empty_week = missing_weeks[0] if missing_weeks else None
    stats = {
        "rows": rows,
        "items": int(overview["items"]),
        "stores": int(overview["stores"]),
        "all_three_negative": int(quantities["all_three_negative"]),
        "negative_dollars": float(quantities["negative_dollars"]),
        "negative_rinv_rows": int(quantities["negative_rinv_rows"]),
        "multi_items": int(items["items_with_many_descriptions"]),
        "multi_item_rows": int(items["rows_on_those_items"]),
        "multi_stores": int(stores["stores_with_many_names"]),
        "multi_store_rows": int(stores["rows_on_those_stores"]),
        "missing_days": len(missing_days),
        "window_days": window_days,
        "saturday_gaps": weekday_counts["Saturday"],
        "sunday_gaps": weekday_counts["Sunday"],
        "weeks": weeks,
        "weeks_with_sales": weeks - len(missing_weeks),
        "empty_week_start": empty_week["week_start"] if empty_week else "none",
        "empty_week_day": empty_week["first_day"] if empty_week else "none",
    }
    findings = key_findings(stats, missing_weeks)
    tolerance = float(cfg["thresholds"]["price_tolerance_dollars"])
    lines = [
        "# Iowa Liquor Sales Data Profile",
        "",
        (
            f"Profile of `source_sales`: {num(rows)} invoice lines from "
            f"{overview['min_date']} to {overview['max_date']}. "
            f"The configured window is {cfg['date_range']['start']} to "
            f"{cfg['date_range']['end']} ({num(window_days)} days)."
        ),
        "",
        "## Key Findings",
        "",
    ]
    for index, finding in enumerate(findings, start=1):
        lines.append(f"{index}. {finding}")
    lines.extend(
        [
            "",
            "## Coverage",
            "",
            (
                f"The extract has {num(overview['stores'])} stores, "
                f"{num(overview['items'])} item numbers, "
                f"{num(overview['categories'])} category codes, "
                f"{num(overview['counties'])} county values, and "
                f"{num(overview['vendors'])} vendors. "
                f"Sales dollars total {money(overview['total_dollars'])}, "
                f"liters total {float(overview['total_liters']):,.2f}, and "
                f"bottles total {num(overview['total_bottles'])}. "
                f"The average line is {money(overview['avg_dollars'])}."
            ),
            "",
            "## Nulls and blanks by column",
            "",
            "Text blanks are empty or whitespace-only strings. Numeric fields have no blank state. An empty numeric value was stored as null.",
            "",
            "| Column | Nulls | Null % | Blanks | Blank % | Null or blank | Null or blank % |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for column in TEXT_COLUMNS + NUMERIC_COLUMNS:
        null_count = int(nulls[f"{column}_nulls"] or 0)
        blank_count = int(nulls[f"{column}_blanks"] or 0)
        either = null_count + blank_count
        lines.append(
            f"| {column} | {num(null_count)} | {pct(null_count, rows)} | "
            f"{num(blank_count)} | {pct(blank_count, rows)} | "
            f"{num(either)} | {pct(either, rows)} |"
        )
    lines.extend(
        [
            "",
            "## Duplicate invoice_line_no",
            "",
            (
                f"Duplicate keys: {num(dupes['duplicate_keys'])} "
                f"({pct(dupes['duplicate_keys'], rows)} of rows). "
                f"Extra copies beyond the first: {num(dupes['extra_rows'])}. "
                f"Rows sitting in duplicate keys: {num(dupes['rows_in_duplicate_keys'])}."
            ),
            "",
            "Invoice line number is unique in the loaded extract.",
            "",
            "## Item numbers with more than one description",
            "",
            (
                f"{num(items['items_with_many_descriptions'])} of {num(overview['items'])} "
                f"item numbers ({pct(items['items_with_many_descriptions'], overview['items'])}) "
                f"have more than one `im_desc`. They account for "
                f"{num(items['rows_on_those_items'])} lines "
                f"({pct(items['rows_on_those_items'], rows)})."
            ),
            "",
        ]
    )
    if result["multi_item_examples"]:
        lines.append("Largest items by line count:")
        lines.append("")
        lines.append(
            markdown_table(
                ["itemno", "description_count", "rows", "descriptions"],
                result["multi_item_examples"],
            )
        )
    else:
        lines.append("No item number has more than one description.")
    lines.extend(
        [
            "",
            "## Stores with more than one name spelling",
            "",
            (
                f"{num(stores['stores_with_many_names'])} of {num(overview['stores'])} "
                f"store numbers ({pct(stores['stores_with_many_names'], overview['stores'])}) "
                f"have more than one `name`. They account for "
                f"{num(stores['rows_on_those_stores'])} lines "
                f"({pct(stores['rows_on_those_stores'], rows)})."
            ),
            "",
        ]
    )
    if result["multi_store_examples"]:
        lines.append("Largest stores by line count:")
        lines.append("")
        lines.append(
            markdown_table(
                ["store", "name_count", "rows", "names"],
                result["multi_store_examples"],
            )
        )
    else:
        lines.append("No store number has more than one name.")
    lines.extend(
        [
            "",
            "## Category codes with more than one category name",
            "",
            (
                f"{num(categories['categories_with_many_names'])} of {num(overview['categories'])} "
                f"category codes ({pct(categories['categories_with_many_names'], overview['categories'])}) "
                f"have more than one `category_name`. They account for "
                f"{num(categories['rows_on_those_categories'])} lines "
                f"({pct(categories['rows_on_those_categories'], rows)})."
            ),
            "",
        ]
    )
    if result["multi_category_examples"]:
        lines.append(
            markdown_table(
                ["category", "name_count", "rows", "names"],
                result["multi_category_examples"],
            )
        )
    else:
        lines.append("Every category code maps to one category name.")
    lines.extend(
        [
            "",
            "## Zero or negative bottles, dollars, and liters",
            "",
            "| Measure | Bottles | Dollars | Liters |",
            "| --- | ---: | ---: | ---: |",
            (
                f"| Zero | {num(quantities['bottles_zero'])} ({pct(quantities['bottles_zero'], rows)}) | "
                f"{num(quantities['dollars_zero'])} ({pct(quantities['dollars_zero'], rows)}) | "
                f"{num(quantities['liters_zero'])} ({pct(quantities['liters_zero'], rows)}) |"
            ),
            (
                f"| Negative | {num(quantities['bottles_negative'])} ({pct(quantities['bottles_negative'], rows)}) | "
                f"{num(quantities['dollars_negative'])} ({pct(quantities['dollars_negative'], rows)}) | "
                f"{num(quantities['liters_negative'])} ({pct(quantities['liters_negative'], rows)}) |"
            ),
            "",
            (
                f"Lines negative on all three measures: {num(quantities['all_three_negative'])} "
                f"({pct(quantities['all_three_negative'], rows)}). "
                f"Negative dollars total {money(quantities['negative_dollars'])}. "
                f"Negative liters total {float(quantities['negative_liters']):,.2f}. "
                f"Negative bottles total {num(quantities['negative_bottles'])}. "
                f"RINV invoice lines: {num(quantities['rinv_rows'])}. "
                f"Negative lines that also use the RINV prefix: {num(quantities['negative_rinv_rows'])}."
            ),
            "",
        ]
    )
    if result["negative_examples"]:
        lines.append("Most negative lines by dollars:")
        lines.append("")
        lines.append(
            markdown_table(
                [
                    "invoice_line_no",
                    "date",
                    "store",
                    "name",
                    "itemno",
                    "im_desc",
                    "sale_bottles",
                    "sale_dollars",
                    "sale_liters",
                ],
                result["negative_examples"],
            )
        )
        lines.append("")
    lines.extend(
        [
            "## Sale dollars versus bottles times retail price",
            "",
            (
                f"A line is comparable when `state_bottle_retail` is present and not zero "
                f"and both bottles and dollars are present. It mismatches when the absolute "
                f"gap versus bottles times retail is greater than ${tolerance:.2f}."
            ),
            "",
            (
                f"Comparable lines: {num(prices['comparable_rows'])} "
                f"({pct(prices['comparable_rows'], rows)})."
            ),
            (
                f"Within ${tolerance:.2f}: {num(prices['rows_within_tolerance'])} "
                f"({pct(prices['rows_within_tolerance'], rows)} of all lines, "
                f"{pct(prices['rows_within_tolerance'], prices['comparable_rows'])} of comparable lines)."
            ),
            (
                f"Mismatches: {num(prices['mismatch_rows'])} "
                f"({pct(prices['mismatch_rows'], rows)} of all lines, "
                f"{pct(prices['mismatch_rows'], prices['comparable_rows'])} of comparable lines)."
            ),
            (
                f"Not comparable: {num(prices['not_comparable_rows'])} "
                f"({pct(prices['not_comparable_rows'], rows)}). "
                "Retail price is null on every line, so this check has no prices to test. "
                "A mismatch count of zero is not evidence that dollars equal bottles times retail."
            ),
            "",
            "## Days with no sales and week level gaps",
            "",
            (
                f"The window has {num(window_days)} days and {num(overview['sales_days'])} days with sales. "
                f"Days with no sales: {num(len(missing_days))} "
                f"({pct(len(missing_days), window_days)})."
            ),
            "",
            "| Weekday | Days with no sales | Share of empty days |",
            "| --- | ---: | ---: |",
        ]
    )
    for weekday in WEEKDAYS:
        count = weekday_counts[weekday]
        lines.append(
            f"| {weekday} | {num(count)} | {pct(count, len(missing_days))} |"
        )
    lines.extend(["", "Empty dates:", ""])
    if missing_days:
        lines.append(markdown_table(["missing_date", "weekday"], missing_days))
    else:
        lines.append("No empty dates in the window.")
    lines.extend(
        [
            "",
            (
                f"Monday-start weeks overlapping the window: {num(weeks)}. "
                f"Weeks with no sales: {num(len(missing_weeks))} "
                f"({pct(len(missing_weeks), weeks)})."
            ),
            "",
        ]
    )
    if missing_weeks:
        lines.append(markdown_table(["week_start", "days_in_window", "first_day", "last_day"], missing_weeks))
        lines.append("")
        lines.append(
            "A week is counted when any of its days fall in the window. "
            "The empty week above is the partial week at the start of the range."
        )
    else:
        lines.append("Every week that overlaps the window has at least one sales day.")
    lines.extend(
        [
            "",
            "## Top 10 lines by sale dollars",
            "",
            (
                f"The largest line is {money(overview['max_dollars'])}, compared with an "
                f"average line of {money(overview['avg_dollars'])}. "
                "These are the ten highest dollar lines, not a statistical cutoff."
            ),
            "",
            markdown_table(
                [
                    "invoice_line_no",
                    "date",
                    "store",
                    "name",
                    "city",
                    "itemno",
                    "im_desc",
                    "sale_bottles",
                    "sale_dollars",
                    "sale_liters",
                ],
                result["top_dollars"],
            ),
            "",
        ]
    )
    return "\n".join(lines) + "\n", findings


def main() -> None:
    """Run the profile queries and write the markdown report."""
    cfg = common.load_config()
    logger = common.get_logger("profile")
    sql_path = common.resolve(cfg["paths"]["profile_sql"])
    report_path = common.resolve(cfg["paths"]["profile_report"])
    db_path = common.resolve(cfg["paths"]["database"])
    statements = split_named_sql(sql_path.read_text(encoding="utf-8"))
    params = {
        "start": cfg["date_range"]["start"],
        "end": cfg["date_range"]["end"],
        "price_tolerance": float(cfg["thresholds"]["price_tolerance_dollars"]),
    }
    logger.info("Running %s profile queries", len(statements))
    conn = common.connect(db_path)
    try:
        conn.execute("PRAGMA temp_store = MEMORY")
        conn.execute("PRAGMA cache_size = -200000")
        result: dict[str, list[dict]] = {}
        for name, sql in statements:
            started = time.perf_counter()
            cursor = conn.execute(sql, params)
            result[name] = rows_to_dicts(cursor)
            logger.info("Query %s finished in %.1f seconds", name, time.perf_counter() - started)
    finally:
        conn.close()
    report, findings = build_report(cfg, result)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(report, encoding="utf-8")
    print("")
    print("Data profile summary")
    print(f"Report: {report_path}")
    print(f"Rows profiled: {num(one(result, 'overview')['row_count'])}")
    print("Key findings:")
    for index, finding in enumerate(findings, start=1):
        print(f"{index}. {finding}")


if __name__ == "__main__":
    main()
