-- Validation checks for staged distributor feeds.
-- validate.py binds :start, :end, :std_mult, and :timeliness_days.

-- name: duplicate_weeks
WITH keyed AS (
    SELECT distributor_id, week_start, account_id, sku_id, COUNT(*) AS n
    FROM stg_feeds
    GROUP BY distributor_id, week_start, account_id, sku_id
    HAVING COUNT(*) > 1
)
SELECT
    distributor_id,
    week_start AS week,
    SUM(n - 1) AS row_count,
    COUNT(*) AS duplicate_keys
FROM keyed
GROUP BY distributor_id, week_start;

-- name: missing_weeks
WITH expected AS (
    SELECT m.distributor_id, w.week_start, COUNT(*) AS internal_rows
    FROM internal_weekly AS w
    INNER JOIN dim_account AS a ON a.account_id = w.account_id
    INNER JOIN distributor_map AS m ON m.county = a.county
    WHERE w.week_start IN (
        SELECT DISTINCT week_start
        FROM dim_calendar
        WHERE date BETWEEN :start AND :end
    )
    GROUP BY m.distributor_id, w.week_start
),
present AS (
    SELECT DISTINCT distributor_id, week_start
    FROM stg_feeds
)
SELECT
    expected.distributor_id,
    expected.week_start AS week,
    expected.internal_rows AS row_count
FROM expected
LEFT JOIN present
    ON present.distributor_id = expected.distributor_id
   AND present.week_start = expected.week_start
WHERE present.week_start IS NULL;

-- name: unmapped_sku
SELECT distributor_id, week_start AS week, COUNT(*) AS row_count
FROM stg_feeds AS f
LEFT JOIN dim_sku AS s ON s.sku_id = f.sku_id
WHERE s.sku_id IS NULL
GROUP BY distributor_id, week_start;

-- name: unmapped_account
SELECT distributor_id, week_start AS week, COUNT(*) AS row_count
FROM stg_feeds AS f
LEFT JOIN dim_account AS a ON a.account_id = f.account_id
WHERE a.account_id IS NULL
GROUP BY distributor_id, week_start;

-- name: negative_volume
SELECT distributor_id, week_start AS week, COUNT(*) AS row_count
FROM stg_feeds
WHERE volume_liters < 0
GROUP BY distributor_id, week_start;

-- name: zero_volume
SELECT distributor_id, week_start AS week, COUNT(*) AS row_count
FROM stg_feeds
WHERE volume_liters = 0
GROUP BY distributor_id, week_start;

-- name: outlier_volume
WITH sku_stats AS (
    SELECT
        sku_id,
        AVG(volume_liters) AS avg_volume,
        AVG(volume_liters * volume_liters) - AVG(volume_liters) * AVG(volume_liters) AS variance
    FROM stg_feeds
    WHERE volume_liters > 0
    GROUP BY sku_id
    HAVING COUNT(*) >= 8
)
SELECT f.distributor_id, f.week_start AS week, COUNT(*) AS row_count
FROM stg_feeds AS f
INNER JOIN sku_stats AS s ON s.sku_id = f.sku_id
WHERE s.variance > 0
  AND f.volume_liters > s.avg_volume + (:std_mult * sqrt(s.variance))
GROUP BY f.distributor_id, f.week_start;

-- name: parse_failures
SELECT
    distributor_id,
    CASE
        WHEN raw_week GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]' THEN raw_week
        ELSE COALESCE(raw_week, '')
    END AS week,
    COUNT(*) AS row_count,
    GROUP_CONCAT(DISTINCT reject_reason) AS reasons
FROM stg_rejects
GROUP BY distributor_id, week;

-- name: late_files
SELECT
    i.file AS source_file,
    m.distributor_id,
    m.max_week_start AS week,
    i.rows_read AS row_count,
    i.received_date,
    m.max_week_start,
    CAST(julianday(i.received_date) - julianday(m.max_week_start) AS INTEGER) AS lag_days
FROM ingestion_log AS i
INNER JOIN (
    SELECT file_name, distributor_id, max_week_start, received_date
    FROM file_manifest
) AS m ON m.file_name = i.file
WHERE julianday(i.received_date) - julianday(m.max_week_start) > :timeliness_days;

-- name: loaded_totals
SELECT distributor_id, COUNT(*) AS loaded_rows, COUNT(DISTINCT week_start) AS present_weeks
FROM stg_feeds
GROUP BY distributor_id;

-- name: expected_weeks
SELECT m.distributor_id, COUNT(DISTINCT w.week_start) AS expected_weeks
FROM internal_weekly AS w
INNER JOIN dim_account AS a ON a.account_id = w.account_id
INNER JOIN distributor_map AS m ON m.county = a.county
WHERE w.week_start IN (
    SELECT DISTINCT week_start
    FROM dim_calendar
    WHERE date BETWEEN :start AND :end
)
GROUP BY m.distributor_id;

-- name: duplicate_extra
WITH keyed AS (
    SELECT distributor_id, COUNT(*) AS n
    FROM stg_feeds
    GROUP BY distributor_id, week_start, account_id, sku_id
    HAVING COUNT(*) > 1
)
SELECT distributor_id, COALESCE(SUM(n - 1), 0) AS extra_rows
FROM keyed
GROUP BY distributor_id;

-- name: invalid_rows
WITH sku_stats AS (
    SELECT
        sku_id,
        AVG(volume_liters) AS avg_volume,
        AVG(volume_liters * volume_liters) - AVG(volume_liters) * AVG(volume_liters) AS variance
    FROM stg_feeds
    WHERE volume_liters > 0
    GROUP BY sku_id
    HAVING COUNT(*) >= 8
)
SELECT f.distributor_id, COUNT(*) AS invalid_rows
FROM stg_feeds AS f
LEFT JOIN dim_sku AS s ON s.sku_id = f.sku_id
LEFT JOIN dim_account AS a ON a.account_id = f.account_id
LEFT JOIN sku_stats AS st ON st.sku_id = f.sku_id
WHERE f.volume_liters < 0
   OR f.volume_liters = 0
   OR s.sku_id IS NULL
   OR a.account_id IS NULL
   OR (
        st.variance > 0
        AND f.volume_liters > st.avg_volume + (:std_mult * sqrt(st.variance))
      )
GROUP BY f.distributor_id;

-- name: reject_totals
SELECT distributor_id, COUNT(*) AS rejected_rows
FROM stg_rejects
GROUP BY distributor_id;

-- name: file_counts
SELECT
    m.distributor_id,
    COUNT(*) AS files,
    SUM(CASE
        WHEN julianday(i.received_date) - julianday(m.max_week_start) > :timeliness_days THEN 1
        ELSE 0
    END) AS late_files
FROM ingestion_log AS i
INNER JOIN file_manifest AS m ON m.file_name = i.file
GROUP BY m.distributor_id;
