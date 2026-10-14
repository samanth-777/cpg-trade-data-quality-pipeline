# Business requirements

## Problem

Trade sales close depends on weekly files from distributors matching the internal book. On this book the internal source is public Iowa Liquor Sales: 5,230,532 invoice lines from 2023-01-02 through 2024-12-31, $893,306,076.14 and 47,036,977.92 liters. The files that arrive do not share a schema, a date format, or a unit of measure. Some weeks never arrive. Some item codes are not on the internal list. Some volumes are shifted just enough to stay inside a normal range.

Without a shared check, Sales restates volume, Trade Finance cannot support a deduction, and distributors resend files that still do not tie. The pipeline makes the gap measurable: what failed ingestion, what failed a quality check, and what still does not match after cleaning.

## Stakeholders

| Stakeholder | Need |
| --- | --- |
| Sales | A weekly volume they can stand behind, by distributor, account, and SKU. |
| Trade Finance | A variance over 5% with a root cause before a deduction is booked. |
| Distributors | A specific file, week, and defect to fix, not a rejected workbook with no reason. |
| IT | One schema, one load log, and a run that can be repeated from `python run_all.py`. |
| Data vendor | A published row count the extract can be tied to. The kept 5,230,532 lines match the Iowa Data Hub published totals for datasets 1260 and 1261. |

## Functional requirements

1. Pull invoice lines for 2023-01-01 through 2024-12-31 and store them in `source_sales`.
2. Profile nulls, duplicate keys, conflicting descriptions and store names, negative measures, calendar gaps, and dollar outliers.
3. Build SKU, account, territory, and calendar masters, using the most frequent value when the source disagrees with itself.
4. Build `internal_weekly` at week, account, and SKU. This is the internal source of truth.
5. Assign counties to distributors D01 through D08 and write a weekly file per distributor. Formats differ on purpose: CSV, pipe-delimited text, and Excel, with cases on D05 and D06 and distributor item codes on D07 and D08.
6. Ingest every file through the feed contract in `config.yaml`. Rows that fail parsing go to `stg_rejects`. Every file is logged.
7. Run quality checks and score each distributor on completeness, uniqueness, validity, and timeliness.
8. Clean the staged feed (one row per key, map item codes, drop negative volumes) and reconcile it to `internal_weekly` at distributor, SKU, and week. Flag absolute variance over 5%.
9. Publish an Excel workbook a non-technical reviewer can filter without opening the database.

## Data requirements

- Grain of the internal book after rollup: Monday week start, account, SKU.
- Grain of reconciliation: distributor, SKU, week.
- Keys: `invoice_line_no` on the invoice extract, `sku_id` on `dim_sku`, `account_id` on `dim_account`, `distributor_id` plus county on `distributor_map`.
- Dates in the staged feed are ISO week starts (`YYYY-MM-DD`), regardless of the format in the source file.
- Volume in `stg_feeds` and `reconciliation` is liters. Case files are converted with 9 liters per case.
- A variance percent is null when internal volume is near zero. Those lines are flagged only when the absolute liter gap is at least 0.01.
- Root cause tags are Duplicate, Missing Week, Unmapped Code, Unit/Format Issue, Timing, and Unknown.
- Thresholds, paths, and seed 42 live in `config.yaml`, not in the scripts.

## Acceptance criteria

1. `source_sales` contains 5,230,532 distinct invoice lines, and the SQLite count matches the CSV.
2. `internal_weekly` dollars, liters, and bottles match the invoice extract: $893,306,076.14, 47,036,977.92 liters, 62,654,117 bottles.
3. Every injected defect event is written to `defect_log.csv`.
4. Validation catches structural events. On this run that is 745 of 749 events (99.47%). The four misses are the uniform volume shifts.
5. Reconciliation reports variance before and after cleaning. On this run: -0.63% and 119,714 flagged lines before, -1.43% and 96,556 flagged lines after. 90.64% of the after-cleaning flags have a named root cause.
6. `excel/variance_workbook.xlsx` opens with Summary, Weekly_Compare, Pivot_Ready, Top_Discrepancies, SKU_Master, Account_Master, and README, and is under 25 MB. This file is 0.85 MB.
7. Each script runs with `python src/<name>.py` and `python run_all.py` runs them in order.

## Success metrics

| Metric | Target | This run |
| --- | --- | ---: |
| Invoice lines loaded vs published hub totals | Match | 5,230,532 |
| Structural defect events detected | At least 95% | 99.47% (745 of 749) |
| Flagged variances with an explained root cause | At least 80% | 90.64% |
| Workbook size | Under 25 MB | 0.85 MB |
| Price tie-out | Within $0.05 where a retail price exists | Not measurable, both price fields are empty |
