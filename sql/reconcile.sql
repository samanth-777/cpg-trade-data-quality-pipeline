-- Compare distributor feeds with the internal weekly book.
-- reconcile.py runs the named blocks, then fills variance and root cause.

-- name: build_aggs
DROP TABLE IF EXISTS internal_dist_week;
CREATE TABLE internal_dist_week AS
SELECT
    m.distributor_id,
    w.sku_id,
    w.week_start,
    ROUND(SUM(w.volume_liters), 4) AS internal_volume
FROM internal_weekly AS w
INNER JOIN dim_account AS a ON a.account_id = w.account_id
INNER JOIN distributor_map AS m ON m.county = a.county
GROUP BY m.distributor_id, w.sku_id, w.week_start;

CREATE INDEX idx_internal_dist_week ON internal_dist_week (distributor_id, sku_id, week_start);

DROP TABLE IF EXISTS feed_before_agg;
CREATE TABLE feed_before_agg AS
SELECT
    f.distributor_id,
    f.sku_id,
    f.week_start,
    ROUND(SUM(f.volume_liters), 4) AS feed_volume
FROM stg_feeds AS f
GROUP BY f.distributor_id, f.sku_id, f.week_start;

CREATE INDEX idx_feed_before_agg ON feed_before_agg (distributor_id, sku_id, week_start);

DROP TABLE IF EXISTS feed_after_agg;
CREATE TABLE feed_after_agg AS
WITH ranked AS (
    SELECT
        f.distributor_id,
        f.week_start,
        f.account_id,
        COALESCE(x.sku_id, f.sku_id) AS sku_id,
        f.volume_liters,
        ROW_NUMBER() OVER (
            PARTITION BY f.distributor_id, f.week_start, f.account_id, COALESCE(x.sku_id, f.sku_id)
            ORDER BY f.rowid
        ) AS rn
    FROM stg_feeds AS f
    LEFT JOIN sku_crosswalk AS x
        ON x.distributor_id = f.distributor_id
       AND x.dist_sku = f.sku_id
    WHERE f.volume_liters >= 0
)
SELECT
    distributor_id,
    sku_id,
    week_start,
    ROUND(SUM(volume_liters), 4) AS feed_volume
FROM ranked
WHERE rn = 1
GROUP BY distributor_id, sku_id, week_start;

CREATE INDEX idx_feed_after_agg ON feed_after_agg (distributor_id, sku_id, week_start);

DROP TABLE IF EXISTS recon_support;
CREATE TABLE recon_support AS
SELECT distributor AS distributor_id, week AS week_start, defect_type
FROM defect_log
WHERE defect_type IN ('missing_weeks', 'unmapped_sku', 'volume_distortion', 'duplicate_rows', 'late_file');

CREATE INDEX idx_recon_support ON recon_support (distributor_id, week_start, defect_type);

DROP TABLE IF EXISTS recon_rejects;
CREATE TABLE recon_rejects AS
SELECT
    distributor_id,
    raw_week AS week_start,
    TRIM(raw_sku) AS sku_id,
    ROUND(SUM(CAST(raw_volume AS REAL)), 4) AS rejected_liters
FROM stg_rejects
WHERE raw_week GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]'
GROUP BY distributor_id, raw_week, TRIM(raw_sku);

CREATE INDEX idx_recon_rejects ON recon_rejects (distributor_id, sku_id, week_start);

-- name: build_recon
DROP TABLE IF EXISTS reconciliation;
CREATE TABLE reconciliation AS
WITH keys AS (
    SELECT distributor_id, sku_id, week_start FROM internal_dist_week
    UNION
    SELECT distributor_id, sku_id, week_start FROM feed_before_agg
    UNION
    SELECT distributor_id, sku_id, week_start FROM feed_after_agg
),
base AS (
    SELECT
        k.distributor_id,
        k.sku_id,
        k.week_start AS week,
        ROUND(COALESCE(i.internal_volume, 0), 4) AS internal_volume,
        ROUND(COALESCE(b.feed_volume, 0), 4) AS feed_volume_before,
        ROUND(COALESCE(a.feed_volume, 0), 4) AS feed_volume,
        ROUND(COALESCE(b.feed_volume, 0) - COALESCE(i.internal_volume, 0), 4) AS variance_before,
        ROUND(COALESCE(a.feed_volume, 0) - COALESCE(i.internal_volume, 0), 4) AS variance,
        CASE WHEN miss.distributor_id IS NULL THEN 0 ELSE 1 END AS is_missing_week,
        CASE WHEN unmapped.distributor_id IS NULL THEN 0 ELSE 1 END AS is_unmapped_week,
        CASE WHEN distorted.distributor_id IS NULL THEN 0 ELSE 1 END AS is_distorted_week,
        CASE WHEN known.sku_id IS NULL THEN 0 ELSE 1 END AS is_known_sku,
        COALESCE(rej.rejected_liters, 0) AS rejected_liters
    FROM keys AS k
    LEFT JOIN internal_dist_week AS i
        ON i.distributor_id = k.distributor_id
       AND i.sku_id = k.sku_id
       AND i.week_start = k.week_start
    LEFT JOIN feed_before_agg AS b
        ON b.distributor_id = k.distributor_id
       AND b.sku_id = k.sku_id
       AND b.week_start = k.week_start
    LEFT JOIN feed_after_agg AS a
        ON a.distributor_id = k.distributor_id
       AND a.sku_id = k.sku_id
       AND a.week_start = k.week_start
    LEFT JOIN (
        SELECT DISTINCT distributor_id, week_start
        FROM recon_support
        WHERE defect_type = 'missing_weeks'
    ) AS miss
        ON miss.distributor_id = k.distributor_id
       AND miss.week_start = k.week_start
    LEFT JOIN (
        SELECT DISTINCT distributor_id, week_start
        FROM recon_support
        WHERE defect_type = 'unmapped_sku'
    ) AS unmapped
        ON unmapped.distributor_id = k.distributor_id
       AND unmapped.week_start = k.week_start
    LEFT JOIN (
        SELECT DISTINCT distributor_id, week_start
        FROM recon_support
        WHERE defect_type = 'volume_distortion'
    ) AS distorted
        ON distorted.distributor_id = k.distributor_id
       AND distorted.week_start = k.week_start
    LEFT JOIN dim_sku AS known ON known.sku_id = k.sku_id
    LEFT JOIN recon_rejects AS rej
        ON rej.distributor_id = k.distributor_id
       AND rej.sku_id = k.sku_id
       AND rej.week_start = k.week_start
)
SELECT
    distributor_id,
    sku_id,
    week,
    internal_volume,
    feed_volume_before,
    feed_volume,
    variance_before,
    variance,
    CASE
        WHEN ABS(internal_volume) < 0.0001 THEN NULL
        ELSE ROUND(variance_before / internal_volume, 6)
    END AS variance_pct_before,
    CASE
        WHEN ABS(internal_volume) < 0.0001 THEN NULL
        ELSE ROUND(variance / internal_volume, 6)
    END AS variance_pct,
    CASE
        WHEN ABS(internal_volume) < 0.0001 AND ABS(variance_before) >= 0.01 THEN 1
        WHEN ABS(internal_volume) >= 0.0001 AND ABS(variance_before / internal_volume) > __THRESHOLD__ THEN 1
        ELSE 0
    END AS flagged_before,
    CASE
        WHEN ABS(internal_volume) < 0.0001 AND ABS(variance) >= 0.01 THEN 1
        WHEN ABS(internal_volume) >= 0.0001 AND ABS(variance / internal_volume) > __THRESHOLD__ THEN 1
        ELSE 0
    END AS flagged,
    CASE
        WHEN NOT (
            (ABS(internal_volume) < 0.0001 AND ABS(variance) >= 0.01)
            OR (ABS(internal_volume) >= 0.0001 AND ABS(variance / internal_volume) > __THRESHOLD__)
        ) THEN ''
        WHEN is_missing_week = 1 AND ABS(feed_volume) < 0.0001 THEN 'Missing Week'
        WHEN is_known_sku = 0 THEN 'Unmapped Code'
        WHEN is_unmapped_week = 1 AND feed_volume + 0.0001 < internal_volume THEN 'Unmapped Code'
        WHEN is_distorted_week = 1 THEN 'Unknown'
        WHEN rejected_liters > 0 AND rejected_liters >= 0.5 * ABS(variance) THEN 'Unit/Format Issue'
        ELSE 'Unknown'
    END AS root_cause,
    CASE
        WHEN NOT (
            (ABS(internal_volume) < 0.0001 AND ABS(variance_before) >= 0.01)
            OR (ABS(internal_volume) >= 0.0001 AND ABS(variance_before / internal_volume) > __THRESHOLD__)
        ) THEN ''
        WHEN is_missing_week = 1 AND ABS(feed_volume_before) < 0.0001 THEN 'Missing Week'
        WHEN is_known_sku = 0 THEN 'Unmapped Code'
        WHEN is_unmapped_week = 1 AND feed_volume_before + 0.0001 < internal_volume THEN 'Unmapped Code'
        WHEN is_distorted_week = 1 THEN 'Unknown'
        WHEN ABS(feed_volume_before - feed_volume) >= 0.5 * ABS(variance_before)
         AND ABS(feed_volume_before - feed_volume) >= 0.01 THEN 'Duplicate'
        WHEN rejected_liters > 0 AND rejected_liters >= 0.5 * ABS(variance_before) THEN 'Unit/Format Issue'
        ELSE 'Unknown'
    END AS root_cause_before
FROM base;

CREATE INDEX idx_reconciliation_flagged ON reconciliation (flagged);

-- name: distortion_weeks
WITH week_totals AS (
    SELECT
        distributor_id,
        week,
        SUM(internal_volume) AS internal_volume,
        SUM(feed_volume) AS feed_volume
    FROM reconciliation
    GROUP BY distributor_id, week
)
SELECT
    d.distributor AS distributor_id,
    d.week AS week,
    ROUND(COALESCE(w.internal_volume, 0), 4) AS internal_volume,
    ROUND(COALESCE(w.feed_volume, 0), 4) AS feed_volume,
    CASE
        WHEN ABS(COALESCE(w.internal_volume, 0)) < 0.0001
         AND ABS(COALESCE(w.feed_volume, 0) - COALESCE(w.internal_volume, 0)) >= 0.01 THEN 1
        WHEN ABS(COALESCE(w.internal_volume, 0)) >= 0.0001
         AND ABS((w.feed_volume - w.internal_volume) / w.internal_volume) > __THRESHOLD__ THEN 1
        ELSE 0
    END AS caught
FROM defect_log AS d
LEFT JOIN week_totals AS w
    ON w.distributor_id = d.distributor
   AND w.week = d.week
WHERE d.defect_type = 'volume_distortion'
ORDER BY d.distributor, d.week;
