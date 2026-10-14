-- Profiling queries for source_sales.
-- profile.py splits this file on "-- name:" markers and binds :start, :end,
-- and :price_tolerance.

-- name: overview
SELECT
    COUNT(*) AS row_count,
    COUNT(DISTINCT invoice_line_no) AS distinct_invoices,
    COUNT(DISTINCT date) AS sales_days,
    COUNT(DISTINCT store) AS stores,
    COUNT(DISTINCT itemno) AS items,
    COUNT(DISTINCT category) AS categories,
    COUNT(DISTINCT county) AS counties,
    COUNT(DISTINCT vendor_number) AS vendors,
    MIN(date) AS min_date,
    MAX(date) AS max_date,
    ROUND(SUM(sale_dollars), 2) AS total_dollars,
    ROUND(SUM(sale_liters), 2) AS total_liters,
    SUM(sale_bottles) AS total_bottles,
    ROUND(AVG(sale_dollars), 2) AS avg_dollars,
    MIN(sale_dollars) AS min_dollars,
    MAX(sale_dollars) AS max_dollars
FROM source_sales;

-- name: nulls_blanks
SELECT
    SUM(CASE WHEN invoice_line_no IS NULL THEN 1 ELSE 0 END) AS invoice_line_no_nulls,
    SUM(CASE WHEN invoice_line_no IS NOT NULL AND TRIM(invoice_line_no) = '' THEN 1 ELSE 0 END) AS invoice_line_no_blanks,
    SUM(CASE WHEN date IS NULL THEN 1 ELSE 0 END) AS date_nulls,
    SUM(CASE WHEN date IS NOT NULL AND TRIM(date) = '' THEN 1 ELSE 0 END) AS date_blanks,
    SUM(CASE WHEN store IS NULL THEN 1 ELSE 0 END) AS store_nulls,
    SUM(CASE WHEN store IS NOT NULL AND TRIM(store) = '' THEN 1 ELSE 0 END) AS store_blanks,
    SUM(CASE WHEN name IS NULL THEN 1 ELSE 0 END) AS name_nulls,
    SUM(CASE WHEN name IS NOT NULL AND TRIM(name) = '' THEN 1 ELSE 0 END) AS name_blanks,
    SUM(CASE WHEN city IS NULL THEN 1 ELSE 0 END) AS city_nulls,
    SUM(CASE WHEN city IS NOT NULL AND TRIM(city) = '' THEN 1 ELSE 0 END) AS city_blanks,
    SUM(CASE WHEN county IS NULL THEN 1 ELSE 0 END) AS county_nulls,
    SUM(CASE WHEN county IS NOT NULL AND TRIM(county) = '' THEN 1 ELSE 0 END) AS county_blanks,
    SUM(CASE WHEN category IS NULL THEN 1 ELSE 0 END) AS category_nulls,
    SUM(CASE WHEN category IS NOT NULL AND TRIM(category) = '' THEN 1 ELSE 0 END) AS category_blanks,
    SUM(CASE WHEN category_name IS NULL THEN 1 ELSE 0 END) AS category_name_nulls,
    SUM(CASE WHEN category_name IS NOT NULL AND TRIM(category_name) = '' THEN 1 ELSE 0 END) AS category_name_blanks,
    SUM(CASE WHEN vendor_number IS NULL THEN 1 ELSE 0 END) AS vendor_number_nulls,
    SUM(CASE WHEN vendor_number IS NOT NULL AND TRIM(vendor_number) = '' THEN 1 ELSE 0 END) AS vendor_number_blanks,
    SUM(CASE WHEN vendor_name IS NULL THEN 1 ELSE 0 END) AS vendor_name_nulls,
    SUM(CASE WHEN vendor_name IS NOT NULL AND TRIM(vendor_name) = '' THEN 1 ELSE 0 END) AS vendor_name_blanks,
    SUM(CASE WHEN itemno IS NULL THEN 1 ELSE 0 END) AS itemno_nulls,
    SUM(CASE WHEN itemno IS NOT NULL AND TRIM(itemno) = '' THEN 1 ELSE 0 END) AS itemno_blanks,
    SUM(CASE WHEN im_desc IS NULL THEN 1 ELSE 0 END) AS im_desc_nulls,
    SUM(CASE WHEN im_desc IS NOT NULL AND TRIM(im_desc) = '' THEN 1 ELSE 0 END) AS im_desc_blanks,
    SUM(CASE WHEN pack IS NULL THEN 1 ELSE 0 END) AS pack_nulls,
    0 AS pack_blanks,
    SUM(CASE WHEN bottle_volume_ml IS NULL THEN 1 ELSE 0 END) AS bottle_volume_ml_nulls,
    0 AS bottle_volume_ml_blanks,
    SUM(CASE WHEN state_bottle_cost IS NULL THEN 1 ELSE 0 END) AS state_bottle_cost_nulls,
    0 AS state_bottle_cost_blanks,
    SUM(CASE WHEN state_bottle_retail IS NULL THEN 1 ELSE 0 END) AS state_bottle_retail_nulls,
    0 AS state_bottle_retail_blanks,
    SUM(CASE WHEN sale_bottles IS NULL THEN 1 ELSE 0 END) AS sale_bottles_nulls,
    0 AS sale_bottles_blanks,
    SUM(CASE WHEN sale_dollars IS NULL THEN 1 ELSE 0 END) AS sale_dollars_nulls,
    0 AS sale_dollars_blanks,
    SUM(CASE WHEN sale_liters IS NULL THEN 1 ELSE 0 END) AS sale_liters_nulls,
    0 AS sale_liters_blanks
FROM source_sales;

-- name: duplicate_invoices
WITH counts AS (
    SELECT invoice_line_no, COUNT(*) AS n
    FROM source_sales
    GROUP BY invoice_line_no
    HAVING COUNT(*) > 1
)
SELECT
    COUNT(*) AS duplicate_keys,
    COALESCE(SUM(n - 1), 0) AS extra_rows,
    COALESCE(SUM(n), 0) AS rows_in_duplicate_keys
FROM counts;

-- name: multi_item_summary
WITH pairs AS (
    SELECT itemno, im_desc, COUNT(*) AS n
    FROM source_sales
    GROUP BY itemno, im_desc
),
multi AS (
    SELECT itemno, COUNT(*) AS descriptions, SUM(n) AS rows
    FROM pairs
    GROUP BY itemno
    HAVING COUNT(*) > 1
)
SELECT
    (SELECT COUNT(*) FROM multi) AS items_with_many_descriptions,
    (SELECT COALESCE(SUM(rows), 0) FROM multi) AS rows_on_those_items;

-- name: multi_item_examples
WITH pairs AS (
    SELECT itemno, im_desc, COUNT(*) AS n
    FROM source_sales
    GROUP BY itemno, im_desc
),
multi AS (
    SELECT itemno
    FROM pairs
    GROUP BY itemno
    HAVING COUNT(*) > 1
)
SELECT
    p.itemno,
    COUNT(*) AS description_count,
    SUM(p.n) AS rows,
    GROUP_CONCAT(p.im_desc || ' (' || p.n || ')', ' || ') AS descriptions
FROM pairs AS p
INNER JOIN multi AS m ON m.itemno = p.itemno
GROUP BY p.itemno
ORDER BY rows DESC
LIMIT 10;

-- name: multi_store_summary
WITH pairs AS (
    SELECT store, name, COUNT(*) AS n
    FROM source_sales
    GROUP BY store, name
),
multi AS (
    SELECT store, COUNT(*) AS spellings, SUM(n) AS rows
    FROM pairs
    GROUP BY store
    HAVING COUNT(*) > 1
)
SELECT
    (SELECT COUNT(*) FROM multi) AS stores_with_many_names,
    (SELECT COALESCE(SUM(rows), 0) FROM multi) AS rows_on_those_stores;

-- name: multi_store_examples
WITH pairs AS (
    SELECT store, name, COUNT(*) AS n
    FROM source_sales
    GROUP BY store, name
),
multi AS (
    SELECT store
    FROM pairs
    GROUP BY store
    HAVING COUNT(*) > 1
)
SELECT
    p.store,
    COUNT(*) AS name_count,
    SUM(p.n) AS rows,
    GROUP_CONCAT(p.name || ' (' || p.n || ')', ' || ') AS names
FROM pairs AS p
INNER JOIN multi AS m ON m.store = p.store
GROUP BY p.store
ORDER BY rows DESC
LIMIT 10;

-- name: multi_category_summary
WITH pairs AS (
    SELECT category, category_name, COUNT(*) AS n
    FROM source_sales
    GROUP BY category, category_name
),
multi AS (
    SELECT category, COUNT(*) AS names, SUM(n) AS rows
    FROM pairs
    GROUP BY category
    HAVING COUNT(*) > 1
)
SELECT
    (SELECT COUNT(*) FROM multi) AS categories_with_many_names,
    (SELECT COALESCE(SUM(rows), 0) FROM multi) AS rows_on_those_categories;

-- name: multi_category_examples
WITH pairs AS (
    SELECT category, category_name, COUNT(*) AS n
    FROM source_sales
    GROUP BY category, category_name
),
multi AS (
    SELECT category
    FROM pairs
    GROUP BY category
    HAVING COUNT(*) > 1
)
SELECT
    p.category,
    COUNT(*) AS name_count,
    SUM(p.n) AS rows,
    GROUP_CONCAT(p.category_name || ' (' || p.n || ')', ' || ') AS names
FROM pairs AS p
INNER JOIN multi AS m ON m.category = p.category
GROUP BY p.category
ORDER BY rows DESC
LIMIT 10;

-- name: nonpositive
SELECT
    SUM(CASE WHEN sale_bottles = 0 THEN 1 ELSE 0 END) AS bottles_zero,
    SUM(CASE WHEN sale_bottles < 0 THEN 1 ELSE 0 END) AS bottles_negative,
    SUM(CASE WHEN sale_dollars = 0 THEN 1 ELSE 0 END) AS dollars_zero,
    SUM(CASE WHEN sale_dollars < 0 THEN 1 ELSE 0 END) AS dollars_negative,
    SUM(CASE WHEN sale_liters = 0 THEN 1 ELSE 0 END) AS liters_zero,
    SUM(CASE WHEN sale_liters < 0 THEN 1 ELSE 0 END) AS liters_negative,
    SUM(CASE WHEN sale_bottles < 0 AND sale_dollars < 0 AND sale_liters < 0 THEN 1 ELSE 0 END) AS all_three_negative,
    ROUND(SUM(CASE WHEN sale_dollars < 0 THEN sale_dollars ELSE 0 END), 2) AS negative_dollars,
    ROUND(SUM(CASE WHEN sale_liters < 0 THEN sale_liters ELSE 0 END), 2) AS negative_liters,
    SUM(CASE WHEN sale_bottles < 0 THEN sale_bottles ELSE 0 END) AS negative_bottles,
    SUM(CASE WHEN invoice_line_no LIKE 'RINV-%' THEN 1 ELSE 0 END) AS rinv_rows,
    SUM(CASE WHEN sale_bottles < 0 AND sale_dollars < 0 AND sale_liters < 0 AND invoice_line_no LIKE 'RINV-%' THEN 1 ELSE 0 END) AS negative_rinv_rows
FROM source_sales;

-- name: negative_examples
SELECT
    invoice_line_no,
    date,
    store,
    name,
    itemno,
    im_desc,
    sale_bottles,
    sale_dollars,
    sale_liters
FROM source_sales
WHERE sale_dollars < 0 OR sale_bottles < 0 OR sale_liters < 0
ORDER BY sale_dollars ASC
LIMIT 5;

-- name: price_check
SELECT
    SUM(CASE
        WHEN state_bottle_retail IS NOT NULL
         AND state_bottle_retail <> 0
         AND sale_bottles IS NOT NULL
         AND sale_dollars IS NOT NULL
        THEN 1 ELSE 0
    END) AS comparable_rows,
    SUM(CASE
        WHEN state_bottle_retail IS NOT NULL
         AND state_bottle_retail <> 0
         AND sale_bottles IS NOT NULL
         AND sale_dollars IS NOT NULL
         AND ABS(sale_dollars - (sale_bottles * state_bottle_retail)) <= :price_tolerance
        THEN 1 ELSE 0
    END) AS rows_within_tolerance,
    SUM(CASE
        WHEN state_bottle_retail IS NOT NULL
         AND state_bottle_retail <> 0
         AND sale_bottles IS NOT NULL
         AND sale_dollars IS NOT NULL
         AND ABS(sale_dollars - (sale_bottles * state_bottle_retail)) > :price_tolerance
        THEN 1 ELSE 0
    END) AS mismatch_rows,
    SUM(CASE
        WHEN state_bottle_retail IS NULL OR state_bottle_retail = 0
          OR sale_bottles IS NULL OR sale_dollars IS NULL
        THEN 1 ELSE 0
    END) AS not_comparable_rows
FROM source_sales;

-- name: missing_days
WITH RECURSIVE dates(d) AS (
    SELECT date(:start)
    UNION ALL
    SELECT date(d, '+1 day') FROM dates WHERE d < date(:end)
)
SELECT
    dates.d AS missing_date,
    CASE CAST(strftime('%w', dates.d) AS INTEGER)
        WHEN 0 THEN 'Sunday'
        WHEN 1 THEN 'Monday'
        WHEN 2 THEN 'Tuesday'
        WHEN 3 THEN 'Wednesday'
        WHEN 4 THEN 'Thursday'
        WHEN 5 THEN 'Friday'
        WHEN 6 THEN 'Saturday'
    END AS weekday
FROM dates
LEFT JOIN (SELECT DISTINCT date AS d FROM source_sales) AS sales
    ON sales.d = dates.d
WHERE sales.d IS NULL
ORDER BY dates.d;

-- name: window_days
WITH RECURSIVE dates(d) AS (
    SELECT date(:start)
    UNION ALL
    SELECT date(d, '+1 day') FROM dates WHERE d < date(:end)
)
SELECT COUNT(*) AS window_days FROM dates;

-- name: missing_weeks
WITH RECURSIVE dates(d) AS (
    SELECT date(:start)
    UNION ALL
    SELECT date(d, '+1 day') FROM dates WHERE d < date(:end)
),
cal AS (
    SELECT
        d,
        date(d, '-' || ((CAST(strftime('%w', d) AS INTEGER) + 6) % 7) || ' days') AS week_start
    FROM dates
),
sales_weeks AS (
    SELECT DISTINCT
        date(date, '-' || ((CAST(strftime('%w', date) AS INTEGER) + 6) % 7) || ' days') AS week_start
    FROM source_sales
)
SELECT
    cal.week_start,
    COUNT(*) AS days_in_window,
    MIN(cal.d) AS first_day,
    MAX(cal.d) AS last_day
FROM cal
LEFT JOIN sales_weeks AS sales USING (week_start)
WHERE sales.week_start IS NULL
GROUP BY cal.week_start
ORDER BY cal.week_start;

-- name: week_count
WITH RECURSIVE dates(d) AS (
    SELECT date(:start)
    UNION ALL
    SELECT date(d, '+1 day') FROM dates WHERE d < date(:end)
)
SELECT COUNT(DISTINCT date(d, '-' || ((CAST(strftime('%w', d) AS INTEGER) + 6) % 7) || ' days')) AS weeks
FROM dates;

-- name: top_dollars
SELECT
    invoice_line_no,
    date,
    store,
    name,
    city,
    itemno,
    im_desc,
    sale_bottles,
    ROUND(sale_dollars, 2) AS sale_dollars,
    ROUND(sale_liters, 2) AS sale_liters
FROM source_sales
ORDER BY sale_dollars DESC
LIMIT 10;
