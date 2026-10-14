# Detection results

Injected events are rows in `defect_log.csv`. An event is caught when validation writes an exception for the same distributor and week.

| Defect type | Injected | Caught | Detection rate |
| --- | ---: | ---: | ---: |
| duplicate_rows | 315 | 315 | 100.00% |
| late_file | 2 | 2 | 100.00% |
| missing_weeks | 8 | 8 | 100.00% |
| mixed_date_format | 105 | 105 | 100.00% |
| negative_volume | 105 | 105 | 100.00% |
| unmapped_sku | 210 | 210 | 100.00% |
| volume_distortion | 4 | 0 | 0.00% |

Overall, validation caught 745 of 749 injected events (99.47%).

Volume distortion is the miss. A uniform 8 to 15 percent move still looks like a normal number, so it does not trip duplicates, mapping, sign, parse, or lateness checks. The reconciliation step measures that shift against the internal book.

## Scorecard

Scores run from 0 to 100. Overall is the unweighted mean of completeness, uniqueness, validity, and timeliness.

| Distributor | Completeness | Uniqueness | Validity | Timeliness | Overall |
| --- | ---: | ---: | ---: | ---: | ---: |
| D01 | 100.00 | 98.04 | 98.75 | 100.00 | 99.20 |
| D02 | 95.24 | 100.00 | 99.39 | 0.00 | 73.66 |
| D03 | 100.00 | 98.04 | 95.32 | 100.00 | 98.34 |
| D04 | 100.00 | 100.00 | 98.98 | 100.00 | 99.75 |
| D05 | 97.14 | 100.00 | 99.33 | 100.00 | 99.12 |
| D06 | 100.00 | 98.04 | 99.01 | 100.00 | 99.26 |
| D07 | 100.00 | 100.00 | 96.32 | 0.00 | 74.08 |
| D08 | 100.00 | 100.00 | 96.27 | 100.00 | 99.07 |
