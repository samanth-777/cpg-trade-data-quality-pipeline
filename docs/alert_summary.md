# Alert summary

A distributor is included when any cleaned week has an absolute variance over 5%, or when validation recorded a High exception.

## Weeks over the variance threshold

| Distributor | Week | Internal liters | Feed liters | Variance |
| --- | --- | ---: | ---: | ---: |
| D02 | 2023-04-10 | 49,717.41 | 0.00 | -100.00% |
| D02 | 2023-04-17 | 48,248.32 | 0.00 | -100.00% |
| D02 | 2023-04-24 | 47,572.62 | 0.00 | -100.00% |
| D02 | 2023-05-01 | 66,486.02 | 0.00 | -100.00% |
| D02 | 2023-05-08 | 50,322.13 | 0.00 | -100.00% |
| D02 | 2023-10-23 | 49,057.01 | 44,338.11 | -9.62% |
| D03 | 2023-01-23 | 43,268.41 | 41,077.90 | -5.06% |
| D03 | 2023-03-27 | 50,148.32 | 46,706.38 | -6.86% |
| D03 | 2023-06-05 | 58,106.18 | 54,915.54 | -5.49% |
| D03 | 2023-06-12 | 54,685.85 | 48,823.76 | -10.72% |
| D03 | 2023-09-04 | 60,480.17 | 57,145.55 | -5.51% |
| D03 | 2023-10-09 | 58,273.96 | 54,396.07 | -6.65% |
| D03 | 2023-11-13 | 55,419.32 | 46,956.22 | -15.27% |
| D03 | 2023-12-25 | 56,178.77 | 52,217.87 | -7.05% |
| D03 | 2024-03-18 | 45,251.33 | 42,853.51 | -5.30% |
| D03 | 2024-04-29 | 52,125.93 | 49,453.39 | -5.13% |
| D03 | 2024-06-17 | 48,862.92 | 40,756.88 | -16.59% |
| D03 | 2024-06-24 | 61,685.62 | 58,159.16 | -5.72% |
| D03 | 2024-08-05 | 51,020.45 | 47,876.90 | -6.16% |
| D03 | 2024-12-09 | 57,673.27 | 54,200.74 | -6.02% |
| D03 | 2024-12-30 | 26,658.12 | 25,233.83 | -5.34% |
| D05 | 2024-10-21 | 54,596.73 | 0.00 | -100.00% |
| D05 | 2024-10-28 | 56,532.29 | 0.00 | -100.00% |
| D05 | 2024-11-04 | 64,401.60 | 0.00 | -100.00% |

Distributors with at least one week over the threshold: D02, D03, D05.

## Pricing/Volume shifts

| Distributor | Check | Events | Rows |
| --- | --- | ---: | ---: |
| D01 | negative_volume | 96 | 413 |
| D01 | outlier_volume | 105 | 11,894 |
| D02 | negative_volume | 79 | 278 |
| D02 | outlier_volume | 100 | 3,059 |
| D03 | negative_volume | 83 | 209 |
| D03 | outlier_volume | 105 | 3,639 |
| D03 | parse_failure | 105 | 23,887 |
| D04 | negative_volume | 105 | 2,004 |
| D04 | outlier_volume | 105 | 3,646 |
| D05 | negative_volume | 96 | 393 |
| D05 | outlier_volume | 102 | 3,443 |
| D06 | negative_volume | 94 | 359 |
| D06 | outlier_volume | 105 | 5,225 |
| D07 | negative_volume | 86 | 262 |
| D07 | outlier_volume | 105 | 3,800 |
| D08 | negative_volume | 92 | 340 |
| D08 | outlier_volume | 105 | 3,633 |

## Timeliness

| Distributor | Check | Events | Rows |
| --- | --- | ---: | ---: |
| D02 | late_file | 1 | 584,771 |
| D02 | missing_weeks | 5 | 29,329 |
| D05 | missing_weeks | 3 | 17,672 |
| D07 | late_file | 1 | 623,888 |

## Master Data Mismatch

| Distributor | Check | Events | Rows |
| --- | --- | ---: | ---: |
| D01 | duplicates | 105 | 19,700 |
| D03 | duplicates | 105 | 11,240 |
| D06 | duplicates | 105 | 11,489 |
| D07 | unmapped_sku | 105 | 18,717 |
| D08 | unmapped_sku | 105 | 17,021 |

Unit or format gaps are reconciliation lines, not validation checks.

| Distributor | Flagged lines | Absolute liters |
| --- | ---: | ---: |
| D03 | 15,339 | 180,659.15 |

Unknown lines on the injected volume-shift weeks:

| Distributor | Week | Flagged lines | Absolute liters |
| --- | --- | ---: | ---: |
| D02 | 2023-10-23 | 1,594 | 4,722.53 |
| D03 | 2023-06-12 | 1,543 | 5,880.09 |
| D03 | 2023-11-13 | 1,546 | 8,469.10 |
| D03 | 2024-06-17 | 1,392 | 8,106.04 |
