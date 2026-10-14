# CPG Trade Data Quality Pipeline

Real public Iowa Liquor Sales data (2023 to 2024, 5,230,532 rows) with a simulated distributor feed layer.

<!-- PULL_STATUS_START -->
Socrata resource m3tr-qhgy returned HTTP 404. Loaded 5,230,532 rows from Iowa Data Hub annual exports for 2023-01-01 to 2024-12-31 (datasets 1260 for 2023 and 1261 for 2024, the public successor to m3tr-qhgy). The annual zip files overlap across CSV parts, so exact duplicate invoice lines were removed. The kept row count matches the published dataset totals.
<!-- PULL_STATUS_END -->

Beverage distributors send weekly sales files that do not match the internal book of record. This project treats public Iowa Liquor Sales as that internal source, builds simulated distributor feeds with known defects, and measures how much of the damage a quality and reconciliation pipeline can catch.

The business write-up, architecture diagram, run book, and results tables are filled in after the pipeline outputs exist.
