# Iowa Liquor Sales Data Profile

Profile of `source_sales`: 5,230,532 invoice lines from 2023-01-02 to 2024-12-31. The configured window is 2023-01-01 to 2024-12-31 (731 days).

## Key Findings

1. Bottle cost and bottle retail are empty on every one of the 5,230,532 lines. Sale dollars cannot be checked against bottles times the retail price, because those price fields are not populated in the public extract.
2. 6,661 lines (0.13%) are negative on bottles, dollars, and liters together, totaling -$1,016,371.54. 6,643 of them use an RINV invoice prefix, which marks a return. Keeping the negative signs in a volume total understates what was sold.
3. 289 of 6,561 item numbers (4.40%) use more than one product description. Those items cover 68,548 lines (1.31%). A single description per item number will disagree with part of the history.
4. 48 of 2,273 store numbers (2.11%) appear under more than one name. Those stores cover 141,389 lines (2.70%). Matching accounts on the name string will split them.
5. 125 of 731 days in the window (17.10%) have no sales. 85 of those days are Saturdays and 37 are Sundays. 105 of 106 Monday-start weeks that overlap the window contain at least one sales day. The other week starts 2022-12-26 and only includes 2023-01-01 inside the window, which has no sales.

## Coverage

The extract has 2,273 stores, 6,561 item numbers, 48 category codes, 100 county values, and 286 vendors. Sales dollars total $893,306,076.14, liters total 47,036,977.92, and bottles total 62,654,117. The average line is $170.79.

## Nulls and blanks by column

Text blanks are empty or whitespace-only strings. Numeric fields have no blank state. An empty numeric value was stored as null.

| Column | Nulls | Null % | Blanks | Blank % | Null or blank | Null or blank % |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| invoice_line_no | 0 | 0.00% | 0 | 0.00% | 0 | 0.00% |
| date | 0 | 0.00% | 0 | 0.00% | 0 | 0.00% |
| store | 0 | 0.00% | 0 | 0.00% | 0 | 0.00% |
| name | 0 | 0.00% | 0 | 0.00% | 0 | 0.00% |
| city | 0 | 0.00% | 1,599 | 0.03% | 1,599 | 0.03% |
| county | 0 | 0.00% | 1,599 | 0.03% | 1,599 | 0.03% |
| category | 0 | 0.00% | 0 | 0.00% | 0 | 0.00% |
| category_name | 0 | 0.00% | 0 | 0.00% | 0 | 0.00% |
| vendor_number | 0 | 0.00% | 0 | 0.00% | 0 | 0.00% |
| vendor_name | 0 | 0.00% | 0 | 0.00% | 0 | 0.00% |
| itemno | 0 | 0.00% | 0 | 0.00% | 0 | 0.00% |
| im_desc | 0 | 0.00% | 0 | 0.00% | 0 | 0.00% |
| pack | 0 | 0.00% | 0 | 0.00% | 0 | 0.00% |
| bottle_volume_ml | 0 | 0.00% | 0 | 0.00% | 0 | 0.00% |
| state_bottle_cost | 5,230,532 | 100.00% | 0 | 0.00% | 5,230,532 | 100.00% |
| state_bottle_retail | 5,230,532 | 100.00% | 0 | 0.00% | 5,230,532 | 100.00% |
| sale_bottles | 0 | 0.00% | 0 | 0.00% | 0 | 0.00% |
| sale_dollars | 0 | 0.00% | 0 | 0.00% | 0 | 0.00% |
| sale_liters | 0 | 0.00% | 0 | 0.00% | 0 | 0.00% |

## Duplicate invoice_line_no

Duplicate keys: 0 (0.00% of rows). Extra copies beyond the first: 0. Rows sitting in duplicate keys: 0.

Invoice line number is unique in the loaded extract.

## Item numbers with more than one description

289 of 6,561 item numbers (4.40%) have more than one `im_desc`. They account for 68,548 lines (1.31%).

Largest items by line count:

| itemno | description_count | rows | descriptions |
| --- | --- | --- | --- |
| 75208 | 2 | 5673 | KINKY PINK MINI (5659) // KINKY PINK MINI - USE CODE 75206 (14) |
| 21236 | 2 | 3711 | 1792 SMALL BATCH (2883) // RIDGEMONT RESERVE 1792 (828) |
| 59154 | 2 | 3469 | 1800 ULTIMATE MARGARITA (667) // 1800 ULTIMATE MARGARITA PET (2802) |
| 76500 | 2 | 3068 | THE ORIGINAL PICKLE SHOT DILL PICKLE VODKA MINI (2264) // THE ORIGINAL PICKLE SHOT MINI (DILL PICKLE VODKA) (804) |
| 66725 | 2 | 1645 | SHANKY''S WHIP (465) // SHANKYS WHIP BLACK SPIRITS (1180) |
| 17207 | 2 | 1643 | BARREL PROOF BOURBON WHISKEY (741) // CEDAR RIDGE BARREL PROOF (902) |
| 76842 | 2 | 1562 | THE ORIGINAL PICKLE SHOT MINI (SPICY PICKLE VODKA) (487) // THE ORIGINAL PICKLE SHOT SPICY PICKLE VODKA MINI (1075) |
| 19009 | 2 | 1412 | JEFFERSONS BOURBON (314) // JEFFERSONS VERY SMALL BATCH (1098) |
| 17917 | 2 | 1374 | ELIJAH CRAIG  BARREL PROOF (652) // ELIJAH CRAIG BARREL PROOF (722) |
| 920376 | 2 | 1373 | OLD FORESTER 1920 (11) // SOOH OLD FORESTER 1920 (1362) |

## Stores with more than one name spelling

48 of 2,273 store numbers (2.11%) have more than one `name`. They account for 141,389 lines (2.70%).

Largest stores by line count:

| store | name_count | rows | names |
| --- | --- | --- | --- |
| 2190 | 2 | 21135 | CENTRAL CITY 2 (25) // CENTRAL CITY LIQUOR, INC. (21110) |
| 4988 | 2 | 16946 | HAPPY'S WINE & SPIRITS (16753) // HAPPY'S WINE & SPIRITS WHOLESALE (193) |
| 5444 | 2 | 14641 | DECORAH MART / DECORAH (4) // MARSHALL BEER WINE SPIRITS (14637) |
| 5889 | 2 | 8091 | SUPER QUICK LIQUOR / WDM (7993) // SUPER QUICK MART / WINDSOR HEIGHTS (98) |
| 5327 | 2 | 7553 | MEGA SAVER (1108) // MEGA SAVER / COUNCIL BLUFFS (6445) |
| 6260 | 3 | 5530 | SUPER QUICK LIQUOR / WDM (155) // SUPER QUICK MART / WINDSOR HEIGHTS (43) // SUPERQUICK LIQUOR VINE / WEST DES MOINES (5332) |
| 3651 | 2 | 5144 | INDY 66 #928 / INDIANOLA (16) // WAL-MART 1491 / INDIANOLA (5128) |
| 4265 | 2 | 4701 | KWIK STOP 3 / WATERLO (1094) // KWIK STOP 3 / WATERLOO (3607) |
| 5949 | 2 | 4458 | HAWKEYE LIQUOR & TOBACCO / IOWA CITY (66) // UPTOWN LIQUOR & TOBACCO / CEDAR RAPIDS (4392) |
| 3944 | 2 | 4377 | SAM'S CLUB 4973 / DUBUQUE (4376) // SAM'S CLUB 4973 / DUBUQUE9 (1) |

## Category codes with more than one category name

0 of 48 category codes (0.00%) have more than one `category_name`. They account for 0 lines (0.00%).

Every category code maps to one category name.

## Zero or negative bottles, dollars, and liters

| Measure | Bottles | Dollars | Liters |
| --- | ---: | ---: | ---: |
| Zero | 0 (0.00%) | 0 (0.00%) | 0 (0.00%) |
| Negative | 6,661 (0.13%) | 6,661 (0.13%) | 6,661 (0.13%) |

Lines negative on all three measures: 6,661 (0.13%). Negative dollars total -$1,016,371.54. Negative liters total -50,284.34. Negative bottles total -70,417. RINV invoice lines: 6,658. Negative lines that also use the RINV prefix: 6,643.

Most negative lines by dollars:

| invoice_line_no | date | store | name | itemno | im_desc | sale_bottles | sale_dollars | sale_liters |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| RINV-05091100002 | 2024-01-19 | 3944 | SAM'S CLUB 4973 / DUBUQUE | 936859 | MEMBERS MARK VODKA | -768 | -8355.84 | -1344.0 |
| RINV-04682100041 | 2023-06-09 | 4162 | FAREWAY STORES #963 / CEDAR RAPIDS | 38178 | TITOS HANDMADE VODKA | -180 | -5130.0 | -315.0 |
| RINV-04842600233 | 2023-09-12 | 2633 | HY-VEE #3 / BDI / DES MOINES | 21597 | TEN HIGH | -648 | -4801.68 | -648.0 |
| RINV-05238500056 | 2024-04-29 | 2558 | HY-VEE FOOD STORE (1433) / MOUNT PLEASANT | 10802 | CROWN ROYAL PEACH | -168 | -4408.32 | -126.0 |
| RINV-05167200052 | 2024-03-11 | 3524 | SAM'S CLUB 6568 / AMES | 77683 | SMIRNOFF KISSED CARAMEL | -336 | -4159.68 | -252.0 |

## Sale dollars versus bottles times retail price

A line is comparable when `state_bottle_retail` is present and not zero and both bottles and dollars are present. It mismatches when the absolute gap versus bottles times retail is greater than $0.05.

Comparable lines: 0 (0.00%).
Within $0.05: 0 (0.00% of all lines, 0.00% of comparable lines).
Mismatches: 0 (0.00% of all lines, 0.00% of comparable lines).
Not comparable: 5,230,532 (100.00%). Retail price is null on every line, so this check has no prices to test. A mismatch count of zero is not evidence that dollars equal bottles times retail.

## Days with no sales and week level gaps

The window has 731 days and 606 days with sales. Days with no sales: 125 (17.10%).

| Weekday | Days with no sales | Share of empty days |
| --- | ---: | ---: |
| Monday | 1 | 0.80% |
| Tuesday | 0 | 0.00% |
| Wednesday | 1 | 0.80% |
| Thursday | 1 | 0.80% |
| Friday | 0 | 0.00% |
| Saturday | 85 | 68.00% |
| Sunday | 37 | 29.60% |

Empty dates:

| missing_date | weekday |
| --- | --- |
| 2023-01-01 | Sunday |
| 2023-01-07 | Saturday |
| 2023-01-14 | Saturday |
| 2023-01-21 | Saturday |
| 2023-01-28 | Saturday |
| 2023-02-04 | Saturday |
| 2023-02-11 | Saturday |
| 2023-02-18 | Saturday |
| 2023-02-19 | Sunday |
| 2023-02-25 | Saturday |
| 2023-02-26 | Sunday |
| 2023-03-04 | Saturday |
| 2023-03-05 | Sunday |
| 2023-03-11 | Saturday |
| 2023-03-12 | Sunday |
| 2023-03-18 | Saturday |
| 2023-03-19 | Sunday |
| 2023-03-25 | Saturday |
| 2023-04-01 | Saturday |
| 2023-04-02 | Sunday |
| 2023-04-08 | Saturday |
| 2023-04-15 | Saturday |
| 2023-04-16 | Sunday |
| 2023-04-22 | Saturday |
| 2023-04-23 | Sunday |
| 2023-04-29 | Saturday |
| 2023-04-30 | Sunday |
| 2023-05-06 | Saturday |
| 2023-05-07 | Sunday |
| 2023-05-13 | Saturday |
| 2023-05-14 | Sunday |
| 2023-05-20 | Saturday |
| 2023-05-27 | Saturday |
| 2023-05-28 | Sunday |
| 2023-06-04 | Sunday |
| 2023-06-10 | Saturday |
| 2023-06-11 | Sunday |
| 2023-06-17 | Saturday |
| 2023-06-18 | Sunday |
| 2023-06-24 | Saturday |
| 2023-06-25 | Sunday |
| 2023-07-01 | Saturday |
| 2023-07-02 | Sunday |
| 2023-07-09 | Sunday |
| 2023-07-15 | Saturday |
| 2023-07-16 | Sunday |
| 2023-07-22 | Saturday |
| 2023-07-29 | Saturday |
| 2023-08-05 | Saturday |
| 2023-08-06 | Sunday |
| 2023-08-12 | Saturday |
| 2023-08-19 | Saturday |
| 2023-08-20 | Sunday |
| 2023-08-26 | Saturday |
| 2023-09-03 | Sunday |
| 2023-09-10 | Sunday |
| 2023-09-16 | Saturday |
| 2023-09-17 | Sunday |
| 2023-09-23 | Saturday |
| 2023-09-24 | Sunday |
| 2023-09-30 | Saturday |
| 2023-10-01 | Sunday |
| 2023-10-07 | Saturday |
| 2023-10-08 | Sunday |
| 2023-10-14 | Saturday |
| 2023-10-21 | Saturday |
| 2023-10-28 | Saturday |
| 2023-10-29 | Sunday |
| 2023-11-04 | Saturday |
| 2023-12-02 | Saturday |
| 2023-12-17 | Sunday |
| 2023-12-23 | Saturday |
| 2023-12-24 | Sunday |
| 2023-12-25 | Monday |
| 2023-12-31 | Sunday |
| 2024-01-06 | Saturday |
| 2024-01-13 | Saturday |
| 2024-01-20 | Saturday |
| 2024-01-27 | Saturday |
| 2024-02-03 | Saturday |
| 2024-02-10 | Saturday |
| 2024-02-17 | Saturday |
| 2024-02-24 | Saturday |
| 2024-03-02 | Saturday |
| 2024-03-09 | Saturday |
| 2024-03-16 | Saturday |
| 2024-03-23 | Saturday |
| 2024-03-30 | Saturday |
| 2024-03-31 | Sunday |
| 2024-04-06 | Saturday |
| 2024-04-07 | Sunday |
| 2024-04-13 | Saturday |
| 2024-04-20 | Saturday |
| 2024-04-27 | Saturday |
| 2024-05-04 | Saturday |
| 2024-05-05 | Sunday |
| 2024-05-18 | Saturday |
| 2024-05-26 | Sunday |
| 2024-06-08 | Saturday |
| 2024-06-15 | Saturday |
| 2024-06-22 | Saturday |
| 2024-07-13 | Saturday |
| 2024-07-27 | Saturday |
| 2024-08-03 | Saturday |
| 2024-08-10 | Saturday |
| 2024-08-17 | Saturday |
| 2024-08-24 | Saturday |
| 2024-08-31 | Saturday |
| 2024-09-01 | Sunday |
| 2024-09-07 | Saturday |
| 2024-09-14 | Saturday |
| 2024-09-21 | Saturday |
| 2024-09-28 | Saturday |
| 2024-10-05 | Saturday |
| 2024-10-12 | Saturday |
| 2024-10-19 | Saturday |
| 2024-10-26 | Saturday |
| 2024-11-02 | Saturday |
| 2024-11-16 | Saturday |
| 2024-11-23 | Saturday |
| 2024-11-28 | Thursday |
| 2024-11-30 | Saturday |
| 2024-12-07 | Saturday |
| 2024-12-14 | Saturday |
| 2024-12-25 | Wednesday |

Monday-start weeks overlapping the window: 106. Weeks with no sales: 1 (0.94%).

| week_start | days_in_window | first_day | last_day |
| --- | --- | --- | --- |
| 2022-12-26 | 1 | 2023-01-01 | 2023-01-01 |

A week is counted when any of its days fall in the window. The empty week above is the partial week at the start of the range.

## Top 10 lines by sale dollars

The largest line is $260,832.00, compared with an average line of $170.79. These are the ten highest dollar lines, not a statistical cutoff.

| invoice_line_no | date | store | name | city | itemno | im_desc | sale_bottles | sale_dollars | sale_liters |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| INV-63744400001 | 2023-10-30 | 2633 | HY-VEE #3 / BDI / DES MOINES | DES MOINES | 38177 | TITOS HANDMADE VODKA | 13200 | 260832.0 | 13200.0 |
| INV-66284100050 | 2024-01-15 | 2633 | HY-VEE #3 / BDI / DES MOINES | DES MOINES | 38177 | TITOS HANDMADE VODKA | 13200 | 260832.0 | 13200.0 |
| INV-69661600001 | 2024-04-29 | 2633 | HY-VEE #3 / BDI / DES MOINES | DES MOINES | 38177 | TITOS HANDMADE VODKA | 13200 | 260832.0 | 13200.0 |
| INV-72306000001 | 2024-07-18 | 2633 | HY-VEE #3 / BDI / DES MOINES | DES MOINES | 38177 | TITOS HANDMADE VODKA | 13200 | 260832.0 | 13200.0 |
| INV-75673900001 | 2024-10-24 | 2633 | HY-VEE #3 / BDI / DES MOINES | DES MOINES | 38177 | TITOS HANDMADE VODKA | 13200 | 260832.0 | 13200.0 |
| INV-57786400063 | 2023-04-24 | 2633 | HY-VEE #3 / BDI / DES MOINES | DES MOINES | 38177 | TITOS HANDMADE VODKA | 11880 | 234748.8 | 11880.0 |
| INV-55381600120 | 2023-01-30 | 2633 | HY-VEE #3 / BDI / DES MOINES | DES MOINES | 38177 | TITOS HANDMADE VODKA | 9900 | 195624.0 | 9900.0 |
| INV-60606600056 | 2023-07-24 | 2633 | HY-VEE #3 / BDI / DES MOINES | DES MOINES | 38177 | TITOS HANDMADE VODKA | 8580 | 169540.8 | 8580.0 |
| INV-60730800005 | 2023-07-27 | 2663 | HY-VEE FOOD STORE / URBANDALE | URBANDALE | 11296 | CROWN ROYAL | 5400 | 141696.0 | 4050.0 |
| INV-71770700049 | 2024-07-01 | 2512 | HY-VEE WINE AND SPIRITS #1 (1281) / IOWA CITY | IOWA CITY | 38177 | TITOS HANDMADE VODKA | 6600 | 130416.0 | 6600.0 |

