#!/usr/bin/env python3
"""Build flood_dataset_v1 processed tables from raw Seoul flood/rainfall data."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sys
import unicodedata
import warnings
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
from pyproj import CRS, Transformer
from rasterio.transform import xy
from scipy import ndimage
from scipy.spatial import cKDTree
from shapely.geometry import box
from shapely.ops import unary_union

try:
    from tqdm import tqdm
except ImportError:  # pragma: no cover - local env may not have tqdm installed.

    def tqdm(iterable=None, **kwargs):  # type: ignore[no-redef]
        return iterable if iterable is not None else []


WGS84 = "EPSG:4326"
DEFAULT_PROJECTED_CRS = "EPSG:5179"
MAX_EVENT_WINDOW_DAYS = 14
DEM_INVALID_LOW_THRESHOLD = -1000.0
FLOOD_TRACE_GLOB = "flood-traces/**/*.shp"
DEM_GLOB = "dem/**/*.tif"
RAINFALL_DIRS_BY_PRIORITY = (
    "rainfall/seoul_city_2011_2020",
    "rainfall/seoul_city_2021_2024",
    "rainfall/seoul_city_2025_monthly",
    "rainfall",
    "rainfall/seoul_city_2020_monthly",
)
SEOUL_DISTRICTS = (
    "종로구",
    "중구",
    "용산구",
    "성동구",
    "광진구",
    "동대문구",
    "중랑구",
    "성북구",
    "강북구",
    "도봉구",
    "노원구",
    "은평구",
    "서대문구",
    "마포구",
    "양천구",
    "강서구",
    "구로구",
    "금천구",
    "영등포구",
    "동작구",
    "관악구",
    "서초구",
    "강남구",
    "송파구",
    "강동구",
)


@dataclass
class BuildContext:
    raw_dir: Path
    output_dir: Path
    projected_crs: CRS
    warnings: list[str] = field(default_factory=list)
    input_files: set[str] = field(default_factory=set)

    def warn(self, message: str) -> None:
        self.warnings.append(message)
        print(f"WARNING: {message}", file=sys.stderr)

    def add_input(self, path: Path | str | None) -> None:
        if path is not None:
            self.input_files.add(str(path))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build flood_dataset_v1 parquet tables from raw flood, DEM, and rainfall data."
    )
    parser.add_argument("--raw-dir", type=Path, default=Path("data/raw"))
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("data/processed/flood_dataset_v1"),
    )
    parser.add_argument("--idw-k", type=int, default=5)
    parser.add_argument("--idw-power", type=float, default=2.0)
    parser.add_argument("--idw-epsilon", type=float, default=1e-6)
    parser.add_argument("--idw-max-distance-m", type=float, default=None)
    parser.add_argument("--grid-chunk-size", type=int, default=10_000)
    parser.add_argument("--flooded-threshold", type=float, default=0.0)
    parser.add_argument("--alternative-flooded-threshold", type=float, default=0.001)
    parser.add_argument("--save-hourly-rainfall", type=parse_bool, default=False)
    parser.add_argument("--preview-rows", type=int, default=10_000)
    return parser.parse_args()


def parse_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    normalized = str(value).strip().lower()
    if normalized in {"true", "1", "yes", "y"}:
        return True
    if normalized in {"false", "0", "no", "n"}:
        return False
    raise argparse.ArgumentTypeError(f"Expected true/false, got {value!r}")


def normalize_text(value: Any) -> str:
    if pd.isna(value):
        return ""
    return unicodedata.normalize("NFC", str(value)).strip()


def station_id_for_name(station_name: str) -> str:
    normalized = normalize_text(station_name)
    digest = hashlib.sha1(normalized.encode("utf-8")).hexdigest()[:10]
    return f"STN_{digest}"


def read_csv_with_fallback(path: Path, **kwargs: Any) -> pd.DataFrame:
    errors: list[str] = []
    for encoding in ("utf-8-sig", "cp949", "euc-kr"):
        try:
            return pd.read_csv(path, encoding=encoding, **kwargs)
        except UnicodeDecodeError as exc:
            errors.append(f"{encoding}: {exc}")
    raise UnicodeDecodeError("csv", b"", 0, 1, f"Could not decode {path}: {errors}")


def write_parquet(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(path, index=False)


def find_dem_path(ctx: BuildContext) -> Path:
    candidates = sorted(ctx.raw_dir.glob(DEM_GLOB))
    if not candidates:
        raise FileNotFoundError(f"No DEM raster found under {ctx.raw_dir / 'dem'}")
    ctx.add_input(candidates[0])
    if len(candidates) > 1:
        ctx.warn(f"Multiple DEM rasters found; using {candidates[0]}")
    return candidates[0]


def discover_flood_trace_files(ctx: BuildContext) -> list[Path]:
    flood_files = sorted(ctx.raw_dir.glob(FLOOD_TRACE_GLOB))
    if not flood_files:
        ctx.warn("No flood trace shapefiles found.")
    for path in flood_files:
        ctx.add_input(path)
    return flood_files


def extract_year_from_path(path: Path) -> int | None:
    candidates = re.findall(r"(20\d{2}|19\d{2})", str(path))
    return int(candidates[-1]) if candidates else None


def parse_event_time(date_value: Any, hour_value: Any, default_hour: int) -> pd.Timestamp | None:
    date_text = normalize_text(date_value)
    if not date_text:
        return None
    match = re.search(r"(20\d{2})(\d{2})(\d{2})", date_text)
    if not match:
        return None
    year, month, day = map(int, match.groups())
    hour_text = normalize_text(hour_value)
    hour_match = re.search(r"\d+", hour_text) if hour_text else None
    hour = int(hour_match.group(0)) if hour_match else default_hour
    base = pd.Timestamp(year=year, month=month, day=day)
    if hour >= 24:
        return base + pd.Timedelta(days=1)
    return base + pd.Timedelta(hours=hour)


def parse_2025_damage_time(value: Any) -> pd.Timestamp | None:
    text = normalize_text(value)
    match = re.search(r"(20\d{2})(\d{2})(\d{2})", text)
    if not match:
        return None
    year, month, day = map(int, match.groups())
    return pd.Timestamp(year=year, month=month, day=day)


def filter_flood_gdf_for_event(
    gdf: gpd.GeoDataFrame, flood_trace_year: int, ctx: BuildContext, source: Path
) -> gpd.GeoDataFrame:
    """Keep rows that belong to the annual event represented by the source file."""
    original_count = len(gdf)
    year_text = str(flood_trace_year)
    for year_col in ("F_YR", "INV_YR"):
        if year_col not in gdf.columns:
            continue
        year_values = gdf[year_col].map(normalize_text).str.extract(r"((?:19|20)\d{2})", expand=False)
        mask = year_values.eq(year_text)
        if mask.any():
            filtered = gdf[mask].copy()
            if len(filtered) != original_count:
                ctx.warn(
                    f"{source}: filtered flood rows by {year_col}={flood_trace_year} "
                    f"({len(filtered)}/{original_count} rows)."
                )
            return filtered
    return gdf.copy()


def timestamp_matches_event_year(ts: pd.Timestamp | None, flood_trace_year: int) -> bool:
    return ts is not None and int(ts.year) == int(flood_trace_year)


def build_event_meta(ctx: BuildContext, flood_files: list[Path]) -> pd.DataFrame:
    records: list[dict[str, Any]] = []
    for flood_file in tqdm(flood_files, desc="event_meta"):
        flood_trace_year = extract_year_from_path(flood_file)
        if flood_trace_year is None:
            ctx.warn(f"Could not infer flood trace year from {flood_file}; skipping event.")
            continue

        needs_manual_review = False
        event_source_note = ""
        try:
            gdf = gpd.read_file(flood_file)
        except Exception as exc:
            ctx.warn(f"Failed to read flood trace file {flood_file}: {exc}")
            continue

        if gdf.empty:
            ctx.warn(f"Flood trace file is empty: {flood_file}")
            needs_manual_review = True
        else:
            gdf = filter_flood_gdf_for_event(gdf, flood_trace_year, ctx, flood_file)

        starts: list[pd.Timestamp] = []
        ends: list[pd.Timestamp] = []
        row_windows: list[tuple[pd.Timestamp, pd.Timestamp]] = []
        if {"F_SAT_YMD", "F_END_YMD"}.issubset(gdf.columns):
            for _, row in gdf.iterrows():
                start = parse_event_time(row.get("F_SAT_YMD"), row.get("F_SAT_TM"), 0)
                end = parse_event_time(row.get("F_END_YMD"), row.get("F_END_TM"), 23)
                if start is not None and not timestamp_matches_event_year(start, flood_trace_year):
                    needs_manual_review = True
                    continue
                if end is not None and not timestamp_matches_event_year(end, flood_trace_year):
                    needs_manual_review = True
                    end = None
                if start is not None:
                    starts.append(start)
                if end is not None:
                    ends.append(end)
                elif start is not None:
                    end = start + pd.Timedelta(days=1)
                    ends.append(end)
                    needs_manual_review = True
                if start is not None and end is not None:
                    row_windows.append((start, end))
        elif "피해일시" in gdf.columns:
            starts = [ts for ts in gdf["피해일시"].map(parse_2025_damage_time) if ts is not None]
            ends = [ts + pd.Timedelta(days=1) for ts in starts]
            needs_manual_review = True

        if starts and ends:
            rain_start_time = min(starts).floor("h")
            rain_end_time = max(ends).ceil("h")
            if rain_end_time <= rain_start_time:
                rain_end_time = rain_start_time + pd.Timedelta(days=1)
                needs_manual_review = True
            duration_days = (rain_end_time - rain_start_time).total_seconds() / 86400
            if duration_days > MAX_EVENT_WINDOW_DAYS and row_windows:
                start_dates = pd.Series([start.date().isoformat() for start, _ in row_windows])
                representative_date = start_dates.mode().iloc[0]
                representative_windows = [
                    (start, end)
                    for start, end in row_windows
                    if start.date().isoformat() == representative_date
                ]
                rain_start_time = min(start for start, _ in representative_windows).floor("h")
                rain_end_time = max(end for _, end in representative_windows).ceil("h")
                if rain_end_time <= rain_start_time:
                    rain_end_time = rain_start_time + pd.Timedelta(days=1)
                needs_manual_review = True
                event_source_note = (
                    f"Original annual date span was {duration_days:.1f} days; "
                    f"used modal flood start date {representative_date} as representative window."
                )
            duration_days = (rain_end_time - rain_start_time).total_seconds() / 86400
            if duration_days > MAX_EVENT_WINDOW_DAYS:
                original_end = rain_end_time
                rain_end_time = rain_start_time + pd.Timedelta(days=MAX_EVENT_WINDOW_DAYS)
                needs_manual_review = True
                suffix = (
                    f" Capped rain_end_time from {original_end} to {rain_end_time} "
                    f"using MAX_EVENT_WINDOW_DAYS={MAX_EVENT_WINDOW_DAYS}."
                )
                event_source_note = f"{event_source_note}{suffix}".strip()
            if rain_start_time.year != flood_trace_year:
                needs_manual_review = True
                mismatch_note = (
                    f"rain_start_year={rain_start_time.year} differs from "
                    f"flood_trace_year={flood_trace_year}"
                )
                event_source_note = f"{event_source_note} {mismatch_note}".strip()
        else:
            rain_start_time = pd.Timestamp(year=flood_trace_year, month=7, day=1)
            rain_end_time = pd.Timestamp(year=flood_trace_year, month=9, day=30, hour=23)
            needs_manual_review = True
            event_source_note = "No reliable rain period in flood trace attributes; used Jul-Sep default."

        event_id = f"EVT_{flood_trace_year}_FLOOD"
        descriptions = []
        if "F_DISA_NM" in gdf.columns:
            descriptions = [normalize_text(x) for x in gdf["F_DISA_NM"].dropna().unique()[:5]]
        description = "; ".join([x for x in descriptions if x]) or f"{flood_trace_year} flood trace event"

        records.append(
            {
                "event_id": event_id,
                "event_year": flood_trace_year,
                "rain_start_time": rain_start_time,
                "rain_end_time": rain_end_time,
                "flood_trace_file": str(flood_file),
                "source": "data/raw/flood-traces",
                "description": description,
                "needs_manual_review": bool(needs_manual_review),
                "flood_trace_year": flood_trace_year,
                "event_source_note": event_source_note,
            }
        )

    event_meta = pd.DataFrame(records).sort_values("event_id").reset_index(drop=True)
    return event_meta


def build_grid_static(ctx: BuildContext, dem_path: Path) -> tuple[pd.DataFrame, gpd.GeoDataFrame]:
    with rasterio.open(dem_path) as src:
        arr = src.read(1).astype("float64")
        transform = src.transform
        nodata = src.nodata
        projected_crs = src.crs or CRS.from_user_input(DEFAULT_PROJECTED_CRS)
        ctx.projected_crs = CRS.from_user_input(projected_crs)
        if nodata is not None:
            arr[arr == nodata] = np.nan
        invalid_low = np.isfinite(arr) & (arr <= DEM_INVALID_LOW_THRESHOLD)
        if invalid_low.any():
            ctx.warn(
                f"{dem_path}: treated {int(invalid_low.sum())} DEM cells <= "
                f"{DEM_INVALID_LOW_THRESHOLD:g} as nodata."
            )
            arr[invalid_low] = np.nan
        valid = np.isfinite(arr)
        pixel_width = abs(transform.a)
        pixel_height = abs(transform.e)

        rows, cols = np.where(valid)
        xs, ys = xy(transform, rows, cols, offset="center")
        xs_arr = np.asarray(xs, dtype="float64")
        ys_arr = np.asarray(ys, dtype="float64")
        transformer = Transformer.from_crs(ctx.projected_crs, WGS84, always_xy=True)
        lons, lats = transformer.transform(xs_arr, ys_arr)

    filled = arr.copy()
    median_elev = np.nanmedian(filled)
    filled[~np.isfinite(filled)] = median_elev
    dz_dy, dz_dx = np.gradient(filled, pixel_height, pixel_width)
    slope = np.degrees(np.arctan(np.sqrt(dz_dx**2 + dz_dy**2)))
    aspect = (np.degrees(np.arctan2(dz_dy, -dz_dx)) + 360.0) % 360.0
    aspect_rad = np.radians(aspect)
    local_mean = ndimage.uniform_filter(filled, size=11, mode="nearest")
    relative_elev = filled - local_mean
    curvature = np.gradient(dz_dx, pixel_width, axis=1) + np.gradient(dz_dy, pixel_height, axis=0)

    grid_ids = np.array([f"GRID_{r:04d}_{c:04d}" for r, c in zip(rows, cols)])
    grid_static = pd.DataFrame(
        {
            "grid_id": grid_ids,
            "centroid_lat": np.asarray(lats, dtype="float64"),
            "centroid_lon": np.asarray(lons, dtype="float64"),
            "x_coord": xs_arr,
            "y_coord": ys_arr,
            "elevation": arr[rows, cols],
            "slope": slope[rows, cols],
            "relative_elev": relative_elev[rows, cols],
            "curvature": curvature[rows, cols],
            "aspect": aspect[rows, cols],
            "aspect_sin": np.sin(aspect_rad[rows, cols]),
            "aspect_cos": np.cos(aspect_rad[rows, cols]),
            "flow_accumulation": np.nan,
            "dem_row": rows.astype("int32"),
            "dem_col": cols.astype("int32"),
            "grid_size_m": float(max(pixel_width, pixel_height)),
        }
    )

    half_w = pixel_width / 2
    half_h = pixel_height / 2
    geometries = [box(x - half_w, y - half_h, x + half_w, y + half_h) for x, y in zip(xs_arr, ys_arr)]
    grid_gdf = gpd.GeoDataFrame(
        grid_static[["grid_id", "x_coord", "y_coord", "grid_size_m"]].copy(),
        geometry=geometries,
        crs=ctx.projected_crs,
    )
    grid_gdf["grid_area"] = grid_gdf.geometry.area
    return grid_static, grid_gdf


def clean_geometries(gdf: gpd.GeoDataFrame, ctx: BuildContext, source: Path) -> gpd.GeoDataFrame:
    if gdf.empty:
        return gdf
    gdf = gdf[gdf.geometry.notna()].copy()
    if gdf.empty:
        return gdf
    invalid_before = int((~gdf.geometry.is_valid).sum())
    if invalid_before:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            gdf.loc[~gdf.geometry.is_valid, "geometry"] = gdf.loc[~gdf.geometry.is_valid, "geometry"].buffer(0)
        invalid_after = int((~gdf.geometry.is_valid).sum())
        if invalid_after:
            ctx.warn(
                f"{source}: dropped {invalid_after} unrecoverable invalid geometries "
                f"after buffer(0)."
            )
            gdf = gdf[gdf.geometry.is_valid].copy()
        ctx.warn(f"{source}: repaired {invalid_before - invalid_after} invalid geometries with buffer(0).")
    return gdf[~gdf.geometry.is_empty].copy()


def district_centroids_from_flood_traces(
    ctx: BuildContext, flood_files: list[Path]
) -> dict[str, tuple[float, float]]:
    parts: list[gpd.GeoDataFrame] = []
    for path in flood_files:
        try:
            gdf = gpd.read_file(path)
        except Exception:
            continue
        if "GU_NAM" not in gdf.columns or gdf.empty:
            continue
        if gdf.crs is None:
            gdf = gdf.set_crs(ctx.projected_crs)
        gdf = gdf.to_crs(ctx.projected_crs)
        gdf = clean_geometries(gdf[["GU_NAM", "geometry"]], ctx, path)
        if not gdf.empty:
            parts.append(gdf)

    if not parts:
        return {}
    all_gdf = pd.concat(parts, ignore_index=True)
    centroids: dict[str, tuple[float, float]] = {}
    for gu_name, group in all_gdf.groupby("GU_NAM"):
        gu_name = normalize_text(gu_name)
        if not gu_name:
            continue
        union_geom = unary_union(list(group.geometry))
        centroid = union_geom.centroid
        centroids[gu_name] = (float(centroid.x), float(centroid.y))
    return centroids


def infer_station_gu(station_name: str, guide_mapping: dict[str, str]) -> str | None:
    normalized = normalize_text(station_name)
    if normalized in guide_mapping:
        return guide_mapping[normalized]
    for district in SEOUL_DISTRICTS:
        if district in normalized:
            return district
    return None


def read_station_guide(ctx: BuildContext) -> dict[str, str]:
    guide_files = sorted((ctx.raw_dir / "rainfall").glob("**/0_*.csv"))
    mapping: dict[str, str] = {}
    for path in guide_files:
        ctx.add_input(path)
        try:
            df = read_csv_with_fallback(path)
        except Exception as exc:
            ctx.warn(f"Failed to read station guide {path}: {exc}")
            continue
        if {"강우량계명", "구청명"}.issubset(df.columns):
            for _, row in df.iterrows():
                station_name = normalize_text(row["강우량계명"])
                gu_name = normalize_text(row["구청명"])
                if station_name and gu_name:
                    mapping[station_name] = gu_name
    return mapping


def discover_station_location_file(ctx: BuildContext) -> Path | None:
    candidates = sorted(ctx.raw_dir.glob("**/*.csv")) + sorted(ctx.raw_dir.glob("**/*.xlsx"))
    for path in candidates:
        name = normalize_text(path.name).lower()
        if not any(token in name for token in ("station", "관측", "강우량계", "위치", "좌표")):
            continue
        try:
            if path.suffix.lower() == ".xlsx":
                df = pd.read_excel(path, nrows=5)
            else:
                df = read_csv_with_fallback(path, nrows=5)
        except Exception:
            continue
        normalized_columns = {normalize_text(col).lower() for col in df.columns}
        has_lat = bool(normalized_columns & {"lat", "latitude", "위도"})
        has_lon = bool(normalized_columns & {"lon", "lng", "longitude", "경도"})
        if has_lat and has_lon:
            return path
    return None


def read_explicit_station_locations(ctx: BuildContext, path: Path) -> pd.DataFrame:
    ctx.add_input(path)
    if path.suffix.lower() == ".xlsx":
        df = pd.read_excel(path)
    else:
        df = read_csv_with_fallback(path)
    rename: dict[str, str] = {}
    for col in df.columns:
        key = normalize_text(col).lower()
        if key in {"강우량계명", "station_name", "name", "관측소명"}:
            rename[col] = "station_name"
        elif key in {"위도", "lat", "latitude"}:
            rename[col] = "latitude"
        elif key in {"경도", "lon", "lng", "longitude"}:
            rename[col] = "longitude"
        elif key in {"표고", "고도", "elevation"}:
            rename[col] = "elevation"
    df = df.rename(columns=rename)
    required = {"station_name", "latitude", "longitude"}
    if not required.issubset(df.columns):
        ctx.warn(f"Station location file lacks required columns after normalization: {path}")
        return pd.DataFrame()
    out = df[list(required | ({"elevation"} if "elevation" in df.columns else set()))].copy()
    out["station_name"] = out["station_name"].map(normalize_text)
    out["station_id"] = out["station_name"].map(station_id_for_name)
    out["latitude"] = pd.to_numeric(out["latitude"], errors="coerce")
    out["longitude"] = pd.to_numeric(out["longitude"], errors="coerce")
    if "elevation" in out.columns:
        out["elevation"] = pd.to_numeric(out["elevation"], errors="coerce")
    else:
        out["elevation"] = np.nan
    return out.dropna(subset=["latitude", "longitude"]).drop_duplicates("station_id")


def discover_rainfall_files(
    ctx: BuildContext, required_years: set[int]
) -> tuple[list[Path], dict[int, int]]:
    selected: list[Path] = []
    selected_paths: set[Path] = set()
    coverage: dict[int, int] = {year: 0 for year in required_years}
    covered_by_primary: set[int] = set()

    for rel_dir in RAINFALL_DIRS_BY_PRIORITY:
        directory = ctx.raw_dir / rel_dir
        if not directory.exists():
            continue
        files = sorted(path for path in directory.glob("*.csv") if not path.name.startswith("0_"))
        for path in files:
            year = extract_year_from_path(path)
            if year not in required_years:
                continue
            if rel_dir.endswith("seoul_city_2020_monthly") and year in covered_by_primary:
                continue
            if path in selected_paths:
                continue
            selected.append(path)
            selected_paths.add(path)
            coverage[year] = coverage.get(year, 0) + 1
        if not rel_dir.endswith("seoul_city_2020_monthly"):
            for path in files:
                year = extract_year_from_path(path)
                if year in required_years:
                    covered_by_primary.add(year)

    for path in selected:
        ctx.add_input(path)
    missing_years = [year for year, count in sorted(coverage.items()) if count == 0]
    if missing_years:
        ctx.warn(f"No rainfall CSV files found for years: {missing_years}")
    return selected, coverage


def station_names_from_rainfall_files(files: list[Path]) -> set[str]:
    names: set[str] = set()
    for path in files:
        if "seoul_city_2020_monthly" in str(path) or "강우량_정보" in path.name:
            continue
        stem = normalize_text(path.stem)
        station_name = re.sub(r"(19|20)\d{2}년?$", "", stem).strip()
        if station_name:
            names.add(station_name)
    return names


def sample_dem_elevation(dem_path: Path, xs: np.ndarray, ys: np.ndarray, ctx: BuildContext) -> np.ndarray:
    values = np.full(len(xs), np.nan, dtype="float64")
    with rasterio.open(dem_path) as src:
        for idx, value in enumerate(src.sample(zip(xs, ys))):
            val = float(value[0])
            if src.nodata is not None and val == src.nodata:
                val = np.nan
            elif val <= DEM_INVALID_LOW_THRESHOLD:
                val = np.nan
            values[idx] = val
    return values


def build_station_meta(
    ctx: BuildContext,
    rainfall_files: list[Path],
    flood_files: list[Path],
    dem_path: Path,
    grid_static: pd.DataFrame,
) -> tuple[pd.DataFrame, dict[str, str]]:
    guide_mapping = read_station_guide(ctx)
    station_names = station_names_from_rainfall_files(rainfall_files)
    station_names.update(guide_mapping.keys())

    explicit_station_file = discover_station_location_file(ctx)
    explicit_locations = pd.DataFrame()
    if explicit_station_file is not None:
        explicit_locations = read_explicit_station_locations(ctx, explicit_station_file)

    station_ids = {name: station_id_for_name(name) for name in sorted(station_names)}
    district_centroids = district_centroids_from_flood_traces(ctx, flood_files)
    fallback_x = float(grid_static["x_coord"].mean())
    fallback_y = float(grid_static["y_coord"].mean())

    explicit_by_id: dict[str, dict[str, Any]] = {}
    if not explicit_locations.empty:
        for record in explicit_locations.to_dict("records"):
            explicit_by_id[record["station_id"]] = record

    transformer_to_projected = Transformer.from_crs(WGS84, ctx.projected_crs, always_xy=True)
    transformer_to_wgs84 = Transformer.from_crs(ctx.projected_crs, WGS84, always_xy=True)

    records: list[dict[str, Any]] = []
    approximate_count = 0
    fallback_count = 0
    for station_name in sorted(station_names):
        station_id = station_ids[station_name]
        gu_name = infer_station_gu(station_name, guide_mapping)
        provider = "Seoul Open Data Plaza"
        station_type = "rain_gauge"
        active_start = None
        active_end = None

        if station_id in explicit_by_id:
            loc = explicit_by_id[station_id]
            lon = float(loc["longitude"])
            lat = float(loc["latitude"])
            x_coord, y_coord = transformer_to_projected.transform(lon, lat)
            elevation = loc.get("elevation", np.nan)
        elif gu_name in district_centroids:
            x_coord, y_coord = district_centroids[gu_name]
            lon, lat = transformer_to_wgs84.transform(x_coord, y_coord)
            elevation = np.nan
            approximate_count += 1
        else:
            x_coord, y_coord = fallback_x, fallback_y
            lon, lat = transformer_to_wgs84.transform(x_coord, y_coord)
            elevation = np.nan
            fallback_count += 1

        records.append(
            {
                "station_id": station_id,
                "station_name": station_name,
                "latitude": lat,
                "longitude": lon,
                "x_coord": x_coord,
                "y_coord": y_coord,
                "elevation": elevation,
                "provider": provider,
                "active_start_date": active_start,
                "active_end_date": active_end,
                "station_type": station_type,
                "district": gu_name,
                "location_source": "explicit" if station_id in explicit_by_id else "district_flood_trace_centroid",
            }
        )

    station_meta = pd.DataFrame(records)
    if not station_meta.empty:
        missing_elev = station_meta["elevation"].isna()
        if missing_elev.any():
            sampled = sample_dem_elevation(
                dem_path,
                station_meta.loc[missing_elev, "x_coord"].to_numpy(),
                station_meta.loc[missing_elev, "y_coord"].to_numpy(),
                ctx,
            )
            station_meta.loc[missing_elev, "elevation"] = sampled

    if approximate_count:
        ctx.warn(
            f"Station coordinate file not found for {approximate_count} stations; "
            "used district centroids derived from flood traces. IDW distances are approximate."
        )
    if fallback_count:
        ctx.warn(
            f"Could not infer district for {fallback_count} stations; used DEM extent centroid as fallback."
        )

    return station_meta, station_ids


def normalize_rainfall_columns(df: pd.DataFrame) -> pd.DataFrame:
    rename: dict[str, str] = {}
    for col in df.columns:
        key = normalize_text(col)
        if key in {"강우량계명", "관측소명", "station_name"}:
            rename[col] = "station_name"
        elif key in {"시간", "자료수집 시각", "observed_time"}:
            rename[col] = "observed_time"
        elif key in {"10분우량", "10분강우량", "rainfall_mm"}:
            rename[col] = "rainfall_10min_mm"
    return df.rename(columns=rename)


def raw_file_station_name(path: Path) -> str:
    stem = normalize_text(path.stem)
    return re.sub(r"(19|20)\d{2}년?$", "", stem).strip()


def build_station_rainfall_raw(
    ctx: BuildContext,
    rainfall_files: list[Path],
    station_meta: pd.DataFrame,
    station_ids: dict[str, str],
) -> pd.DataFrame:
    station_meta_ids = set(station_meta["station_id"]) if not station_meta.empty else set()
    hourly_parts: list[pd.DataFrame] = []
    for path in tqdm(rainfall_files, desc="station_rainfall_raw"):
        try:
            df = read_csv_with_fallback(path)
        except Exception as exc:
            ctx.warn(f"Failed to read rainfall CSV {path}: {exc}")
            continue

        df = normalize_rainfall_columns(df)
        required = {"station_name", "observed_time", "rainfall_10min_mm"}
        if not required.issubset(df.columns):
            ctx.warn(f"Rainfall CSV lacks required columns {required}: {path}")
            continue
        df = df[["station_name", "observed_time", "rainfall_10min_mm"]].copy()
        df["station_name"] = df["station_name"].map(normalize_text)
        file_station_name = raw_file_station_name(path)
        df.loc[df["station_name"].eq(""), "station_name"] = file_station_name
        df["station_id"] = df["station_name"].map(station_id_for_name)
        df["observed_time"] = pd.to_datetime(df["observed_time"], errors="coerce")
        df["rainfall_10min_mm"] = pd.to_numeric(df["rainfall_10min_mm"], errors="coerce")

        missing_time = df["observed_time"].isna()
        missing_rain = df["rainfall_10min_mm"].isna()
        negative = df["rainfall_10min_mm"] < 0
        extreme_10min = df["rainfall_10min_mm"] > 100
        invalid = missing_time | missing_rain | negative | extreme_10min
        df.loc[negative | extreme_10min, "rainfall_10min_mm"] = np.nan
        df = df[~missing_time].copy()
        if df.empty:
            continue
        df["observed_time"] = df["observed_time"].dt.floor("h")
        df["raw_invalid_count"] = invalid[~missing_time].astype("int8").to_numpy()

        grouped = (
            df.groupby(["station_id", "station_name", "observed_time"], as_index=False)
            .agg(
                rainfall_mm=("rainfall_10min_mm", "sum"),
                raw_invalid_count=("raw_invalid_count", "sum"),
            )
        )
        grouped["raw_file"] = str(path)
        grouped["source"] = "10min_rainfall_csv_hourly_sum"
        grouped["provider"] = "Seoul Open Data Plaza"
        grouped["quality_flag"] = "ok"
        grouped.loc[grouped["raw_invalid_count"] > 0, "quality_flag"] = "raw_invalid_values"
        grouped.loc[grouped["rainfall_mm"] < 0, "quality_flag"] = "negative_hourly"
        grouped.loc[grouped["rainfall_mm"] > 300, "quality_flag"] = "extreme_hourly"
        hourly_parts.append(
            grouped[
                [
                    "station_id",
                    "station_name",
                    "observed_time",
                    "rainfall_mm",
                    "source",
                    "quality_flag",
                    "raw_file",
                    "provider",
                ]
            ]
        )

    if not hourly_parts:
        return pd.DataFrame(
            columns=[
                "station_id",
                "station_name",
                "observed_time",
                "rainfall_mm",
                "source",
                "quality_flag",
                "raw_file",
                "provider",
            ]
        )
    rainfall = pd.concat(hourly_parts, ignore_index=True)
    rainfall["rainfall_mm"] = pd.to_numeric(rainfall["rainfall_mm"], errors="coerce")
    rainfall = rainfall.sort_values(["station_id", "observed_time"]).reset_index(drop=True)
    return rainfall


def augment_station_meta_from_rainfall_raw(
    ctx: BuildContext,
    station_meta: pd.DataFrame,
    station_rainfall_raw: pd.DataFrame,
    flood_files: list[Path],
    dem_path: Path,
    grid_static: pd.DataFrame,
) -> pd.DataFrame:
    if station_rainfall_raw.empty or "station_name" not in station_rainfall_raw.columns:
        return station_meta
    existing_ids = set(station_meta["station_id"]) if not station_meta.empty else set()
    raw_stations = station_rainfall_raw[["station_id", "station_name"]].drop_duplicates()
    missing = raw_stations[~raw_stations["station_id"].isin(existing_ids)].copy()
    if missing.empty:
        return station_meta

    guide_mapping = read_station_guide(ctx)
    district_centroids = district_centroids_from_flood_traces(ctx, flood_files)
    fallback_x = float(grid_static["x_coord"].mean())
    fallback_y = float(grid_static["y_coord"].mean())
    transformer_to_wgs84 = Transformer.from_crs(ctx.projected_crs, WGS84, always_xy=True)

    records: list[dict[str, Any]] = []
    fallback_count = 0
    district_count = 0
    for _, row in missing.iterrows():
        station_id = row["station_id"]
        station_name = normalize_text(row["station_name"])
        gu_name = infer_station_gu(station_name, guide_mapping)
        if gu_name in district_centroids:
            x_coord, y_coord = district_centroids[gu_name]
            location_source = "district_flood_trace_centroid_from_raw_station"
            district_count += 1
        else:
            x_coord, y_coord = fallback_x, fallback_y
            location_source = "dem_extent_centroid_from_raw_station"
            fallback_count += 1
        lon, lat = transformer_to_wgs84.transform(x_coord, y_coord)
        records.append(
            {
                "station_id": station_id,
                "station_name": station_name,
                "latitude": lat,
                "longitude": lon,
                "x_coord": x_coord,
                "y_coord": y_coord,
                "elevation": np.nan,
                "provider": "Seoul Open Data Plaza",
                "active_start_date": None,
                "active_end_date": None,
                "station_type": "rain_gauge",
                "district": gu_name,
                "location_source": location_source,
            }
        )

    added = pd.DataFrame(records)
    if not added.empty:
        sampled = sample_dem_elevation(
            dem_path,
            added["x_coord"].to_numpy(dtype="float64"),
            added["y_coord"].to_numpy(dtype="float64"),
            ctx,
        )
        added["elevation"] = sampled
        station_meta = pd.concat([station_meta, added], ignore_index=True)
        ctx.warn(
            f"Added {len(added)} station_meta rows found only inside rainfall raw CSVs "
            f"({district_count} district centroid, {fallback_count} DEM centroid)."
        )
    return station_meta.drop_duplicates("station_id").sort_values("station_name").reset_index(drop=True)


def required_rainfall_years(event_meta: pd.DataFrame) -> set[int]:
    years: set[int] = set()
    for _, row in event_meta.iterrows():
        years.add(int(row["event_year"]))
        start = pd.Timestamp(row["rain_start_time"])
        end = pd.Timestamp(row["rain_end_time"])
        for year in range(start.year, end.year + 1):
            years.add(year)
    return years


def compute_idw_neighbors(
    grid_static: pd.DataFrame,
    station_subset: pd.DataFrame,
    idw_k: int,
    idw_power: float,
    idw_epsilon: float,
    max_distance_m: float | None,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    grid_xy = grid_static[["x_coord", "y_coord"]].to_numpy(dtype="float64")
    station_xy = station_subset[["x_coord", "y_coord"]].to_numpy(dtype="float64")
    k = min(idw_k, len(station_subset))
    tree = cKDTree(station_xy)
    distances, indices = tree.query(grid_xy, k=k)
    if k == 1:
        distances = distances[:, None]
        indices = indices[:, None]
    valid = np.isfinite(distances)
    if max_distance_m is not None:
        valid &= distances <= max_distance_m
    safe_distances = np.maximum(distances, idw_epsilon)
    weights = np.where(valid, 1.0 / np.power(safe_distances, idw_power), 0.0)
    station_counts = valid.sum(axis=1).astype("int16")
    avg_distances = np.divide(
        np.where(valid, distances, 0.0).sum(axis=1),
        station_counts,
        out=np.full(len(grid_static), np.nan, dtype="float64"),
        where=station_counts > 0,
    )
    return indices.astype("int32"), weights.astype("float64"), station_counts, avg_distances


def aggregate_hourly_matrix(
    hourly_matrix: np.ndarray, windows: tuple[int, ...] = (1, 3, 6, 24)
) -> dict[int, np.ndarray]:
    df = pd.DataFrame(hourly_matrix)
    out: dict[int, np.ndarray] = {}
    for window in windows:
        min_periods = 1 if window == 1 else window
        out[window] = df.rolling(window=window, min_periods=min_periods).sum().max(axis=0).to_numpy()
    return out


def interpolate_event_rainfall(
    event_id: str,
    event_rain: pd.DataFrame,
    station_meta: pd.DataFrame,
    grid_static: pd.DataFrame,
    args: argparse.Namespace,
    ctx: BuildContext,
) -> tuple[pd.DataFrame, pd.DataFrame | None]:
    feature_columns = [
        "grid_id",
        "event_id",
        "rainfall_1h_max",
        "rainfall_3h_max",
        "rainfall_6h_max",
        "rainfall_24h_total",
        "rainfall_total",
        "rainfall_duration_hours",
        "rainfall_avg_intensity",
        "idw_station_count",
        "idw_avg_distance_m",
    ]
    if event_rain.empty:
        ctx.warn(f"{event_id}: no rainfall observations in event window.")
        out = grid_static[["grid_id"]].copy()
        out["event_id"] = event_id
        for col in feature_columns:
            if col not in {"grid_id", "event_id"}:
                out[col] = np.nan
        return out[feature_columns], None

    valid_rain = event_rain[event_rain["quality_flag"].isin(["ok", "raw_invalid_values"])].copy()
    valid_rain = valid_rain.dropna(subset=["rainfall_mm"])
    station_ids = sorted(set(valid_rain["station_id"]) & set(station_meta["station_id"]))
    if not station_ids:
        ctx.warn(f"{event_id}: no rainfall stations with usable metadata.")
        out = grid_static[["grid_id"]].copy()
        out["event_id"] = event_id
        for col in feature_columns:
            if col not in {"grid_id", "event_id"}:
                out[col] = np.nan
        return out[feature_columns], None

    station_subset = (
        station_meta[station_meta["station_id"].isin(station_ids)]
        .drop_duplicates("station_id")
        .sort_values("station_id")
        .reset_index(drop=True)
    )
    pivot = (
        valid_rain[valid_rain["station_id"].isin(station_ids)]
        .pivot_table(
            index="observed_time",
            columns="station_id",
            values="rainfall_mm",
            aggfunc="sum",
        )
        .sort_index()
    )
    station_subset = station_subset[station_subset["station_id"].isin(pivot.columns)].reset_index(drop=True)
    pivot = pivot.reindex(columns=station_subset["station_id"].tolist())
    rain_values = pivot.to_numpy(dtype="float64")

    neighbor_idx, weights, station_counts, avg_distances = compute_idw_neighbors(
        grid_static=grid_static,
        station_subset=station_subset,
        idw_k=args.idw_k,
        idw_power=args.idw_power,
        idw_epsilon=args.idw_epsilon,
        max_distance_m=args.idw_max_distance_m,
    )

    rows: list[pd.DataFrame] = []
    hourly_parts: list[pd.DataFrame] = []
    grid_ids = grid_static["grid_id"].to_numpy()
    n_grids = len(grid_static)

    for start in tqdm(range(0, n_grids, args.grid_chunk_size), desc=f"idw {event_id}"):
        end = min(start + args.grid_chunk_size, n_grids)
        idx = neighbor_idx[start:end]
        w = weights[start:end]
        selected = rain_values[:, idx]
        valid = np.isfinite(selected) & (w[None, :, :] > 0)
        weighted = np.where(valid, selected * w[None, :, :], 0.0)
        denom = np.where(valid, w[None, :, :], 0.0).sum(axis=2)
        hourly = np.divide(
            weighted.sum(axis=2),
            denom,
            out=np.full((rain_values.shape[0], end - start), np.nan, dtype="float64"),
            where=denom > 0,
        )
        rolling = aggregate_hourly_matrix(hourly)
        total = np.nansum(hourly, axis=0)
        all_missing = np.isnan(hourly).all(axis=0)
        total[all_missing] = np.nan
        duration = np.nansum(hourly > 0, axis=0)
        avg_intensity = np.divide(
            total,
            duration,
            out=np.full_like(total, np.nan, dtype="float64"),
            where=duration > 0,
        )

        chunk_grid_ids = grid_ids[start:end]
        rows.append(
            pd.DataFrame(
                {
                    "grid_id": chunk_grid_ids,
                    "event_id": event_id,
                    "rainfall_1h_max": rolling[1],
                    "rainfall_3h_max": rolling[3],
                    "rainfall_6h_max": rolling[6],
                    "rainfall_24h_total": rolling[24],
                    "rainfall_total": total,
                    "rainfall_duration_hours": duration.astype("float64"),
                    "rainfall_avg_intensity": avg_intensity,
                    "idw_station_count": station_counts[start:end].astype("float64"),
                    "idw_avg_distance_m": avg_distances[start:end],
                }
            )
        )

        if args.save_hourly_rainfall:
            hourly_df = pd.DataFrame(hourly.T, columns=pivot.index)
            hourly_df.insert(0, "grid_id", chunk_grid_ids)
            hourly_long = hourly_df.melt(
                id_vars="grid_id", var_name="observed_time", value_name="rainfall_mm"
            )
            hourly_long.insert(1, "event_id", event_id)
            hourly_parts.append(hourly_long)

    features = pd.concat(rows, ignore_index=True)
    hourly_out = pd.concat(hourly_parts, ignore_index=True) if hourly_parts else None
    return features[feature_columns], hourly_out


def build_grid_event_rainfall(
    ctx: BuildContext,
    event_meta: pd.DataFrame,
    station_rainfall_raw: pd.DataFrame,
    station_meta: pd.DataFrame,
    grid_static: pd.DataFrame,
    args: argparse.Namespace,
) -> tuple[pd.DataFrame, pd.DataFrame | None]:
    feature_parts: list[pd.DataFrame] = []
    hourly_parts: list[pd.DataFrame] = []
    for event in tqdm(event_meta.to_dict("records"), desc="grid_event_rainfall"):
        event_id = event["event_id"]
        start = pd.Timestamp(event["rain_start_time"])
        end = pd.Timestamp(event["rain_end_time"])
        event_rain = station_rainfall_raw[
            (station_rainfall_raw["observed_time"] >= start)
            & (station_rainfall_raw["observed_time"] <= end)
        ]
        features, hourly = interpolate_event_rainfall(
            event_id, event_rain, station_meta, grid_static, args, ctx
        )
        feature_parts.append(features)
        if hourly is not None:
            hourly_parts.append(hourly)
    grid_event_rainfall = pd.concat(feature_parts, ignore_index=True)
    grid_hourly = pd.concat(hourly_parts, ignore_index=True) if hourly_parts else None
    return grid_event_rainfall, grid_hourly


def build_grid_event_label(
    ctx: BuildContext,
    event_meta: pd.DataFrame,
    grid_gdf: gpd.GeoDataFrame,
    flooded_threshold: float,
) -> pd.DataFrame:
    label_parts: list[pd.DataFrame] = []
    base_grid = grid_gdf[["grid_id", "grid_area", "geometry"]].copy()
    for event in tqdm(event_meta.to_dict("records"), desc="grid_event_label"):
        event_id = event["event_id"]
        flood_file = Path(event["flood_trace_file"])
        labels = base_grid[["grid_id", "grid_area", "geometry"]].copy()
        labels["event_id"] = event_id
        labels["flood_overlap_area"] = 0.0
        labels["distance_to_flood_trace_m"] = np.nan

        try:
            flood_gdf = gpd.read_file(flood_file)
        except Exception as exc:
            ctx.warn(f"{event_id}: failed to read flood trace file {flood_file}: {exc}")
            labels["flood_overlap_ratio"] = np.nan
            labels["is_flooded"] = False
            label_parts.append(labels.drop(columns=["geometry", "grid_area"]))
            continue

        if flood_gdf.crs is None:
            flood_gdf = flood_gdf.set_crs(ctx.projected_crs)
            ctx.warn(f"{event_id}: flood trace CRS missing; assumed {ctx.projected_crs}.")
        flood_gdf = filter_flood_gdf_for_event(flood_gdf, int(event["flood_trace_year"]), ctx, flood_file)
        flood_gdf = flood_gdf.to_crs(ctx.projected_crs)
        flood_gdf = clean_geometries(flood_gdf[["geometry"]].copy(), ctx, flood_file)
        if flood_gdf.empty:
            ctx.warn(f"{event_id}: flood trace has no usable geometries.")
            labels["flood_overlap_ratio"] = 0.0
            labels["is_flooded"] = False
            label_parts.append(labels.drop(columns=["geometry", "grid_area"]))
            continue

        flood_union = unary_union(list(flood_gdf.geometry))
        labels["distance_to_flood_trace_m"] = labels.geometry.distance(flood_union)

        candidates = gpd.sjoin(
            labels[["grid_id", "geometry"]],
            flood_gdf[["geometry"]],
            how="inner",
            predicate="intersects",
        )
        if not candidates.empty:
            intersecting_grid_ids = candidates["grid_id"].drop_duplicates().tolist()
            hit_mask = labels["grid_id"].isin(intersecting_grid_ids)
            overlap_area = labels.loc[hit_mask, "geometry"].intersection(flood_union).area
            labels.loc[hit_mask, "flood_overlap_area"] = overlap_area.to_numpy()

        labels["flood_overlap_ratio"] = labels["flood_overlap_area"] / labels["grid_area"]
        labels["is_flooded"] = labels["flood_overlap_ratio"] > flooded_threshold
        label_parts.append(
            labels[
                [
                    "grid_id",
                    "event_id",
                    "flood_overlap_ratio",
                    "flood_overlap_area",
                    "is_flooded",
                    "distance_to_flood_trace_m",
                ]
            ].copy()
        )

    return pd.concat(label_parts, ignore_index=True)


def build_training_preview(
    grid_static: pd.DataFrame,
    grid_event_rainfall: pd.DataFrame,
    grid_event_label: pd.DataFrame,
    output_path: Path,
    preview_rows: int,
) -> tuple[bool, pd.DataFrame]:
    rainfall_key_dupes = grid_event_rainfall.duplicated(["grid_id", "event_id"]).any()
    label_key_dupes = grid_event_label.duplicated(["grid_id", "event_id"]).any()
    grid_key_dupes = grid_static.duplicated(["grid_id"]).any()
    joined = (
        grid_event_label.merge(grid_event_rainfall, on=["grid_id", "event_id"], how="inner")
        .merge(grid_static, on="grid_id", how="inner")
    )
    join_ok = (
        not rainfall_key_dupes
        and not label_key_dupes
        and not grid_key_dupes
        and len(joined) == len(grid_event_label)
    )
    preview = joined.head(preview_rows).copy()
    write_parquet(preview, output_path)
    return join_ok, preview


def missing_rate(df: pd.DataFrame, columns: list[str]) -> dict[str, float]:
    if df.empty:
        return {col: math.nan for col in columns}
    return {col: float(df[col].isna().mean()) for col in columns if col in df.columns}


def build_report(
    ctx: BuildContext,
    tables: dict[str, pd.DataFrame],
    event_meta: pd.DataFrame,
    join_ok: bool,
    args: argparse.Namespace,
) -> dict[str, Any]:
    label = tables["grid_event_label"]
    rainfall = tables["grid_event_rainfall"]
    positive_count = int(label["is_flooded"].sum()) if "is_flooded" in label else 0
    positive_rate = float(label["is_flooded"].mean()) if len(label) else math.nan
    rainfall_feature_cols = [
        "rainfall_1h_max",
        "rainfall_3h_max",
        "rainfall_6h_max",
        "rainfall_24h_total",
        "rainfall_total",
        "rainfall_duration_hours",
        "rainfall_avg_intensity",
    ]
    label_cols = [
        "flood_overlap_ratio",
        "flood_overlap_area",
        "is_flooded",
        "distance_to_flood_trace_m",
    ]
    report = {
        "created_at": datetime.now(timezone.utc).astimezone().isoformat(),
        "input_raw_files": sorted(ctx.input_files),
        "processed_tables": {
            name: {
                "row_count": int(len(df)),
                "columns": list(df.columns),
            }
            for name, df in tables.items()
        },
        "event_ids": event_meta["event_id"].tolist(),
        "grid_count": int(len(tables["grid_static"])),
        "station_count": int(len(tables["station_meta"])),
        "is_flooded_positive_count": positive_count,
        "is_flooded_positive_rate": positive_rate,
        "rainfall_feature_missing_rate": missing_rate(rainfall, rainfall_feature_cols),
        "rainfall_feature_missing_rate_overall": float(rainfall[rainfall_feature_cols].isna().mean().mean())
        if len(rainfall)
        else math.nan,
        "label_missing_rate": missing_rate(label, label_cols),
        "label_missing_rate_overall": float(label[label_cols].isna().mean().mean()) if len(label) else math.nan,
        "idw_avg_station_count": float(rainfall["idw_station_count"].mean())
        if "idw_station_count" in rainfall and len(rainfall)
        else math.nan,
        "join_validation_ok": join_ok,
        "parameters": {
            "idw_k": args.idw_k,
            "idw_power": args.idw_power,
            "idw_epsilon": args.idw_epsilon,
            "idw_max_distance_m": args.idw_max_distance_m,
            "flooded_threshold": args.flooded_threshold,
            "alternative_flooded_threshold": args.alternative_flooded_threshold,
            "save_hourly_rainfall": args.save_hourly_rainfall,
        },
        "warnings": ctx.warnings,
    }
    return report


def print_summary(report: dict[str, Any], output_dir: Path) -> None:
    print("\nBuild complete: flood_dataset_v1")
    print(f"Output directory: {output_dir}")
    print("\nGenerated files:")
    for name in report["processed_tables"]:
        print(f"- {output_dir / (name + '.parquet')}")
    print(f"- {output_dir / 'model_training_dataset_preview.parquet'}")
    print(f"- {output_dir / 'build_report.json'}")

    print("\nRow counts:")
    for name, meta in report["processed_tables"].items():
        print(f"- {name}: {meta['row_count']:,}")

    print(f"\nJoin validation: {report['join_validation_ok']}")
    print(
        "Positive labels: "
        f"{report['is_flooded_positive_count']:,} "
        f"({report['is_flooded_positive_rate']:.6f})"
    )
    print(f"Rainfall feature missing rate: {report['rainfall_feature_missing_rate_overall']:.6f}")
    print("\nWarnings:")
    if report["warnings"]:
        for warning in report["warnings"]:
            print(f"- {warning}")
    else:
        print("- None")

    print("\nJoin code example:")
    print(
        "import pandas as pd\n"
        f"base = '{output_dir}'\n"
        "grid_static = pd.read_parquet(f'{base}/grid_static.parquet')\n"
        "rainfall = pd.read_parquet(f'{base}/grid_event_rainfall.parquet')\n"
        "label = pd.read_parquet(f'{base}/grid_event_label.parquet')\n"
        "train = label.merge(rainfall, on=['grid_id', 'event_id'], how='inner')\n"
        "train = train.merge(grid_static, on='grid_id', how='inner')\n"
    )


def main() -> None:
    args = parse_args()
    output_dir = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    initial_crs = CRS.from_user_input(DEFAULT_PROJECTED_CRS)
    ctx = BuildContext(raw_dir=args.raw_dir, output_dir=output_dir, projected_crs=initial_crs)

    dem_path = find_dem_path(ctx)
    flood_files = discover_flood_trace_files(ctx)

    event_meta = build_event_meta(ctx, flood_files)
    if event_meta.empty:
        raise RuntimeError("No events were built from flood trace files.")

    grid_static, grid_gdf = build_grid_static(ctx, dem_path)
    rainfall_years = required_rainfall_years(event_meta)
    rainfall_files, _coverage = discover_rainfall_files(ctx, rainfall_years)
    station_meta, station_ids = build_station_meta(
        ctx=ctx,
        rainfall_files=rainfall_files,
        flood_files=flood_files,
        dem_path=dem_path,
        grid_static=grid_static,
    )
    station_rainfall_raw = build_station_rainfall_raw(
        ctx=ctx,
        rainfall_files=rainfall_files,
        station_meta=station_meta,
        station_ids=station_ids,
    )
    station_meta = augment_station_meta_from_rainfall_raw(
        ctx=ctx,
        station_meta=station_meta,
        station_rainfall_raw=station_rainfall_raw,
        flood_files=flood_files,
        dem_path=dem_path,
        grid_static=grid_static,
    )
    grid_event_rainfall, grid_hourly_rainfall = build_grid_event_rainfall(
        ctx=ctx,
        event_meta=event_meta,
        station_rainfall_raw=station_rainfall_raw,
        station_meta=station_meta,
        grid_static=grid_static,
        args=args,
    )
    grid_event_label = build_grid_event_label(
        ctx=ctx,
        event_meta=event_meta,
        grid_gdf=grid_gdf,
        flooded_threshold=args.flooded_threshold,
    )

    tables: dict[str, pd.DataFrame] = {
        "grid_static": grid_static,
        "event_meta": event_meta,
        "station_meta": station_meta,
        "station_rainfall_raw": station_rainfall_raw,
        "grid_event_rainfall": grid_event_rainfall,
        "grid_event_label": grid_event_label,
    }
    if grid_hourly_rainfall is not None:
        tables["grid_hourly_rainfall"] = grid_hourly_rainfall

    for table_name, df in tables.items():
        write_parquet(df, output_dir / f"{table_name}.parquet")

    join_ok, _preview = build_training_preview(
        grid_static=grid_static,
        grid_event_rainfall=grid_event_rainfall,
        grid_event_label=grid_event_label,
        output_path=output_dir / "model_training_dataset_preview.parquet",
        preview_rows=args.preview_rows,
    )

    report = build_report(ctx, tables, event_meta, join_ok, args)
    with (output_dir / "build_report.json").open("w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    print_summary(report, output_dir)


if __name__ == "__main__":
    main()
