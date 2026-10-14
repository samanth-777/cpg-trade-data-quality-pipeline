# Reconciliation results

Feeds are compared with internal weekly volume at distributor, SKU, and week. A line is flagged when the absolute variance percent is over 5%.

## Before and after cleaning

Cleaning keeps one copy of a duplicate key, maps distributor SKU codes back to the internal item, and drops negative volumes.

Total absolute variance percent is the sum of absolute liter gaps divided by internal liters. Flagged rate is flagged lines divided by lines compared.

Lines compared: 1,311,419. Internal liters: 47,036,977.92.

| Stage | Absolute variance | Flagged lines | Flagged rate |
| --- | ---: | ---: | ---: |
| Before cleaning | 3.60% | 119,714 | 9.13% |
| After cleaning | 2.82% | 96,556 | 7.36% |

Signed net variance, feed liters minus internal liters divided by internal liters, was -0.63% before cleaning and -1.43% after cleaning.

## Why signed variance rose

Missing weeks and unmapped codes are unrecoverable from the feed. Duplicate copies had been offsetting those gaps, so removing the copies makes the signed shortfall larger. Absolute variance and the flagged line count fall because those extra copies are no longer counted as gaps.

After cleaning, 90.64% of flagged variances have an explained root cause. Explained causes are Duplicate, Missing Week, Unmapped Code, Unit/Format Issue, and Timing. Unknown remains on uniform volume shifts and on any other gap the tags do not cover.

## Root cause of flagged lines after cleaning

| Root cause | Flagged lines | Share of flagged |
| --- | ---: | ---: |
| Unmapped Code | 59,873 | 62.01% |
| Unit/Format Issue | 15,339 | 15.89% |
| Missing Week | 12,304 | 12.74% |
| Unknown | 9,040 | 9.36% |
