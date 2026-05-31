#!/usr/bin/env python3
"""Create flood_dataset_v2 by removing uncertain flood-boundary grid labels."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
from pyproj import CRS
from shapely.ops import unary_union
from tqdm import tqdm


DEFAULT_PROJECTED_CRS = "EPSG:5179"
COPY_TABLES = (
    "grid_static.parquet",
    "event_meta.parquet",
    "station_meta.parquet",
    "station_rainfall_raw.parquet",
)


@dataclass
class BuildContext:
    warnings: list[str] = field(default_factory=list)

    def warn(self, message: str) -> None:
        self.warnings.append(message)
        print(f"WARNING: {message}", file=sys.stderr)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Remove flood-trace boundary-buffer grid/event labels from flood_dataset_v1."
    )
    parser.add_argument("--input-dir", type=Path, default=Path("data/processed/flood_dataset_v1"))
    parser.add_argument("--output-dir", type=Path, default=Path("data/processed/flood_dataset_v2"))
    parser.add_argument("--raw-dir", type=Path, default=Path("data/raw"))
    parser.add_argument("--buffer-distance-m", type=float, default=50.0)
    parser.add_argument(
        "--sensitivity-distances-m",
        type=str,
        default="30,50,100",
        help="Comma-separated distances for removal sensitivity reporting.",
    )
    return parser.parse_args()


def normalize_text(value: Any) -> str:
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return ""
    return unicodedata.normalize("NFC", str(value)).strip()


def get_projected_crs(raw_dir: Path, ctx: BuildContext) -> CRS:
    dem_candidates = sorted((raw_dir / "dem").glob("**/*.tif"))
    if not dem_candidates:
        ctx.warn(f"No DEM found under {raw_dir / 'dem'}; using {DEFAULT_PROJECTED_CRS}.")
        return CRS.from_user_input(DEFAULT_PROJECTED_CRS)
    with rasterio.open(dem_candidates[0]) as src:
        if src.crs is None:
            ctx.warn(f"{dem_candidates[0]} has no CRS; using {DEFAULT_PROJECTED_CRS}.")
            return CRS.from_user_input(DEFAULT_PROJECTED_CRS)
        return CRS.from_user_input(src.crs)


def filter_flood_gdf_for_event(
    gdf: gpd.GeoDataFrame, flood_trace_year: int, ctx: BuildContext, source: Path
) -> gpd.GeoDataFrame:
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


def clean_geometries(gdf: gpd.GeoDataFrame, ctx: BuildContext, source: Path) -> gpd.GeoDataFrame:
    out = gdf[gdf.geometry.notna()].copy()
    if out.empty:
        return out
    invalid_before = int((~out.geometry.is_valid).sum())
    if invalid_before:
        out.loc[~out.geometry.is_valid, "geometry"] = out.loc[~out.geometry.is_valid, "geometry"].buffer(0)
        invalid_after = int((~out.geometry.is_valid).sum())
        repaired = invalid_before - invalid_after
        if repaired:
            ctx.warn(f"{source}: repaired {repaired} invalid geometries with buffer(0).")
        if invalid_after:
            ctx.warn(f"{source}: dropping {invalid_after} unrecoverable invalid geometries.")
            out = out[out.geometry.is_valid].copy()
    return out[~out.geometry.is_empty].copy()


def load_event_flood_union(
    event: dict[str, Any], projected_crs: CRS, ctx: BuildContext
):
    event_id = str(event["event_id"])
    flood_file = Path(event["flood_trace_file"])
    try:
        flood_gdf = gpd.read_file(flood_file)
    except Exception as exc:
        ctx.warn(f"{event_id}: failed to read flood trace file {flood_file}: {exc}")
        return None

    if flood_gdf.crs is None:
        flood_gdf = flood_gdf.set_crs(projected_crs)
        ctx.warn(f"{event_id}: flood trace CRS missing; assumed {projected_crs}.")

    flood_gdf = filter_flood_gdf_for_event(
        flood_gdf,
        int(event.get("flood_trace_year", event["event_year"])),
        ctx,
        flood_file,
    )
    flood_gdf = flood_gdf.to_crs(projected_crs)
    flood_gdf = clean_geometries(flood_gdf[["geometry"]].copy(), ctx, flood_file)
    if flood_gdf.empty:
        ctx.warn(f"{event_id}: flood trace has no usable geometries.")
        return None
    return unary_union(list(flood_gdf.geometry))


def make_grid_points(grid_static: pd.DataFrame, projected_crs: CRS) -> gpd.GeoDataFrame:
    return gpd.GeoDataFrame(
        grid_static[["grid_id", "x_coord", "y_coord"]].copy(),
        geometry=gpd.points_from_xy(grid_static["x_coord"], grid_static["y_coord"]),
        crs=projected_crs,
    )


def removed_index_for_distance(
    grid_points: gpd.GeoDataFrame,
    event_meta: pd.DataFrame,
    projected_crs: CRS,
    buffer_distance_m: float,
    ctx: BuildContext,
) -> pd.DataFrame:
    parts: list[pd.DataFrame] = []
    for event in tqdm(event_meta.to_dict("records"), desc=f"boundary_buffer_{buffer_distance_m:g}m"):
        event_id = str(event["event_id"])
        flood_union = load_event_flood_union(event, projected_crs, ctx)
        if flood_union is None or flood_union.is_empty:
            continue
        buffer_zone = flood_union.boundary.buffer(buffer_distance_m)
        if buffer_zone.is_empty:
            continue
        mask = grid_points.geometry.within(buffer_zone)
        removed_grid_ids = grid_points.loc[mask, "grid_id"]
        if not removed_grid_ids.empty:
            parts.append(pd.DataFrame({"grid_id": removed_grid_ids.to_numpy(), "event_id": event_id}))
    if not parts:
        return pd.DataFrame(columns=["grid_id", "event_id"])
    return pd.concat(parts, ignore_index=True).drop_duplicates(["grid_id", "event_id"])


def anti_join_removed(df: pd.DataFrame, removed: pd.DataFrame) -> pd.DataFrame:
    if removed.empty:
        return df.copy()
    filtered = df.merge(removed.assign(_remove=1), on=["grid_id", "event_id"], how="left")
    filtered = filtered[filtered["_remove"].isna()].drop(columns="_remove")
    return filtered.reset_index(drop=True)


def label_stats(label: pd.DataFrame) -> dict[str, int | float]:
    total = int(len(label))
    pos = int(label["flood_overlap_ratio"].gt(0).sum())
    neg = total - pos
    return {
        "total": total,
        "positive": pos,
        "negative": neg,
        "positive_ratio": float(pos / total) if total else 0.0,
    }


def removal_stats(label: pd.DataFrame, removed: pd.DataFrame) -> dict[str, int | float]:
    before = label_stats(label)
    if removed.empty:
        removed_labeled = label.iloc[0:0].copy()
    else:
        removed_labeled = label.merge(removed, on=["grid_id", "event_id"], how="inner")
    removed_pos = int(removed_labeled["flood_overlap_ratio"].gt(0).sum())
    removed_total = int(len(removed_labeled))
    removed_neg = removed_total - removed_pos
    remaining = before["total"] - removed_total
    remaining_pos = before["positive"] - removed_pos
    remaining_neg = before["negative"] - removed_neg
    return {
        "total_before": int(before["total"]),
        "positive_before": int(before["positive"]),
        "negative_before": int(before["negative"]),
        "positive_ratio_before": float(before["positive_ratio"]),
        "removed": removed_total,
        "removed_positive": removed_pos,
        "removed_negative": removed_neg,
        "removed_ratio": float(removed_total / before["total"]) if before["total"] else 0.0,
        "positive_loss_ratio": float(removed_pos / before["positive"]) if before["positive"] else 0.0,
        "remaining": int(remaining),
        "remaining_positive": int(remaining_pos),
        "remaining_negative": int(remaining_neg),
        "remaining_positive_ratio": float(remaining_pos / remaining) if remaining else 0.0,
    }


def parse_sensitivity_distances(value: str, primary: float) -> list[float]:
    distances: list[float] = []
    for item in value.split(","):
        item = item.strip()
        if not item:
            continue
        distances.append(float(item))
    if primary not in distances:
        distances.append(primary)
    return sorted(set(distances))


def validate_join(
    grid_static: pd.DataFrame,
    label_v2: pd.DataFrame,
    rainfall_v2: pd.DataFrame,
) -> dict[str, bool | int]:
    label_keys = label_v2[["grid_id", "event_id"]].drop_duplicates()
    rainfall_keys = rainfall_v2[["grid_id", "event_id"]].drop_duplicates()
    key_check = label_keys.merge(rainfall_keys, on=["grid_id", "event_id"], how="outer", indicator=True)
    unmatched = int(key_check["_merge"].ne("both").sum())
    grid_joined = label_v2[["grid_id"]].drop_duplicates().merge(
        grid_static[["grid_id"]], on="grid_id", how="left", indicator=True
    )
    missing_grid = int(grid_joined["_merge"].ne("both").sum())
    return {
        "label_rainfall_row_count_match": int(len(label_v2)) == int(len(rainfall_v2)),
        "label_rainfall_key_unmatched": unmatched,
        "grid_static_missing_grid_count": missing_grid,
        "join_possible": unmatched == 0 and missing_grid == 0,
    }


def copy_passthrough_tables(input_dir: Path, output_dir: Path) -> None:
    for filename in COPY_TABLES:
        shutil.copy2(input_dir / filename, output_dir / filename)


def main() -> None:
    args = parse_args()
    ctx = BuildContext()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    projected_crs = get_projected_crs(args.raw_dir, ctx)
    grid_static = pd.read_parquet(args.input_dir / "grid_static.parquet")
    event_meta = pd.read_parquet(args.input_dir / "event_meta.parquet")
    label_v1 = pd.read_parquet(args.input_dir / "grid_event_label.parquet")
    rainfall_v1 = pd.read_parquet(args.input_dir / "grid_event_rainfall.parquet")
    grid_points = make_grid_points(grid_static, projected_crs)

    total = len(label_v1)
    print(f"전체 grid×event: {total:,}")

    sensitivity_results = []
    removed_primary: pd.DataFrame | None = None
    for distance in parse_sensitivity_distances(args.sensitivity_distances_m, args.buffer_distance_m):
        distance_ctx = BuildContext()
        removed = removed_index_for_distance(grid_points, event_meta, projected_crs, distance, distance_ctx)
        stats = removal_stats(label_v1, removed)
        stats["buffer_distance_m"] = float(distance)
        stats["warnings"] = distance_ctx.warnings
        sensitivity_results.append(stats)
        print(
            f"[sensitivity {distance:g}m] removed={stats['removed']:,} "
            f"({stats['removed_ratio'] * 100:.2f}%), "
            f"removed_pos={stats['removed_positive']:,}, "
            f"positive_loss={stats['positive_loss_ratio'] * 100:.2f}%"
        )
        if stats["positive_loss_ratio"] > 0.10:
            print("WARNING: positive 손실 10% 초과, buffer 거리 재검토 필요")
        ctx.warnings.extend(distance_ctx.warnings)
        if float(distance) == float(args.buffer_distance_m):
            removed_primary = removed

    if removed_primary is None:
        raise RuntimeError("Primary buffer removal index was not created.")

    stats = removal_stats(label_v1, removed_primary)
    label_v2 = anti_join_removed(label_v1, removed_primary)
    rainfall_v2 = anti_join_removed(rainfall_v1, removed_primary)
    v2_stats = label_stats(label_v2)
    validation = validate_join(grid_static, label_v2, rainfall_v2)

    copy_passthrough_tables(args.input_dir, args.output_dir)
    label_v2.to_parquet(args.output_dir / "grid_event_label.parquet", index=False)
    rainfall_v2.to_parquet(args.output_dir / "grid_event_rainfall.parquet", index=False)
    removed_primary.to_parquet(args.output_dir / "buffer_removed_index.parquet", index=False)

    report = {
        "created_at": datetime.now(timezone.utc).astimezone().isoformat(),
        "source_dataset": str(args.input_dir),
        "output_dataset": str(args.output_dir),
        "projected_crs": projected_crs.to_string(),
        "buffer_distance_m": float(args.buffer_distance_m),
        **stats,
        "v2": v2_stats,
        "sensitivity": sensitivity_results,
        "validation": validation,
        "warnings": ctx.warnings,
    }
    with (args.output_dir / "build_report_v2.json").open("w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    v1_stats = label_stats(label_v1)
    print(f"buffer 제거 대상: {stats['removed']:,} ({stats['removed_ratio'] * 100:.2f}%)")
    print(f"  - 제거된 positive: {stats['removed_positive']:,}")
    print(f"  - 제거된 negative: {stats['removed_negative']:,}")
    print(f"잔존 grid×event: {stats['remaining']:,}")
    print(
        f"잔존 positive: {stats['remaining_positive']:,} "
        f"({stats['remaining_positive_ratio'] * 100:.4f}%)"
    )

    print("\n=== v1 vs v2 비교 ===")
    print(
        f"grid×event: {v1_stats['total']:,} → {v2_stats['total']:,} "
        f"({v1_stats['total'] - v2_stats['total']:,} 제거)"
    )
    print(f"positive:   {v1_stats['positive']:,} → {v2_stats['positive']:,}")
    print(f"negative:   {v1_stats['negative']:,} → {v2_stats['negative']:,}")
    print(f"positive ratio: {v1_stats['positive_ratio']:.4f} → {v2_stats['positive_ratio']:.4f}")
    print(f"join 가능 여부: {validation['join_possible']}")
    print(f"저장 완료: {args.output_dir}")


if __name__ == "__main__":
    main()
