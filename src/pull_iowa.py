"""Download Iowa liquor sales and load the source_sales table.

The historical Socrata resource m3tr-qhgy is requested first, with paged
reads of 50,000 rows, stable :id ordering, retries, and an optional app
token. As of October 2026 that route returns HTTP 404. The same public
series now ships as annual Iowa Data Hub exports (dataset 1260 for 2023
and dataset 1261 for 2024). This script uses those exports when Socrata
is unavailable, still writing 50,000 row chunks and remaining resumable.

If a full 2023 to 2024 pull is projected to exceed the configured runtime
budget, the script keeps 2024 only and records that decision.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import time
import zipfile
from pathlib import Path

import pandas as pd
import requests
from tqdm import tqdm

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common  # noqa: E402

KEEP_COLUMNS: list[str] = []
NUMERIC_COLUMNS: list[str] = []
INTEGER_COLUMNS: list[str] = []


def load_dotenv(path: Path) -> None:
    """Load KEY=VALUE pairs from .env without overriding existing variables."""
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def request_headers(cfg: dict) -> dict:
    """Build request headers, including the optional Socrata app token."""
    headers = {"User-Agent": "cpg-trade-data-quality-pipeline/1.0"}
    token_var = cfg["api"].get("token_env", "SOCRATA_APP_TOKEN")
    token = os.environ.get(token_var, "").strip()
    if token:
        headers["X-App-Token"] = token
    return headers


def request_with_retries(session: requests.Session, url: str, cfg: dict, **kwargs):
    """GET a URL with exponential backoff on transient failures."""
    logger = common.get_logger("pull_iowa")
    retries = int(cfg["api"].get("retries", 5))
    delay = 2.0
    last_error: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            response = session.get(url, **kwargs)
            if response.status_code in {429, 500, 502, 503, 504}:
                raise requests.HTTPError(
                    f"HTTP {response.status_code} from {url}", response=response
                )
            response.raise_for_status()
            return response
        except (requests.RequestException, requests.HTTPError) as exc:
            last_error = exc
            logger.warning("Request attempt %s/%s failed: %s", attempt, retries, exc)
            if attempt == retries:
                break
            time.sleep(delay)
            delay = min(delay * 2, 60)
    raise RuntimeError(f"Request failed after {retries} attempts: {url}") from last_error


def read_checkpoint(path: Path) -> dict:
    """Return the resume checkpoint, or an empty one."""
    if not path.exists():
        return {"completed_dataset_ids": [], "parts": {}, "source": ""}
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    payload.setdefault("completed_dataset_ids", [])
    payload.setdefault("parts", {})
    return payload


def write_checkpoint(path: Path, payload: dict) -> None:
    """Persist the resume checkpoint next to the raw extract."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(".json.tmp")
    with temp.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)
    temp.replace(path)


def probe_socrata(session: requests.Session, cfg: dict) -> int:
    """Return the HTTP status of a one-row Socrata probe."""
    logger = common.get_logger("pull_iowa")
    url = cfg["api"]["socrata_url"]
    try:
        response = session.get(
            url,
            params={"$limit": 1, "$order": cfg["api"]["order"]},
            headers=request_headers(cfg),
            timeout=45,
        )
        logger.info("Socrata probe %s returned HTTP %s", url, response.status_code)
        return int(response.status_code)
    except requests.RequestException as exc:
        logger.warning("Socrata probe failed: %s", exc)
        return 0


def normalize_frame(frame: pd.DataFrame, source: str, cfg: dict) -> pd.DataFrame:
    """Rename, cast, and order a chunk to the source_sales schema."""
    if source == "iowa_data_hub":
        frame = frame.rename(columns=cfg["columns"]["hub_rename"])
    missing = [col for col in KEEP_COLUMNS if col not in frame.columns]
    if missing:
        raise RuntimeError(f"Download is missing columns: {missing}")
    frame = frame[KEEP_COLUMNS].copy()
    for col in KEEP_COLUMNS:
        if col in NUMERIC_COLUMNS:
            continue
        frame[col] = frame[col].fillna("").astype(str)
        if col == "date":
            frame[col] = frame[col].str.slice(0, 10)
    for col in NUMERIC_COLUMNS:
        frame[col] = pd.to_numeric(frame[col].replace("", pd.NA), errors="coerce")
    for col in INTEGER_COLUMNS:
        as_float = frame[col]
        whole = as_float.dropna()
        if not whole.empty and (whole == whole.round()).all():
            frame[col] = as_float.round().astype("Int64")
    start = cfg["date_range"]["start"]
    end = cfg["date_range"]["end"]
    mask = (frame["date"] >= start) & (frame["date"] <= end) & (frame["date"] != "")
    return frame.loc[mask]


def append_chunk(csv_path: Path, frame: pd.DataFrame, write_header: bool) -> None:
    """Append one standardized chunk to the raw CSV."""
    frame.to_csv(csv_path, mode="a", header=write_header, index=False)


def fetch_socrata_pages(session: requests.Session, cfg: dict, csv_path: Path, deadline: float) -> int:
    """Page the Socrata API and append 50,000 row chunks. Returns rows written."""
    logger = common.get_logger("pull_iowa")
    page_size = int(cfg["api"]["page_size"])
    start = cfg["date_range"]["start"]
    end = cfg["date_range"]["end"]
    where = f"date between '{start}T00:00:00' and '{end}T23:59:59'"
    select = ",".join(KEEP_COLUMNS)
    offset = 0
    written = 0
    write_header = not csv_path.exists() or csv_path.stat().st_size == 0
    progress = tqdm(unit="rows", desc="Socrata pages")
    while True:
        if time.monotonic() > deadline and offset > 0:
            progress.close()
            raise TimeoutError(
                f"Socrata pull exceeded {cfg['api']['max_runtime_minutes']} minutes"
            )
        params = {
            "$select": select,
            "$where": where,
            "$order": cfg["api"]["order"],
            "$limit": page_size,
            "$offset": offset,
        }
        response = request_with_retries(
            session,
            cfg["api"]["socrata_url"],
            cfg,
            params=params,
            headers=request_headers(cfg),
            timeout=120,
        )
        payload = response.json()
        if isinstance(payload, dict):
            progress.close()
            raise RuntimeError(f"Socrata returned an object, not rows: {str(payload)[:300]}")
        if not payload:
            break
        frame = normalize_frame(pd.DataFrame(payload), "socrata", cfg)
        append_chunk(csv_path, frame, write_header)
        write_header = False
        batch_n = len(payload)
        written += len(frame)
        offset += batch_n
        progress.update(batch_n)
        logger.info("Appended Socrata offset %s (%s rows kept)", offset, len(frame))
        if batch_n < page_size:
            break
    progress.close()
    return written


def hub_metadata(session: requests.Session, cfg: dict, dataset_id: int) -> dict:
    """Fetch Iowa Data Hub dataset metadata, including numRows."""
    url = f"{cfg['api']['hub_base_url'].rstrip('/')}/{dataset_id}/"
    response = request_with_retries(
        session, url, cfg, headers=request_headers(cfg), timeout=60
    )
    body = response.json()
    if isinstance(body, dict) and isinstance(body.get("data"), dict):
        return body["data"]
    if isinstance(body, dict):
        return body
    raise RuntimeError(f"Unexpected metadata payload for dataset {dataset_id}")


def download_hub_zip(session: requests.Session, cfg: dict, dataset_id: int, dest: Path) -> None:
    """Download one annual export. The rows.csv route returns a zip archive."""
    logger = common.get_logger("pull_iowa")
    if dest.exists() and zipfile.is_zipfile(dest) and dest.stat().st_size > 0:
        logger.info("Reusing existing zip %s (%s bytes)", dest.name, dest.stat().st_size)
        return
    url = f"{cfg['api']['hub_base_url'].rstrip('/')}/{dataset_id}/rows.csv"
    dest.parent.mkdir(parents=True, exist_ok=True)
    partial = dest.with_suffix(dest.suffix + ".partial")
    if partial.exists():
        partial.unlink()
    logger.info("Downloading dataset %s from %s", dataset_id, url)
    retries = int(cfg["api"].get("retries", 5))
    delay = 2.0
    last_error: Exception | None = None
    for attempt in range(1, retries + 1):
        response = None
        progress = None
        try:
            response = session.get(
                url,
                headers=request_headers(cfg),
                timeout=(30, 180),
                stream=True,
            )
            if response.status_code in {429, 500, 502, 503, 504}:
                raise requests.HTTPError(f"HTTP {response.status_code} from {url}")
            response.raise_for_status()
            total = int(response.headers.get("Content-Length") or 0)
            progress = tqdm(
                total=total or None,
                unit="B",
                unit_scale=True,
                desc=f"dataset {dataset_id}",
            )
            with partial.open("wb") as handle:
                for chunk in response.iter_content(chunk_size=1024 * 1024):
                    if not chunk:
                        continue
                    handle.write(chunk)
                    progress.update(len(chunk))
            if not zipfile.is_zipfile(partial):
                raise RuntimeError(f"Dataset {dataset_id} download was not a zip archive")
            partial.replace(dest)
            logger.info("Saved %s (%s bytes)", dest.name, dest.stat().st_size)
            return
        except (requests.RequestException, OSError, RuntimeError, zipfile.BadZipFile) as exc:
            last_error = exc
            logger.warning("Download attempt %s/%s failed: %s", attempt, retries, exc)
            partial.unlink(missing_ok=True)
            if attempt == retries:
                break
            time.sleep(delay)
            delay = min(delay * 2, 60)
        finally:
            if progress is not None:
                progress.close()
            if response is not None:
                response.close()
    raise RuntimeError(f"Could not download dataset {dataset_id}") from last_error


def csv_members(zip_path: Path) -> list[str]:
    """Return CSV members in archive order. Hub exports split a year across parts."""
    with zipfile.ZipFile(zip_path) as archive:
        members = [
            name
            for name in archive.namelist()
            if name.lower().endswith(".csv") and not name.startswith("__MACOSX")
        ]
    if not members:
        raise RuntimeError(f"No CSV member inside {zip_path}")
    return sorted(members)


def iter_csv_chunks(csv_path: Path, page_size: int):
    """Yield DataFrame chunks from a CSV, keeping blanks as empty strings."""
    reader = pd.read_csv(
        csv_path,
        dtype=str,
        chunksize=page_size,
        keep_default_na=False,
        encoding="utf-8-sig",
    )
    yield from reader


def process_hub_dataset(
    session: requests.Session,
    cfg: dict,
    dataset: dict,
    part_path: Path,
    cache_dir: Path,
) -> int:
    """Download one year, append standardized chunks, and return rows written."""
    logger = common.get_logger("pull_iowa")
    dataset_id = int(dataset["dataset_id"])
    year = int(dataset["year"])
    meta = hub_metadata(session, cfg, dataset_id)
    expected = int(meta.get("numRows") or 0)
    logger.info(
        "Dataset %s (%s) reports %s rows, coverage %s to %s",
        dataset_id,
        year,
        f"{expected:,}",
        str(meta.get("earliestDataCoverageDate", ""))[:10],
        str(meta.get("latestDataCoverageDate", ""))[:10],
    )
    zip_path = cache_dir / f"iowa_liquor_sales_{year}_{dataset_id}.zip"
    download_hub_zip(session, cfg, dataset_id, zip_path)
    members = csv_members(zip_path)
    logger.info("Dataset %s zip contains %s CSV part(s)", dataset_id, len(members))
    if part_path.exists():
        part_path.unlink()
    written = 0
    seen = 0
    dropped_overlap = 0
    seen_ids: set[str] = set()
    write_header = True
    progress = tqdm(total=expected or None, unit="rows", desc=f"{year} rows")
    try:
        with zipfile.ZipFile(zip_path) as archive:
            for name in members:
                extract_path = cache_dir / Path(name).name
                logger.info("Reading %s", name)
                with archive.open(name) as src, extract_path.open("wb") as dst:
                    shutil.copyfileobj(src, dst, length=1024 * 1024)
                try:
                    for raw_chunk in iter_csv_chunks(extract_path, int(cfg["api"]["page_size"])):
                        frame = normalize_frame(raw_chunk, "iowa_data_hub", cfg)
                        seen += len(raw_chunk)
                        progress.update(len(raw_chunk))
                        if frame.empty:
                            continue
                        # Hub zip parts overlap. Invoice id is unique inside the
                        # published dataset, so exact repeat lines are export copies.
                        fresh = [value not in seen_ids for value in frame["invoice_line_no"]]
                        frame = frame.loc[fresh]
                        dropped_overlap += int(len(fresh) - len(frame))
                        if frame.empty:
                            continue
                        seen_ids.update(frame["invoice_line_no"].tolist())
                        append_chunk(part_path, frame, write_header)
                        write_header = False
                        written += len(frame)
                finally:
                    extract_path.unlink(missing_ok=True)
    finally:
        progress.close()
    if expected and not (int(expected * 0.98) <= written <= int(expected * 1.02)):
        raise RuntimeError(
            f"Dataset {dataset_id} kept {written:,} rows, outside 2% of reported {expected:,}"
        )
    logger.info(
        "Year %s read %s rows, dropped %s overlapping export copies, kept %s",
        year,
        f"{seen:,}",
        f"{dropped_overlap:,}",
        f"{written:,}",
    )
    return written


def datasets_for_range(cfg: dict) -> list[dict]:
    """Return hub datasets whose year overlaps the configured date window."""
    start_year = int(str(cfg["date_range"]["start"])[:4])
    end_year = int(str(cfg["date_range"]["end"])[:4])
    selected = []
    for item in cfg["api"]["hub_datasets"]:
        year = int(item["year"])
        if start_year <= year <= end_year:
            selected.append(item)
    return selected


def combine_parts(part_paths: list[Path], dest: Path) -> int:
    """Concatenate year extracts in order into the canonical raw CSV."""
    logger = common.get_logger("pull_iowa")
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        dest.unlink()
    rows = 0
    header_written = False
    with dest.open("w", encoding="utf-8", newline="") as out:
        for part in part_paths:
            with part.open("r", encoding="utf-8", newline="") as src:
                header = src.readline()
                if not header:
                    continue
                if not header_written:
                    out.write(header)
                    header_written = True
                for line in src:
                    out.write(line)
                    rows += 1
    logger.info("Combined %s rows into %s", f"{rows:,}", dest)
    return rows


def load_sqlite(csv_path: Path, db_path: Path, page_size: int) -> int:
    """Replace source_sales with the standardized CSV and add indexes."""
    logger = common.get_logger("pull_iowa")
    conn = common.connect(db_path)
    try:
        conn.execute("PRAGMA synchronous = OFF")
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA temp_store = MEMORY")
        conn.execute("DROP TABLE IF EXISTS source_sales")
        conn.execute(
            """
            CREATE TABLE source_sales (
                invoice_line_no TEXT,
                date TEXT,
                store TEXT,
                name TEXT,
                city TEXT,
                county TEXT,
                category TEXT,
                category_name TEXT,
                vendor_number TEXT,
                vendor_name TEXT,
                itemno TEXT,
                im_desc TEXT,
                pack INTEGER,
                bottle_volume_ml REAL,
                state_bottle_cost REAL,
                state_bottle_retail REAL,
                sale_bottles INTEGER,
                sale_dollars REAL,
                sale_liters REAL
            )
            """
        )
        inserted = 0
        progress = tqdm(unit="rows", desc="SQLite load")
        try:
            for chunk in iter_csv_chunks(csv_path, page_size):
                frame = normalize_frame(chunk, "socrata", {"date_range": {"start": "0001-01-01", "end": "9999-12-31"}, "columns": {"hub_rename": {}}})
                records = frame.astype(object).where(pd.notna(frame), None)
                conn.executemany(
                    """
                    INSERT INTO source_sales (
                        invoice_line_no, date, store, name, city, county, category,
                        category_name, vendor_number, vendor_name, itemno, im_desc,
                        pack, bottle_volume_ml, state_bottle_cost, state_bottle_retail,
                        sale_bottles, sale_dollars, sale_liters
                    ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    """,
                    list(records.itertuples(index=False, name=None)),
                )
                conn.commit()
                inserted += len(frame)
                progress.update(len(frame))
        finally:
            progress.close()
        logger.info("Building indexes on source_sales")
        conn.execute("CREATE INDEX idx_source_sales_invoice ON source_sales (invoice_line_no)")
        conn.execute("CREATE INDEX idx_source_sales_date ON source_sales (date)")
        conn.execute("CREATE INDEX idx_source_sales_store ON source_sales (store)")
        conn.execute("CREATE INDEX idx_source_sales_item ON source_sales (itemno)")
        conn.execute("CREATE INDEX idx_source_sales_category ON source_sales (category)")
        conn.execute("PRAGMA synchronous = NORMAL")
        conn.commit()
        db_rows = int(conn.execute("SELECT COUNT(*) FROM source_sales").fetchone()[0])
        span = conn.execute("SELECT MIN(date), MAX(date) FROM source_sales").fetchone()
        logger.info("SQLite source_sales has %s rows from %s to %s", f"{db_rows:,}", span[0], span[1])
        return db_rows
    finally:
        conn.close()


def update_readme(cfg: dict, row_count: int, fallback: bool, note: str) -> None:
    """Refresh the opening sentence and the pull status block in README.md."""
    readme_path = common.resolve(cfg["paths"]["readme"])
    if fallback:
        opening = (
            f"Real public Iowa Liquor Sales data (2024 only, {row_count:,} rows) "
            "with a simulated distributor feed layer."
        )
    else:
        opening = (
            f"Real public Iowa Liquor Sales data (2023 to 2024, {row_count:,} rows) "
            "with a simulated distributor feed layer."
        )
    status = (
        "<!-- PULL_STATUS_START -->\n"
        f"{note}\n"
        "<!-- PULL_STATUS_END -->"
    )
    if readme_path.exists():
        text = readme_path.read_text(encoding="utf-8")
    else:
        text = (
            "# CPG Trade Data Quality Pipeline\n\n"
            "OPENING\n\n"
            "<!-- PULL_STATUS_START -->\npending\n<!-- PULL_STATUS_END -->\n"
        )
    import re

    text2, n_open = re.subn(
        r"Real public Iowa Liquor Sales data \([^)]*\) with a simulated distributor feed layer\.",
        opening,
        text,
        count=1,
    )
    if n_open == 0:
        text2 = text2.replace("OPENING", opening, 1)
        if "OPENING" in text2 or opening not in text2:
            text2 = text2.replace("# CPG Trade Data Quality Pipeline\n", "# CPG Trade Data Quality Pipeline\n\n" + opening + "\n", 1)
    text2, n_status = re.subn(
        r"<!-- PULL_STATUS_START -->.*?<!-- PULL_STATUS_END -->",
        status,
        text2,
        count=1,
        flags=re.S,
    )
    if n_status == 0:
        text2 = text2.rstrip() + "\n\n" + status + "\n"
    readme_path.write_text(text2, encoding="utf-8")


def pull_via_hub(session: requests.Session, cfg: dict, started: float) -> dict:
    """Download annual hub exports, falling back to 2024 when the budget is too tight."""
    logger = common.get_logger("pull_iowa")
    budget = float(cfg["api"]["max_runtime_minutes"]) * 60
    selected = datasets_for_range(cfg)
    by_year = {int(item["year"]): item for item in selected}
    if 2024 not in by_year and not by_year:
        raise RuntimeError("No Iowa Data Hub dataset overlaps the configured date range")

    raw_dir = common.resolve(cfg["paths"]["raw_dir"])
    cache_dir = raw_dir / "cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    checkpoint_path = common.resolve(cfg["paths"]["checkpoint"])
    checkpoint = read_checkpoint(checkpoint_path)
    parts_dir = raw_dir / "parts"
    parts_dir.mkdir(parents=True, exist_ok=True)

    order = [year for year in (2024, 2023) if year in by_year]
    completed: list[int] = []
    part_rows: dict[int, int] = {}
    fallback = False
    fallback_note = ""

    for index, year in enumerate(order):
        elapsed = time.monotonic() - started
        remaining_years = len(order) - index
        if index > 0 and elapsed * (remaining_years + index) / index > budget:
            fallback = True
            fallback_note = (
                f"The full 2023 to 2024 pull was projected to exceed "
                f"{cfg['api']['max_runtime_minutes']} minutes after the {order[0]} "
                f"extract took {elapsed / 60:.1f} minutes. The pipeline kept 2024 only."
            )
            logger.warning(fallback_note)
            break
        dataset = by_year[year]
        dataset_id = str(dataset["dataset_id"])
        part_path = parts_dir / f"iowa_sales_{year}.csv"
        already = checkpoint.get("parts", {}).get(dataset_id)
        if (
            already
            and part_path.exists()
            and part_path.stat().st_size == int(already.get("bytes", -1))
        ):
            logger.info("Reusing completed year part %s (%s rows)", part_path.name, already["rows"])
            part_rows[year] = int(already["rows"])
            completed.append(year)
            continue
        year_started = time.monotonic()
        rows = process_hub_dataset(session, cfg, dataset, part_path, cache_dir)
        part_rows[year] = rows
        completed.append(year)
        checkpoint.setdefault("parts", {})[dataset_id] = {
            "year": year,
            "rows": rows,
            "bytes": part_path.stat().st_size,
        }
        if dataset_id not in checkpoint["completed_dataset_ids"]:
            checkpoint["completed_dataset_ids"].append(dataset_id)
        checkpoint["source"] = "iowa_data_hub"
        write_checkpoint(checkpoint_path, checkpoint)
        logger.info("Year %s finished in %.1f minutes", year, (time.monotonic() - year_started) / 60)
        if time.monotonic() - started > budget and index < len(order) - 1:
            fallback = True
            fallback_note = (
                f"The full 2023 to 2024 pull exceeded "
                f"{cfg['api']['max_runtime_minutes']} minutes. The pipeline kept the "
                f"completed year extracts: {completed}."
            )
            logger.warning(fallback_note)
            break

    if fallback and 2024 in by_year and 2024 not in completed:
        dataset = by_year[2024]
        part_path = parts_dir / "iowa_sales_2024.csv"
        rows = process_hub_dataset(session, cfg, dataset, part_path, cache_dir)
        part_rows[2024] = rows
        completed = [2024]
        fallback_note = (
            "The full range could not be finished inside the runtime budget. "
            "The pipeline downloaded 2024 only."
        )

    if not completed:
        raise RuntimeError("No annual extracts were produced")

    # Chronological combine. A 2024-only fallback leaves a single part.
    years_in_file = sorted(completed)
    if fallback and years_in_file != [2024] and 2023 not in years_in_file:
        pass
    if 2023 in by_year and 2023 not in completed:
        fallback = True
        if not fallback_note:
            fallback_note = "2023 was not included. The pipeline kept 2024 only."

    raw_csv = common.resolve(cfg["paths"]["raw_csv"])
    part_paths = [parts_dir / f"iowa_sales_{year}.csv" for year in years_in_file]
    row_count = combine_parts(part_paths, raw_csv)
    return {
        "row_count": row_count,
        "years": years_in_file,
        "fallback": fallback or years_in_file == [2024] and 2023 in by_year,
        "fallback_note": fallback_note,
        "part_rows": part_rows,
    }


def apply_run_metadata(cfg: dict, result: dict, status: int, elapsed: float, source: str) -> None:
    """Record the pull outcome on the date window, the pull block, and the README."""
    years = result["years"]
    fallback = bool(result["fallback"])
    cfg["date_range"]["fallback_applied"] = fallback
    cfg["date_range"]["actual_start"] = f"{min(years)}-01-01"
    cfg["date_range"]["actual_end"] = f"{max(years)}-12-31"
    cfg["date_range"]["fallback_note"] = result["fallback_note"] if fallback else ""
    cfg["pull"]["requested_source"] = "socrata"
    cfg["pull"]["source_used"] = source
    cfg["pull"]["socrata_http_status"] = status or None
    cfg["pull"]["row_count"] = int(result["row_count"])
    raw_csv = common.resolve(cfg["paths"]["raw_csv"])
    cfg["pull"]["file_bytes"] = raw_csv.stat().st_size if raw_csv.exists() else 0
    cfg["pull"]["elapsed_seconds"] = round(elapsed, 1)
    cfg["pull"]["datasets_loaded"] = [int(year) for year in years]
    common.save_config(cfg)
    if source == "socrata":
        note = (
            f"Loaded {result['row_count']:,} rows from Socrata resource m3tr-qhgy "
            f"for {cfg['date_range']['actual_start']} to {cfg['date_range']['actual_end']}."
        )
    else:
        note = (
            f"Socrata resource m3tr-qhgy returned HTTP {status}. "
            f"Loaded {result['row_count']:,} rows from Iowa Data Hub annual exports "
            f"for {cfg['date_range']['actual_start']} to {cfg['date_range']['actual_end']} "
            "(datasets 1260 for 2023 and 1261 for 2024, the public successor to m3tr-qhgy). "
            "The annual zip files overlap across CSV parts, so exact duplicate invoice "
            "lines were removed. The kept row count matches the published dataset totals."
        )
        if fallback and result["fallback_note"]:
            note = note + " " + result["fallback_note"]
    update_readme(cfg, int(result["row_count"]), fallback, note)


def main() -> None:
    """Pull Iowa liquor sales, write the raw CSV, and load source_sales."""
    global KEEP_COLUMNS, NUMERIC_COLUMNS, INTEGER_COLUMNS
    load_dotenv(common.ROOT / ".env")
    cfg = common.load_config()
    logger = common.get_logger("pull_iowa")
    KEEP_COLUMNS = list(cfg["columns"]["keep"])
    NUMERIC_COLUMNS = list(cfg["columns"]["numeric"])
    INTEGER_COLUMNS = list(cfg["columns"]["integer"])

    token_var = cfg["api"].get("token_env", "SOCRATA_APP_TOKEN")
    logger.info(
        "App token %s is %s",
        token_var,
        "set" if os.environ.get(token_var, "").strip() else "not set",
    )
    started = time.monotonic()
    raw_csv = common.resolve(cfg["paths"]["raw_csv"])
    raw_csv.parent.mkdir(parents=True, exist_ok=True)
    db_path = common.resolve(cfg["paths"]["database"])
    session = requests.Session()
    status = probe_socrata(session, cfg)
    budget = float(cfg["api"]["max_runtime_minutes"]) * 60
    source = "socrata"

    try:
        if status == 200:
            if raw_csv.exists():
                raw_csv.unlink()
            try:
                written = fetch_socrata_pages(session, cfg, raw_csv, started + budget)
                result = {
                    "row_count": written,
                    "years": [2023, 2024],
                    "fallback": False,
                    "fallback_note": "",
                }
            except TimeoutError as exc:
                logger.warning("%s. Falling back to 2024 only.", exc)
                if raw_csv.exists():
                    raw_csv.unlink()
                original_start = cfg["date_range"]["start"]
                cfg["date_range"]["start"] = "2024-01-01"
                written = fetch_socrata_pages(session, cfg, raw_csv, time.monotonic() + budget)
                cfg["date_range"]["start"] = original_start
                result = {
                    "row_count": written,
                    "years": [2024],
                    "fallback": True,
                    "fallback_note": (
                        "The full 2023 to 2024 Socrata pull exceeded "
                        f"{cfg['api']['max_runtime_minutes']} minutes, so the extract "
                        "was limited to 2024."
                    ),
                }
        else:
            source = "iowa_data_hub"
            logger.warning(
                "Socrata resource is not available (HTTP %s). Using Iowa Data Hub annual exports.",
                status,
            )
            result = pull_via_hub(session, cfg, started)
    finally:
        session.close()

    elapsed = time.monotonic() - started
    db_rows = load_sqlite(raw_csv, db_path, int(cfg["api"]["page_size"]))
    if db_rows != int(result["row_count"]):
        raise RuntimeError(
            f"SQLite row count {db_rows:,} does not match CSV row count {result['row_count']:,}"
        )
    apply_run_metadata(cfg, result, status, elapsed, source)
    size_mb = raw_csv.stat().st_size / (1024 * 1024)
    logger.info("Iowa liquor sales pull summary")
    logger.info("Source used: %s", source)
    logger.info("Socrata HTTP status: %s", status)
    logger.info("Date range loaded: %s-01-01 to %s-12-31", min(result["years"]), max(result["years"]))
    logger.info("Fallback to a shorter window: %s", result["fallback"])
    logger.info("Rows: %s", f"{result['row_count']:,}")
    logger.info("CSV: %s", raw_csv)
    logger.info("File size: %.1f MB (%s bytes)", size_mb, f"{raw_csv.stat().st_size:,}")
    logger.info("SQLite table source_sales: %s rows", f"{db_rows:,}")
    logger.info("Elapsed minutes: %.1f", elapsed / 60)


if __name__ == "__main__":
    main()
