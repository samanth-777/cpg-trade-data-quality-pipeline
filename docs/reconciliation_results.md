# Reconciliation results

Feeds are compared with internal weekly volume at distributor, SKU, and week. A line is flagged when the absolute variance percent is over 5%.

## Before and after cleaning

Cleaning keeps one copy of a duplicate key, maps distributor SKU codes back to the internal item, and drops negative volumes.

| Stage | Feed liters | Internal liters | Overall variance | Flagged lines | Explained flagged lines |
| --- | ---: | ---: | ---: | ---: | ---: |
| Before cleaning | 46,739,260.73 | 47,036,977.92 | -0.63% | 119,714 | 113,579 (94.88%) |
| After cleaning | 46,365,624.99 | 47,036,977.92 | -1.43% | 96,556 | 87,516 (90.64%) |

After cleaning, 90.64% of flagged variances have an explained root cause. Explained causes are Duplicate, Missing Week, Unmapped Code, Unit/Format Issue, and Timing. Unknown remains on uniform volume shifts and on any other gap the tags do not cover.

Flagged lines fell after cleaning because duplicate keys were collapsed. Overall variance moved further from zero because those extra copies had been offsetting missing weeks, rejected rows, and downward volume shifts.

## Root cause of flagged lines after cleaning

| Root cause | Flagged lines |
| --- | ---: |
| Unmapped Code | 59,873 |
| Unit/Format Issue | 15,339 |
| Missing Week | 12,304 |
| Unknown | 9,040 |
