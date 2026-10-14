-- Master data for the internal book of record.
-- build_reference.py runs each named block with executescript.
-- Modes keep the most frequent non-blank value. Ties break on the value itself
-- so the result does not depend on row order.

-- name: dim_sku
DROP TABLE IF EXISTS dim_sku;
CREATE TABLE dim_sku (
    sku_id TEXT PRIMARY KEY,
    itemno TEXT NOT NULL,
    im_desc TEXT NOT NULL,
    category TEXT NOT NULL,
    category_name TEXT NOT NULL,
    pack INTEGER,
    bottle_volume_ml REAL,
    vendor_number TEXT NOT NULL,
    vendor_name TEXT NOT NULL,
    source_rows INTEGER NOT NULL
);

INSERT INTO dim_sku (
    sku_id, itemno, im_desc, category, category_name,
    pack, bottle_volume_ml, vendor_number, vendor_name, source_rows
)
WITH item_rows AS (
    SELECT itemno, COUNT(*) AS source_rows
    FROM source_sales
    GROUP BY itemno
),
desc_grouped AS (
    SELECT itemno, im_desc, COUNT(*) AS n
    FROM source_sales
    WHERE TRIM(COALESCE(im_desc, '')) <> ''
    GROUP BY itemno, im_desc
),
desc_mode AS (
    SELECT itemno, im_desc
    FROM (
        SELECT
            itemno,
            im_desc,
            ROW_NUMBER() OVER (PARTITION BY itemno ORDER BY n DESC, im_desc) AS rn
        FROM desc_grouped
    )
    WHERE rn = 1
),
category_grouped AS (
    SELECT itemno, category, category_name, COUNT(*) AS n
    FROM source_sales
    WHERE TRIM(COALESCE(category, '')) <> ''
    GROUP BY itemno, category, category_name
),
category_mode AS (
    SELECT itemno, category, category_name
    FROM (
        SELECT
            itemno,
            category,
            category_name,
            ROW_NUMBER() OVER (
                PARTITION BY itemno
                ORDER BY n DESC, category, category_name
            ) AS rn
        FROM category_grouped
    )
    WHERE rn = 1
),
pack_grouped AS (
    SELECT itemno, pack, COUNT(*) AS n
    FROM source_sales
    WHERE pack IS NOT NULL
    GROUP BY itemno, pack
),
pack_mode AS (
    SELECT itemno, pack
    FROM (
        SELECT
            itemno,
            pack,
            ROW_NUMBER() OVER (PARTITION BY itemno ORDER BY n DESC, pack) AS rn
        FROM pack_grouped
    )
    WHERE rn = 1
),
volume_grouped AS (
    SELECT itemno, bottle_volume_ml, COUNT(*) AS n
    FROM source_sales
    WHERE bottle_volume_ml IS NOT NULL
    GROUP BY itemno, bottle_volume_ml
),
volume_mode AS (
    SELECT itemno, bottle_volume_ml
    FROM (
        SELECT
            itemno,
            bottle_volume_ml,
            ROW_NUMBER() OVER (PARTITION BY itemno ORDER BY n DESC, bottle_volume_ml) AS rn
        FROM volume_grouped
    )
    WHERE rn = 1
),
vendor_grouped AS (
    SELECT itemno, vendor_number, vendor_name, COUNT(*) AS n
    FROM source_sales
    WHERE TRIM(COALESCE(vendor_number, '')) <> ''
    GROUP BY itemno, vendor_number, vendor_name
),
vendor_mode AS (
    SELECT itemno, vendor_number, vendor_name
    FROM (
        SELECT
            itemno,
            vendor_number,
            vendor_name,
            ROW_NUMBER() OVER (
                PARTITION BY itemno
                ORDER BY n DESC, vendor_number, vendor_name
            ) AS rn
        FROM vendor_grouped
    )
    WHERE rn = 1
)
SELECT
    item_rows.itemno,
    item_rows.itemno,
    COALESCE(desc_mode.im_desc, 'UNKNOWN'),
    COALESCE(category_mode.category, 'UNKNOWN'),
    COALESCE(category_mode.category_name, 'UNKNOWN'),
    pack_mode.pack,
    volume_mode.bottle_volume_ml,
    COALESCE(vendor_mode.vendor_number, 'UNKNOWN'),
    COALESCE(vendor_mode.vendor_name, 'UNKNOWN'),
    item_rows.source_rows
FROM item_rows
LEFT JOIN desc_mode USING (itemno)
LEFT JOIN category_mode USING (itemno)
LEFT JOIN pack_mode USING (itemno)
LEFT JOIN volume_mode USING (itemno)
LEFT JOIN vendor_mode USING (itemno);

CREATE INDEX idx_dim_sku_category ON dim_sku (category);

-- name: dim_account
DROP TABLE IF EXISTS dim_account;
CREATE TABLE dim_account (
    account_id TEXT PRIMARY KEY,
    store TEXT NOT NULL,
    name TEXT NOT NULL,
    city TEXT NOT NULL,
    county TEXT NOT NULL,
    territory_id TEXT,
    source_rows INTEGER NOT NULL
);

INSERT INTO dim_account (
    account_id, store, name, city, county, territory_id, source_rows
)
WITH store_rows AS (
    SELECT store, COUNT(*) AS source_rows
    FROM source_sales
    GROUP BY store
),
name_grouped AS (
    SELECT store, name, COUNT(*) AS n
    FROM source_sales
    WHERE TRIM(COALESCE(name, '')) <> ''
    GROUP BY store, name
),
name_mode AS (
    SELECT store, name
    FROM (
        SELECT
            store,
            name,
            ROW_NUMBER() OVER (PARTITION BY store ORDER BY n DESC, name) AS rn
        FROM name_grouped
    )
    WHERE rn = 1
),
city_grouped AS (
    SELECT store, city, COUNT(*) AS n
    FROM source_sales
    WHERE TRIM(COALESCE(city, '')) <> ''
    GROUP BY store, city
),
city_mode AS (
    SELECT store, city
    FROM (
        SELECT
            store,
            city,
            ROW_NUMBER() OVER (PARTITION BY store ORDER BY n DESC, city) AS rn
        FROM city_grouped
    )
    WHERE rn = 1
),
county_grouped AS (
    SELECT store, county, COUNT(*) AS n
    FROM source_sales
    WHERE TRIM(COALESCE(county, '')) <> ''
    GROUP BY store, county
),
county_mode AS (
    SELECT store, county
    FROM (
        SELECT
            store,
            county,
            ROW_NUMBER() OVER (PARTITION BY store ORDER BY n DESC, county) AS rn
        FROM county_grouped
    )
    WHERE rn = 1
)
SELECT
    store_rows.store,
    store_rows.store,
    COALESCE(name_mode.name, 'UNKNOWN'),
    COALESCE(city_mode.city, 'UNKNOWN'),
    COALESCE(county_mode.county, 'UNKNOWN'),
    NULL,
    store_rows.source_rows
FROM store_rows
LEFT JOIN name_mode USING (store)
LEFT JOIN city_mode USING (store)
LEFT JOIN county_mode USING (store);

CREATE INDEX idx_dim_account_county ON dim_account (county);

-- name: dim_territory
DROP TABLE IF EXISTS dim_territory;
CREATE TABLE dim_territory (
    territory_id TEXT PRIMARY KEY,
    county TEXT NOT NULL,
    state TEXT NOT NULL
);

INSERT INTO dim_territory (territory_id, county, state)
SELECT
    'T' || printf('%03d', ROW_NUMBER() OVER (ORDER BY county)),
    county,
    'IA'
FROM (
    SELECT DISTINCT county
    FROM dim_account
);

UPDATE dim_account
SET territory_id = (
    SELECT territory_id
    FROM dim_territory
    WHERE dim_territory.county = dim_account.county
);

CREATE INDEX idx_dim_account_territory ON dim_account (territory_id);

-- name: internal_weekly
DROP TABLE IF EXISTS internal_weekly;
CREATE TABLE internal_weekly (
    week_start TEXT NOT NULL,
    account_id TEXT NOT NULL,
    sku_id TEXT NOT NULL,
    volume_liters REAL NOT NULL,
    bottles INTEGER NOT NULL,
    dollars REAL NOT NULL,
    PRIMARY KEY (week_start, account_id, sku_id)
);

INSERT INTO internal_weekly (
    week_start, account_id, sku_id, volume_liters, bottles, dollars
)
SELECT
    date(
        date,
        '-' || ((CAST(strftime('%w', date) AS INTEGER) + 6) % 7) || ' days'
    ) AS week_start,
    store AS account_id,
    itemno AS sku_id,
    ROUND(SUM(sale_liters), 4) AS volume_liters,
    SUM(sale_bottles) AS bottles,
    ROUND(SUM(sale_dollars), 2) AS dollars
FROM source_sales
GROUP BY week_start, account_id, sku_id;

CREATE INDEX idx_internal_weekly_account ON internal_weekly (account_id);
CREATE INDEX idx_internal_weekly_sku ON internal_weekly (sku_id);
