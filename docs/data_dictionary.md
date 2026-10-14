# Data dictionary

SQLite database: `data/pipeline.db`. CSV copies of the reference tables live in `data/reference/`. Pipeline outputs live in `data/output/` and are gitignored. Types below are the SQLite types. Blank type means the column was created by a query without an explicit type. Those values are numeric.

`source_sales` is loaded from the Iowa Data Hub annual exports, dataset 1260 for 2023 and dataset 1261 for 2024. It is not loaded from the Socrata API. The pull script probes `m3tr-qhgy` and uses the Hub files when that resource returns HTTP 404.

## source_sales

Invoice lines from the Iowa Data Hub annual exports, one row per `invoice_line_no`. 5,230,532 rows. CSV: `data/raw/iowa_sales.csv`.

| Column | Type | Description |
| --- | --- | --- |
| invoice_line_no | TEXT | Invoice line id. Unique after the pull removes overlapping zip parts. |
| date | TEXT | Sale date, `YYYY-MM-DD`. |
| store | TEXT | Store number. Leading zeros are kept. |
| name | TEXT | Store name as printed on the line. |
| city | TEXT | Store city. Blank on 1,599 lines. |
| county | TEXT | Store county. Blank on the same 1,599 lines. |
| category | TEXT | Category code. |
| category_name | TEXT | Category description. |
| vendor_number | TEXT | Vendor number. |
| vendor_name | TEXT | Vendor name. |
| itemno | TEXT | Item number. |
| im_desc | TEXT | Item description as printed on the line. |
| pack | INTEGER | Bottles per case. |
| bottle_volume_ml | REAL | Bottle size in milliliters. |
| state_bottle_cost | REAL | State bottle cost. Null on every row in this extract. |
| state_bottle_retail | REAL | State bottle retail. Null on every row in this extract. |
| sale_bottles | INTEGER | Bottles sold. Negative on return lines. |
| sale_dollars | REAL | Dollars sold. Negative on return lines. |
| sale_liters | REAL | Liters sold. Negative on return lines. |

## dim_sku

One row per item number. Description, category, pack, size, and vendor are the most frequent non-blank values. 6,561 rows. CSV: `data/reference/dim_sku.csv`.

| Column | Type | Description |
| --- | --- | --- |
| sku_id | TEXT | Internal SKU. Equal to `itemno`. |
| itemno | TEXT | Same value as `sku_id`. |
| im_desc | TEXT | Most frequent description. |
| category | TEXT | Most frequent category code. |
| category_name | TEXT | Most frequent category name. |
| pack | INTEGER | Most frequent pack. |
| bottle_volume_ml | REAL | Most frequent bottle size. |
| vendor_number | TEXT | Most frequent vendor number. |
| vendor_name | TEXT | Most frequent vendor name. |
| source_rows | INTEGER | Invoice lines that used this item number. |

## dim_account

One row per store. Name, city, and county are the most frequent non-blank values. 2,273 rows. CSV: `data/reference/dim_account.csv`.

| Column | Type | Description |
| --- | --- | --- |
| account_id | TEXT | Internal account. Equal to `store`. |
| store | TEXT | Same value as `account_id`. |
| name | TEXT | Most frequent store name. |
| city | TEXT | Most frequent city. |
| county | TEXT | Most frequent county. |
| territory_id | TEXT | Territory for that county. Null only if the county is missing. |
| source_rows | INTEGER | Invoice lines for this store. |

## dim_territory

One row per county that appears on an account. 99 rows. CSV: `data/reference/dim_territory.csv`.

| Column | Type | Description |
| --- | --- | --- |
| territory_id | TEXT | `T001` through `T099`. |
| county | TEXT | County name. |
| state | TEXT | Always `IA` in this extract. |

## dim_calendar

One row per calendar date in the configured window. 731 rows. CSV: `data/reference/dim_calendar.csv`.

| Column | Type | Description |
| --- | --- | --- |
| date | TEXT | Calendar date, `YYYY-MM-DD`. |
| iso_week | TEXT | ISO week, `YYYY-Www`. |
| week_start | TEXT | Monday of that week. |
| month | TEXT | `YYYY-MM`. |
| quarter | TEXT | `YYYYQn`. |

## distributor_map

County to distributor. Eight distributors, assigned so volume is as even as whole counties allow. 99 rows. CSV: `data/reference/distributor_map.csv`.

| Column | Type | Description |
| --- | --- | --- |
| distributor_id | TEXT | `D01` through `D08`. |
| territory_id | TEXT | Territory for the county. |
| county | TEXT | County assigned to the distributor. |
| volume_liters | REAL | Internal liters in that county. |

## sku_crosswalk

Distributor item code to internal SKU for D07 and D08. Codes that were injected as unmapped are not in this table. 9,974 rows. CSV: `data/reference/sku_crosswalk.csv`.

| Column | Type | Description |
| --- | --- | --- |
| distributor_id | TEXT | `D07` or `D08`. |
| dist_sku | TEXT | Code printed on the distributor file. |
| sku_id | TEXT | Internal SKU. |

## defect_log

One row per injected defect event. 749 events. CSV: `data/reference/defect_log.csv`.

| Column | Type | Description |
| --- | --- | --- |
| distributor | TEXT | Distributor the defect was applied to. |
| week | TEXT | Week start, or the file's max week for a late file. |
| defect_type | TEXT | `duplicate_rows`, `missing_weeks`, `unmapped_sku`, `negative_volume`, `mixed_date_format`, `volume_distortion`, or `late_file`. |
| rows_affected | INTEGER | Rows in the feed touched by that event. |

## file_manifest

One row per simulated feed file. CSV: `data/feeds/file_manifest.csv`. Also loaded into SQLite before validation.

| Column | Type | Description |
| --- | --- | --- |
| file_name | TEXT | File name under `data/feeds/`. |
| distributor_id | TEXT | Distributor that owns the file. |
| row_count | INTEGER | Rows written, including injected duplicates. |
| max_week_start | TEXT | Latest week start in the file. |
| received_date | TEXT | Simulated receipt date. |
| is_late | INTEGER | 1 when receipt is more than 10 days after `max_week_start`. |

## internal_weekly

Internal source of truth after the invoice extract is summed. Grain is week, account, SKU. CSV: `data/reference/internal_weekly.csv` (gitignored, about 177 MB).

| Column | Type | Description |
| --- | --- | --- |
| week_start | TEXT | Monday week start. |
| account_id | TEXT | Store number. |
| sku_id | TEXT | Item number. |
| volume_liters | REAL | Sum of `sale_liters`, including returns. |
| bottles | INTEGER | Sum of `sale_bottles`. |
| dollars | REAL | Sum of `sale_dollars`. |

## stg_feeds

Distributor rows that parsed. Grain is the feed line after column mapping and, where the crosswalk hits, SKU mapping. Duplicates and negatives are still here.

| Column | Type | Description |
| --- | --- | --- |
| distributor_id | TEXT | Distributor. |
| week_start | TEXT | Week start, ISO date. |
| account_id | TEXT | Account code from the file, stripped when the feed config says so. |
| sku_id | TEXT | Internal SKU when the crosswalk matched, otherwise the raw code. |
| volume_liters | REAL | Liters. Case files are multiplied by 9. |
| bottles | REAL | Bottle quantity from the file. |
| dollars | REAL | Dollar amount from the file. |
| source_file | TEXT | File name. |
| load_ts | TEXT | UTC timestamp of the load. |

## stg_rejects

Rows that failed parsing. On this run, 23,887 rows, all from D03 with reason `invalid date`.

| Column | Type | Description |
| --- | --- | --- |
| distributor_id | TEXT | Distributor. |
| source_file | TEXT | File name. |
| row_number | INTEGER | 1-based data row in the file, header is row 1 so the first data row is 2. |
| reject_reason | TEXT | Why the row was not loaded. |
| raw_week | TEXT | Week text before parsing. |
| raw_account | TEXT | Account text before parsing. |
| raw_sku | TEXT | SKU text before parsing. |
| raw_volume | TEXT | Volume text before parsing. |
| raw_bottles | TEXT | Bottle text before parsing. |
| raw_dollars | TEXT | Dollar text before parsing. |

## ingestion_log

One row per feed file.

| Column | Type | Description |
| --- | --- | --- |
| file | TEXT | File name. |
| rows_read | INTEGER | Data rows read. |
| rows_loaded | INTEGER | Rows written to `stg_feeds`. |
| rows_rejected | INTEGER | Rows written to `stg_rejects`. |
| received_date | TEXT | From `file_manifest`. |

## exceptions

One row per distributor, week, and check. CSV: `data/output/exceptions.csv` and `docs/sample_output/exceptions.csv`.

| Column | Type | Description |
| --- | --- | --- |
| distributor_id | TEXT | Distributor. |
| week | TEXT | Week start, or blank when the check is file level. |
| check_name | TEXT | `duplicates`, `missing_weeks`, `unmapped_sku`, `unmapped_account`, `negative_volume`, `zero_volume`, `outlier_volume`, `parse_failure`, or `late_file`. |
| issue_description | TEXT | Plain-language description. |
| row_count | INTEGER | Rows or files involved. |
| severity | TEXT | `High`, `Medium`, or `Low`. |

## dq_scorecard

One row per distributor. Scores are 0 to 100. CSV: `data/output/dq_scorecard.csv` and `docs/sample_output/dq_scorecard.csv`.

| Column | Type | Description |
| --- | --- | --- |
| distributor_id | TEXT | Distributor. |
| completeness | REAL | 100 times present weeks over expected weeks. |
| uniqueness | REAL | 100 times one minus extra duplicate rows over loaded rows. |
| validity | REAL | 100 times one minus invalid plus rejected rows over loaded plus rejected rows. |
| timeliness | REAL | 100 times one minus late files over files. |
| overall | REAL | Unweighted mean of the four scores. |
| loaded_rows | INTEGER | Rows in `stg_feeds`. |
| rejected_rows | INTEGER | Rows in `stg_rejects`. |
| expected_weeks | INTEGER | Internal weeks for this distributor inside the calendar. |
| present_weeks | INTEGER | Of those weeks, how many appear in `stg_feeds`. |
| duplicate_extra_rows | INTEGER | Extra copies beyond the first row of a key. |
| invalid_rows | INTEGER | Distinct loaded rows that are negative, zero, unmapped, or an outlier. |
| late_files | INTEGER | Files with `is_late` = 1. |
| files | INTEGER | Files for this distributor. |

## reconciliation

Distributor, SKU, and week compared with the internal book. `feed_volume` is after cleaning. CSV export columns are the after-cleaning set: `data/output/reconciliation.csv`. The top 25 by absolute variance are in `data/output/top_discrepancies.csv` and `docs/sample_output/top_discrepancies.csv`.

| Column | Type | Description |
| --- | --- | --- |
| distributor_id | TEXT | Distributor. |
| sku_id | TEXT | Internal SKU, or the raw code if it never mapped. |
| week | TEXT | Week start. |
| internal_volume | REAL | Liters from `internal_weekly` for this distributor, SKU, and week. |
| feed_volume_before | REAL | Liters from `stg_feeds` before cleaning. |
| feed_volume | REAL | Liters after dedupe, SKU mapping, and dropping negatives. |
| variance_before | REAL | `feed_volume_before` minus `internal_volume`. |
| variance | REAL | `feed_volume` minus `internal_volume`. |
| variance_pct_before | REAL | Variance before divided by internal volume. Null when internal volume is near zero. |
| variance_pct | REAL | Variance after divided by internal volume. Null when internal volume is near zero. |
| flagged_before | INTEGER | 1 when the before-cleaning absolute percent is over 5%, or the liter gap is at least 0.01 on a near-zero internal line. |
| flagged | INTEGER | Same rule after cleaning. |
| root_cause | TEXT | After cleaning: Missing Week, Unmapped Code, Unit/Format Issue, Timing, Unknown, or blank when not flagged. |
| root_cause_before | TEXT | Same tags, plus Duplicate when the before and after volumes differ enough to explain the gap. |

## Working tables

These are rebuilt by `sql/reconcile.sql` and are not exported.

| Table | Columns | Description |
| --- | --- | --- |
| internal_dist_week | distributor_id, sku_id, week_start, internal_volume | Internal liters rolled to distributor, SKU, and week. |
| feed_before_agg | distributor_id, sku_id, week_start, feed_volume | Staged liters before cleaning. |
| feed_after_agg | distributor_id, sku_id, week_start, feed_volume | Staged liters after cleaning. |
| recon_support | distributor_id, week_start, defect_type | Defect events used to tag a root cause. |
| recon_rejects | distributor_id, week_start, sku_id, rejected_liters | Rejected liters that can explain a unit or format gap. |

## Feed files

Files in `data/feeds/` are the simulated distributor extracts. The logical columns, after the mapping in `config.yaml`, are distributor, week, account, SKU, volume, bottles, and dollars. Headers, delimiters, date formats, and units differ by distributor. D05 and D06 report volume in cases (liters divided by 9). D07 and D08 use distributor item codes and trailing spaces.
