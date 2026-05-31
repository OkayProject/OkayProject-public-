#!/usr/bin/env python3
"""Add a CRS-correct distance_to_stream feature to flood_dataset_v1 grid_static.

The DEM/grid coordinates in flood_dataset_v1 are in the DEM projected CRS
(Seoul TM-like, matching EPSG:5186 for the current raw data). Older model code
incorrectly labelled those coordinates as EPSG:5179 while transforming the
river layer, which produced stream distances around 1,500 km. This script uses
the DEM CRS explicitly and writes a sanity-checked feature into grid_static.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import geopandas as gpd
import pandas as pd
import rasterio
from pyproj import CRS
from shapely.geometry import Point
from shapely.ops import unary_union


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Add distance_to_stream to grid_static parquet.")
    parser.add_argument("--data-dir", type=Path, default=Path("data/processed/flood_dataset_v1"))
    parser.add_argument("--dem-path", type=Path, default=Path("data/raw/dem/seoul_dem.tif"))
    parser.add_argument(
        "--river-path",
        type=Path,
        default=Path("data/raw/hydrography/rivers/seoul/seoul_rivers.gpkg"),
    )
    parser.add_argument("--report-path", type=Path, default=None)
    return parser.parse_args()


def crs_text(crs: CRS | None) -> str | None:
    if crs is None:
        return None
    epsg = crs.to_epsg()
    return f"EPSG:{epsg}" if epsg else crs.to_string()


def main() -> None:
    args = parse_args()
    grid_path = args.data_dir / "grid_static.parquet"
    if not grid_path.exists():
        raise FileNotFoundError(f"Missing grid_static parquet: {grid_path}")
    if not args.dem_path.exists():
        raise FileNotFoundError(f"Missing DEM raster: {args.dem_path}")
    if not args.river_path.exists():
        raise FileNotFoundError(f"Missing river layer: {args.river_path}")

    grid = pd.read_parquet(grid_path)
    with rasterio.open(args.dem_path) as src:
        dem_crs = CRS.from_user_input(src.crs)

    rivers = gpd.read_file(args.river_path)
    if rivers.crs is None:
        rivers = rivers.set_crs(dem_crs)
    rivers = rivers.to_crs(dem_crs)
    river_union = unary_union(list(rivers.geometry.dropna()))

    points = gpd.GeoDataFrame(
        grid[["grid_id", "x_coord", "y_coord"]].copy(),
        geometry=[Point(x, y) for x, y in zip(grid["x_coord"], grid["y_coord"])],
        crs=dem_crs,
    )
    distances = points.geometry.distance(river_union)
    out = grid.drop(columns=["distance_to_stream"], errors="ignore").copy()
    out["distance_to_stream"] = distances.to_numpy(dtype="float64")
    out.to_parquet(grid_path, index=False)

    dist_path = args.data_dir / "grid_distance_to_stream.parquet"
    out[["grid_id", "distance_to_stream"]].to_parquet(dist_path, index=False)

    stats = out["distance_to_stream"].describe(percentiles=[0.01, 0.05, 0.1, 0.25, 0.5, 0.75, 0.9, 0.95, 0.99])
    report = {
        "created_at": datetime.now(timezone.utc).astimezone().isoformat(),
        "grid_static_path": str(grid_path),
        "distance_cache_path": str(dist_path),
        "dem_path": str(args.dem_path),
        "river_path": str(args.river_path),
        "dem_crs": crs_text(dem_crs),
        "river_original_crs": crs_text(CRS.from_user_input(gpd.read_file(args.river_path, rows=1).crs)),
        "grid_count": int(len(out)),
        "distance_to_stream_stats_m": {k: float(v) for k, v in stats.to_dict().items()},
        "sanity_warning": bool(out["distance_to_stream"].max() > 100_000),
    }
    report_path = args.report_path or args.data_dir / "stream_distance_fix_report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
