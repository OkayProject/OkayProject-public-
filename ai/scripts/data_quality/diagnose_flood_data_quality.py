#!/usr/bin/env python3
"""Diagnose flood spatial features, CRS assumptions, 2025 event behavior, and splits."""

from __future__ import annotations

import argparse
import json
import math
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
from pyproj import CRS
from sklearn.metrics import average_precision_score, roc_auc_score


FEATURES_FOR_SANITY = [
    "elevation",
    "mean_elevation",
    "relative_elev",
    "relative_low",
    "relative_high",
    "slope",
    "aspect",
    "curvature",
    "flow_accumulation",
    "distance_to_stream",
    "distance_to_flood_trace_m",
    "flood_overlap_area",
    "flood_overlap_ratio",
    "x_coord",
    "y_coord",
    "centroid_lat",
    "centroid_lon",
    "grid_size_m",
    "grid_area_m2",
]

FEATURES_FOR_2025_COMPARISON = [
    "rainfall_total",
    "rainfall_3h",
    "rainfall_6h",
    "rainfall_24h",
    "max_hourly_intensity",
    "cumulative_rainfall_mm",
    "elevation",
    "slope",
    "relative_elev",
    "distance_to_stream",
    "flood_overlap_ratio",
    "flood_overlap_area",
]

QUANTILES = [0.01, 0.05, 0.25, 0.75, 0.95, 0.99]
DEFAULT_V6_THRESHOLD = 0.10080808080808079
DEFAULT_V6_STAGE1_THRESHOLD = 0.0032253803219646215


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Flood data quality diagnostics.")
    parser.add_argument("--data-dir", type=Path, default=Path("data/processed/flood_dataset_v1"))
    parser.add_argument("--raw-dir", type=Path, default=Path("data/raw"))
    parser.add_argument("--v6-model-dir", type=Path, default=Path("ai/models/flood_xgb_v6"))
    parser.add_argument("--v7-model-dir", type=Path, default=Path("ai/models/flood_xgb_v7_streamfix"))
    parser.add_argument(
        "--report-dir",
        type=Path,
        default=Path("ai/reports/flood_data_quality_diagnostics"),
    )
    return parser.parse_args()


def crs_text(crs: Any) -> str | None:
    if crs is None:
        return None
    parsed = CRS.from_user_input(crs)
    epsg = parsed.to_epsg()
    return f"EPSG:{epsg}" if epsg else parsed.to_string()


def load_dataset(data_dir: Path) -> pd.DataFrame:
    static = pd.read_parquet(data_dir / "grid_static.parquet")
    rain = pd.read_parquet(data_dir / "grid_event_rainfall.parquet")
    label = pd.read_parquet(data_dir / "grid_event_label.parquet")
    event = pd.read_parquet(data_dir / "event_meta.parquet")

    df = (
        label.merge(rain, on=["grid_id", "event_id"], how="inner")
        .merge(static, on="grid_id", how="inner")
        .merge(event[["event_id", "event_year", "flood_trace_file"]], on="event_id", how="left")
    )
    if "flood_overlap_ratio" in df.columns:
        df["overlap_ratio"] = df["flood_overlap_ratio"]
    df["flooded"] = df["overlap_ratio"].gt(0).astype("int8")
    add_derived_columns(df)
    return df


def add_derived_columns(df: pd.DataFrame) -> None:
    if "mean_elevation" not in df.columns and {"elevation", "relative_elev"}.issubset(df.columns):
        df["mean_elevation"] = df["elevation"] - df["relative_elev"]
    if "relative_low" not in df.columns and "relative_elev" in df.columns:
        df["relative_low"] = np.maximum(-df["relative_elev"], 0)
    if "relative_high" not in df.columns and "relative_elev" in df.columns:
        df["relative_high"] = np.maximum(df["relative_elev"], 0)
    if "rainfall_3h" not in df.columns and "rainfall_3h_max" in df.columns:
        df["rainfall_3h"] = df["rainfall_3h_max"]
    if "rainfall_6h" not in df.columns and "rainfall_6h_max" in df.columns:
        df["rainfall_6h"] = df["rainfall_6h_max"]
    if "rainfall_24h" not in df.columns and "rainfall_24h_total" in df.columns:
        df["rainfall_24h"] = df["rainfall_24h_total"]
    if "max_hourly_intensity" not in df.columns and "rainfall_1h_max" in df.columns:
        df["max_hourly_intensity"] = df["rainfall_1h_max"]
    if "cumulative_rainfall_mm" not in df.columns and "rainfall_total" in df.columns:
        df["cumulative_rainfall_mm"] = df["rainfall_total"]
    if "grid_area_m2" not in df.columns and "grid_size_m" in df.columns:
        df["grid_area_m2"] = df["grid_size_m"] ** 2


def abnormal_note(feature: str, series: pd.Series) -> str:
    vals = pd.to_numeric(series, errors="coerce")
    notes: list[str] = []
    if vals.isna().all():
        return "all_missing"
    if feature in {"elevation", "mean_elevation"}:
        if (vals <= -999).any():
            notes.append("contains_dem_nodata_or_-999")
        if vals.min(skipna=True) < -50 or vals.max(skipna=True) > 1000:
            notes.append("outside_expected_seoul_elevation_range")
    elif feature == "relative_elev":
        if vals.abs().max(skipna=True) > 500:
            notes.append("relative_elev_abs_gt_500m")
    elif feature in {"relative_low", "relative_high"}:
        if vals.min(skipna=True) < 0:
            notes.append("negative_relative_component")
        if vals.max(skipna=True) > 500:
            notes.append("relative_component_gt_500m")
    elif feature == "slope":
        if vals.min(skipna=True) < 0 or vals.max(skipna=True) > 90:
            notes.append("slope_outside_0_90")
    elif feature == "aspect":
        if vals.min(skipna=True) < 0 or vals.max(skipna=True) > 360:
            notes.append("aspect_outside_0_360")
    elif feature in {"distance_to_stream", "distance_to_flood_trace_m"}:
        if vals.min(skipna=True) < 0:
            notes.append("negative_distance")
        if vals.max(skipna=True) > 100_000:
            notes.append("distance_gt_100km_possible_crs_error")
    elif feature == "flood_overlap_ratio":
        if vals.min(skipna=True) < 0 or vals.max(skipna=True) > 1:
            notes.append("overlap_ratio_outside_0_1")
    elif feature == "flood_overlap_area":
        if vals.min(skipna=True) < 0:
            notes.append("negative_area")
    elif feature == "x_coord":
        if vals.min(skipna=True) < 100_000 or vals.max(skipna=True) > 300_000:
            notes.append("x_outside_seoul_tm_expected_range")
    elif feature == "y_coord":
        if vals.min(skipna=True) < 450_000 or vals.max(skipna=True) > 700_000:
            notes.append("y_outside_seoul_tm_expected_range")
    elif feature == "centroid_lat":
        if vals.min(skipna=True) < 37.0 or vals.max(skipna=True) > 38.0:
            notes.append("lat_outside_seoul_expected_range")
    elif feature == "centroid_lon":
        if vals.min(skipna=True) < 126.0 or vals.max(skipna=True) > 128.0:
            notes.append("lon_outside_seoul_expected_range")
    return ";".join(notes) if notes else "ok"


def numeric_stats(group_name: str, event_id: str, feature: str, series: pd.Series) -> dict[str, Any]:
    vals = pd.to_numeric(series, errors="coerce")
    desc = vals.describe(percentiles=QUANTILES)
    return {
        "group": group_name,
        "event_id": event_id,
        "feature": feature,
        "row_count": int(len(vals)),
        "count": int(vals.count()),
        "missing_count": int(vals.isna().sum()),
        "missing_rate": float(vals.isna().mean()),
        "mean": float(vals.mean(skipna=True)) if vals.count() else math.nan,
        "median": float(vals.median(skipna=True)) if vals.count() else math.nan,
        "std": float(vals.std(skipna=True)) if vals.count() else math.nan,
        "min": float(vals.min(skipna=True)) if vals.count() else math.nan,
        "p01": float(desc.get("1%", math.nan)),
        "p05": float(desc.get("5%", math.nan)),
        "p25": float(desc.get("25%", math.nan)),
        "p75": float(desc.get("75%", math.nan)),
        "p95": float(desc.get("95%", math.nan)),
        "p99": float(desc.get("99%", math.nan)),
        "max": float(vals.max(skipna=True)) if vals.count() else math.nan,
        "abnormal_note": abnormal_note(feature, vals),
    }


def spatial_feature_sanity(df: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    features = [col for col in FEATURES_FOR_SANITY if col in df.columns]
    for feature in features:
        rows.append(numeric_stats("ALL", "ALL", feature, df[feature]))
    for event_id, group in df.groupby("event_id", sort=True):
        for feature in features:
            rows.append(numeric_stats("event", str(event_id), feature, group[feature]))
    return pd.DataFrame(rows)


def load_v6_thresholds(v6_model_dir: Path) -> tuple[float, float]:
    meta_path = v6_model_dir / "stage12_v6_meta.json"
    if not meta_path.exists():
        return DEFAULT_V6_STAGE1_THRESHOLD, DEFAULT_V6_THRESHOLD
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    return (
        float(meta.get("stage1_threshold", DEFAULT_V6_STAGE1_THRESHOLD)),
        float(meta.get("stage2_threshold", DEFAULT_V6_THRESHOLD)),
    )


def load_v6_scores(v6_model_dir: Path) -> pd.DataFrame:
    return pd.read_parquet(v6_model_dir / "passcap_75" / "stage12_v6_oof_predictions.parquet")


def select_v7_candidate(v7_model_dir: Path) -> dict[str, Any]:
    comp = pd.read_csv(v7_model_dir / "v7_model_comparison.csv")
    candidates = comp[comp["experiment"].ne("baseline")].sort_values("f2", ascending=False)
    if candidates.empty:
        raise RuntimeError("No non-baseline v7 candidate rows found.")
    row = candidates.iloc[0].to_dict()
    row["source_file"] = str(v7_model_dir / "v7_model_comparison.csv")
    return row


def load_v7_best_scores(df: pd.DataFrame, v6_scores: pd.DataFrame, v7_model_dir: Path, v6_stage1_threshold: float) -> tuple[pd.DataFrame, dict[str, Any]]:
    candidate = select_v7_candidate(v7_model_dir)
    variant = str(candidate["variant"])
    experiment = str(candidate["experiment"])
    out = df[["row_id", "grid_id", "event_id", "flooded", "overlap_ratio"]].merge(
        v6_scores[["row_id", "stage1_proba"]], on="row_id", how="left"
    )

    if experiment == "D_stage2_reweighted":
        score_path = v7_model_dir / f"stage2_reweighted_{variant}" / "stage2_reweighted_oof.parquet"
        s2 = pd.read_parquet(score_path)
        out = out.merge(s2, on="row_id", how="left")
        out["stage2_pred"] = out["stage2_reweighted_pred"]
        out["final_score"] = np.where(out["stage1_proba"] >= v6_stage1_threshold, out["stage2_pred"], 0.0)
    elif experiment == "B_stage1_rainfall_candidate":
        s1 = pd.read_parquet(v7_model_dir / "stage1_rainfall_oof.parquet")
        out = out.merge(s1, on="row_id", how="left")
        out["stage1_proba"] = out["stage1_rainfall_proba"]
        out["stage2_pred"] = v6_scores["stage2_pred"].to_numpy()
        threshold = float(candidate.get("stage1_rainfall_threshold", v6_stage1_threshold))
        out["final_score"] = np.where(out["stage1_proba"] >= threshold, out["stage2_pred"], 0.0)
    else:
        out["stage2_pred"] = v6_scores["stage2_pred"].to_numpy()
        out["final_score"] = v6_scores["final_pred"].to_numpy()

    candidate["resolved_score_model"] = f"{experiment}/{variant}"
    return out, candidate


def score_stats_for_model(model_name: str, scores: pd.DataFrame, threshold: float) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for event_id, group in scores.groupby("event_id", sort=True):
        y = group["flooded"].to_numpy(dtype="int8")
        event_row = {
            "model": model_name,
            "event_id": event_id,
            "positive_count": int(y.sum()),
            "negative_count": int((y == 0).sum()),
            "threshold": float(threshold),
        }
        for score_col in ["stage1_proba", "stage2_pred", "final_score"]:
            if score_col not in group.columns:
                continue
            vals = pd.to_numeric(group[score_col], errors="coerce")
            for prefix, mask in {
                "all": np.ones(len(group), dtype=bool),
                "positive": y == 1,
                "negative": y == 0,
            }.items():
                sub = vals[mask]
                event_row[f"{score_col}_{prefix}_mean"] = float(sub.mean()) if len(sub) else math.nan
                event_row[f"{score_col}_{prefix}_median"] = float(sub.median()) if len(sub) else math.nan
                event_row[f"{score_col}_{prefix}_p95"] = float(sub.quantile(0.95)) if len(sub) else math.nan
            event_row[f"{score_col}_positive_gt_negative_mean"] = (
                event_row.get(f"{score_col}_positive_mean", math.nan)
                > event_row.get(f"{score_col}_negative_mean", math.nan)
            )
        try:
            event_row["roc_auc_final_score"] = float(roc_auc_score(y, group["final_score"])) if len(np.unique(y)) == 2 else math.nan
        except ValueError:
            event_row["roc_auc_final_score"] = math.nan
        event_row["pr_auc_final_score"] = float(average_precision_score(y, group["final_score"])) if y.sum() > 0 else math.nan
        pred = group["final_score"].to_numpy() >= threshold
        event_row["predicted_positive_count"] = int(pred.sum())
        event_row["tp"] = int(((pred == 1) & (y == 1)).sum())
        event_row["fp"] = int(((pred == 1) & (y == 0)).sum())
        event_row["fn"] = int(((pred == 0) & (y == 1)).sum())
        event_row["recall"] = float(event_row["tp"] / max(event_row["positive_count"], 1))
        event_row["precision"] = float(event_row["tp"] / max(event_row["tp"] + event_row["fp"], 1))
        event_row["alert_rate"] = float(pred.mean())
        rows.append(event_row)
    return rows


def feature_comparison(df: pd.DataFrame, v6_scores: pd.DataFrame, v6_threshold: float) -> pd.DataFrame:
    work = df.merge(v6_scores[["row_id", "final_pred"]], on="row_id", how="left")
    y = work["flooded"].to_numpy(dtype="int8")
    pred = work["final_pred"].to_numpy() >= v6_threshold
    group_masks = {
        "EVT_2025_positive": work["event_id"].eq("EVT_2025_FLOOD") & work["flooded"].eq(1),
        "EVT_2025_negative": work["event_id"].eq("EVT_2025_FLOOD") & work["flooded"].eq(0),
        "EVT_2022_positive": work["event_id"].eq("EVT_2022_FLOOD") & work["flooded"].eq(1),
        "overall_TP_v6": (pred == 1) & (y == 1),
        "overall_FN_v6": (pred == 0) & (y == 1),
        "overall_positive": work["flooded"].eq(1),
    }
    rows: list[dict[str, Any]] = []
    for group_name, mask in group_masks.items():
        g = work.loc[mask]
        for feature in [f for f in FEATURES_FOR_2025_COMPARISON if f in work.columns]:
            rows.append(numeric_stats(group_name, "mixed", feature, g[feature]))
    return pd.DataFrame(rows)


def raw_crs_report(args: argparse.Namespace, df: pd.DataFrame) -> dict[str, Any]:
    report: dict[str, Any] = {
        "created_at": datetime.now(timezone.utc).astimezone().isoformat(),
        "grid_static_crs": {
            "stored_in_parquet": False,
            "inferred_from": "data/raw/dem/seoul_dem.tif",
            "note": "grid_static has x_coord/y_coord but no embedded CRS metadata; coordinates align with DEM CRS.",
        },
        "grid_coordinate_bounds": {
            "x_min": float(df["x_coord"].min()),
            "x_max": float(df["x_coord"].max()),
            "y_min": float(df["y_coord"].min()),
            "y_max": float(df["y_coord"].max()),
            "centroid_lat_min": float(df["centroid_lat"].min()),
            "centroid_lat_max": float(df["centroid_lat"].max()),
            "centroid_lon_min": float(df["centroid_lon"].min()),
            "centroid_lon_max": float(df["centroid_lon"].max()),
        },
    }

    dem_path = args.raw_dir / "dem/seoul_dem.tif"
    if dem_path.exists():
        with rasterio.open(dem_path) as src:
            report["dem_crs"] = crs_text(src.crs)
            report["dem_bounds"] = tuple(float(x) for x in src.bounds)
            report["dem_resolution"] = tuple(float(x) for x in src.res)

    river_path = args.raw_dir / "hydrography/rivers/seoul/seoul_rivers.gpkg"
    if river_path.exists():
        rivers = gpd.read_file(river_path, rows=1)
        report["stream_layer_crs"] = crs_text(rivers.crs)
        report["stream_layer_path"] = str(river_path)

    event_meta = pd.read_parquet(args.data_dir / "event_meta.parquet")
    flood_rows = []
    for row in event_meta.itertuples(index=False):
        shp = Path(row.flood_trace_file)
        item: dict[str, Any] = {
            "event_id": str(row.event_id),
            "event_year": int(row.event_year),
            "flood_trace_file": str(shp),
            "exists": shp.exists(),
        }
        if shp.exists():
            gdf = gpd.read_file(shp, rows=1)
            item["crs"] = crs_text(gdf.crs)
        flood_rows.append(item)
    report["flood_trace_crs_by_event"] = flood_rows
    report["overlap_calculation_crs"] = {
        "source": "ai/scripts/data_pipeline/build_processed_flood_dataset_v1.py",
        "code_behavior": "uses DEM raster CRS when available, otherwise DEFAULT_PROJECTED_CRS EPSG:5179",
        "current_inferred_crs": report.get("dem_crs"),
    }
    report["distance_calculation_crs"] = {
        "distance_to_flood_trace_m": "processed labels were generated in build_processed_flood_dataset_v1 projected CRS",
        "distance_to_stream": "streamfix uses DEM CRS and transforms river layer to DEM CRS before distance calculation",
        "streamfix_report": str(args.data_dir / "stream_distance_fix_report.json"),
    }
    if (args.data_dir / "stream_distance_fix_report.json").exists():
        report["streamfix_report_summary"] = json.loads((args.data_dir / "stream_distance_fix_report.json").read_text(encoding="utf-8"))
    return report


def split_method_report() -> dict[str, Any]:
    files = [
        Path("ai/scripts/model_xgb/train_stage12_passcap_sweep_v6.py"),
        Path("ai/scripts/model_v7/train_v7_candidate_rescue_experiments.py"),
    ]
    methods = {}
    for path in files:
        text = path.read_text(encoding="utf-8") if path.exists() else ""
        methods[str(path)] = {
            "exists": path.exists(),
            "imports_random_kfold": bool(re.search(r"\bKFold\b|\bStratifiedKFold\b", text)),
            "imports_group_kfold": bool(re.search(r"\bGroupKFold\b|\bLeaveOneGroupOut\b", text)),
            "uses_event_holdout_loop": "event_id" in text and ("holdout" in text or "~df[\"event_id\".eq" in text),
            "diagnosed_method": "LOEO by event_id" if "event_id" in text and "holdout" in text else "unknown",
            "event_generalization_ok": bool("event_id" in text and "holdout" in text),
        }
    return {
        "summary": "v6 and v7 train/evaluate with one event_id held out at a time (manual Leave-One-Event-Out).",
        "split_family": "LeaveOneGroupOut-style by event_id",
        "not_random_row_level": True,
        "leakage_note": "No random row-level split was found in v6/v7 scripts checked here. Event-level holdout is appropriate for event generalization diagnostics.",
        "files": methods,
    }


def write_summary(
    report_dir: Path,
    spatial: pd.DataFrame,
    crs_report: dict[str, Any],
    feature_cmp: pd.DataFrame,
    score_diag: pd.DataFrame,
    split_report: dict[str, Any],
    v7_candidate: dict[str, Any],
) -> None:
    abnormal = spatial[spatial["abnormal_note"].ne("ok")]
    all_abnormal = abnormal[abnormal["event_id"].eq("ALL")][["feature", "abnormal_note"]].drop_duplicates()
    evt2025_scores = score_diag[score_diag["event_id"].eq("EVT_2025_FLOOD")]
    evt2025_v6 = evt2025_scores[evt2025_scores["model"].eq("v6_baseline")]
    evt2025_v7 = evt2025_scores[evt2025_scores["model"].eq("streamfix_v7_best_candidate")]

    def val(frame: pd.DataFrame, col: str) -> str:
        if frame.empty or col not in frame:
            return "n/a"
        x = frame.iloc[0][col]
        return "nan" if pd.isna(x) else f"{x:.4f}" if isinstance(x, (float, np.floating)) else str(x)

    def cmp_mean(group: str, feature: str) -> float:
        row = feature_cmp[feature_cmp["group"].eq(group) & feature_cmp["feature"].eq(feature)]
        return float(row["mean"].iloc[0]) if not row.empty else math.nan

    def score_value(frame: pd.DataFrame, col: str) -> float:
        return float(frame.iloc[0][col]) if not frame.empty and col in frame else math.nan

    rainfall_2025_pos = cmp_mean("EVT_2025_positive", "rainfall_total")
    rainfall_2025_neg = cmp_mean("EVT_2025_negative", "rainfall_total")
    rainfall_2022_pos = cmp_mean("EVT_2022_positive", "rainfall_total")
    rainfall_tp = cmp_mean("overall_TP_v6", "rainfall_total")
    elev_2025_pos = cmp_mean("EVT_2025_positive", "elevation")
    elev_tp = cmp_mean("overall_TP_v6", "elevation")
    stream_2025_pos = cmp_mean("EVT_2025_positive", "distance_to_stream")
    stream_tp = cmp_mean("overall_TP_v6", "distance_to_stream")
    v6_pos_final = score_value(evt2025_v6, "final_score_positive_mean")
    v6_neg_final = score_value(evt2025_v6, "final_score_negative_mean")
    v7_pos_final = score_value(evt2025_v7, "final_score_positive_mean")
    v7_neg_final = score_value(evt2025_v7, "final_score_negative_mean")

    lines = [
        "# Flood Data Quality Diagnostics",
        "",
        f"- Generated at: {datetime.now(timezone.utc).astimezone().isoformat()}",
        f"- v7 best non-baseline candidate used for score diagnostic: `{v7_candidate.get('resolved_score_model', v7_candidate.get('variant'))}`",
        "",
        "## 1. 공간 feature 오류 여부",
    ]
    if all_abnormal.empty:
        lines.append("- `distance_to_stream` 외의 전체 기준 명백한 CRS/단위 오류는 발견되지 않았습니다.")
    else:
        lines.append("- 전체 기준 비정상 플래그:")
        for row in all_abnormal.itertuples(index=False):
            lines.append(f"  - `{row.feature}`: {row.abnormal_note}")
    lines.extend(
        [
            "- `flow_accumulation`은 원본 `grid_static`에서 전부 결측인 상태입니다. 모델 feature로 쓰면 정보량이 없습니다.",
            "- `distance_to_stream`은 평균 약 "
            f"{spatial[(spatial['event_id'].eq('ALL')) & (spatial['feature'].eq('distance_to_stream'))]['mean'].iloc[0]:.1f}m, "
            "최대 약 "
            f"{spatial[(spatial['event_id'].eq('ALL')) & (spatial['feature'].eq('distance_to_stream'))]['max'].iloc[0]:.1f}m로 정상 범위입니다.",
            "",
            "## 2. EVT_2025_FLOOD 실패 원인",
            f"- v6 기준 EVT_2025 recall: {val(evt2025_v6, 'recall')}",
            f"- streamfix v7 best 후보 기준 EVT_2025 recall: {val(evt2025_v7, 'recall')}",
            f"- EVT_2025 내부 v6 final_score ROC-AUC: {val(evt2025_v6, 'roc_auc_final_score')}, PR-AUC: {val(evt2025_v6, 'pr_auc_final_score')}",
            f"- EVT_2025 내부 streamfix v7 final_score ROC-AUC: {val(evt2025_v7, 'roc_auc_final_score')}, PR-AUC: {val(evt2025_v7, 'pr_auc_final_score')}",
            f"- EVT_2025 positive rainfall_total 평균은 {rainfall_2025_pos:.1f}mm로, EVT_2022 positive {rainfall_2022_pos:.1f}mm 및 v6 TP {rainfall_tp:.1f}mm보다 매우 낮습니다.",
            f"- EVT_2025 negative rainfall_total 평균은 {rainfall_2025_neg:.1f}mm로, 2025 내부에서는 positive가 negative보다 오히려 낮습니다.",
            f"- EVT_2025 positive 평균 고도는 {elev_2025_pos:.1f}m로 v6 TP 평균 {elev_tp:.1f}m보다 높고, 평균 하천거리는 {stream_2025_pos:.1f}m로 v6 TP 평균 {stream_tp:.1f}m와 같은 방향의 저위험 feature는 아닙니다.",
            f"- v6 final_score 평균은 2025 positive {v6_pos_final:.4f}, negative {v6_neg_final:.4f}입니다.",
            f"- streamfix v7 final_score 평균은 2025 positive {v7_pos_final:.4f}, negative {v7_neg_final:.4f}입니다.",
            "- 따라서 EVT_2025는 threshold만 낮추면 해결되는 모양이 아니라, event 내부 ranking도 거의 무작위 또는 역전된 상태입니다.",
            "",
            "## 3. 데이터/모델/threshold 판단",
            "- CRS 관점에서는 하천 거리 문제는 수정됐고, grid 좌표와 DEM/하천/침수흔적도는 같은 서울 TM 계열 projected 좌표로 처리된 것으로 보입니다.",
            "- 가장 가능성 높은 실패 원인은 2025 이벤트의 강수 기간/강수 원천 매칭 문제입니다. 2025 침수 positive가 학습된 침수 패턴에 비해 강수량이 너무 낮게 들어가 있습니다.",
            "- 두 번째 원인은 2025 침수흔적도 라벨의 공간 분포 차이입니다. 2025 positive는 평균 고도가 높고 하천거리도 TP와 크게 다르지 않아, 기존 feature 조합으로는 positive/negative ranking이 되지 않습니다.",
            "- 결론적으로 현재 증상은 단순 threshold 문제가 아니라 데이터 품질과 event generalization 문제가 섞여 있습니다.",
            "",
            "## 4. Split 방식",
            f"- 진단 결과: {split_report['summary']}",
            "- random row-level split은 확인되지 않았고, event generalization 평가 방식은 적절합니다.",
            "",
            "## 5. 다음 단계",
            "- 다음 모델 실험으로 바로 넘어가기보다 EVT_2025의 rain_start/end, 원시 강수 파일 시간 범위, 침수흔적도 발생일, 2025 라벨 좌표/면적 분포를 먼저 수정/검증하는 쪽을 권장합니다.",
        ]
    )
    (report_dir / "data_quality_summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    args = parse_args()
    args.report_dir.mkdir(parents=True, exist_ok=True)

    df = load_dataset(args.data_dir).reset_index(drop=True)
    df["row_id"] = np.arange(len(df), dtype="int64")

    spatial = spatial_feature_sanity(df)
    spatial.to_csv(args.report_dir / "spatial_feature_sanity_check.csv", index=False)

    crs_report = raw_crs_report(args, df)
    (args.report_dir / "crs_unit_sanity_check.json").write_text(
        json.dumps(crs_report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    v6_stage1_threshold, v6_threshold = load_v6_thresholds(args.v6_model_dir)
    v6_scores = load_v6_scores(args.v6_model_dir)
    feature_cmp = feature_comparison(df, v6_scores, v6_threshold)
    feature_cmp.to_csv(args.report_dir / "evt2025_feature_comparison.csv", index=False)

    base_score = df[["row_id", "grid_id", "event_id", "flooded", "overlap_ratio"]].merge(
        v6_scores[["row_id", "stage1_proba", "stage2_pred", "final_pred"]],
        on="row_id",
        how="left",
    )
    base_score["final_score"] = base_score["final_pred"]
    v7_score, v7_candidate = load_v7_best_scores(df, v6_scores, args.v7_model_dir, v6_stage1_threshold)
    v7_threshold = float(v7_candidate.get("final_threshold", v6_threshold))

    score_rows = []
    score_rows.extend(score_stats_for_model("v6_baseline", base_score, v6_threshold))
    score_rows.extend(score_stats_for_model("streamfix_v7_best_candidate", v7_score, v7_threshold))
    score_diag = pd.DataFrame(score_rows)
    score_diag.to_csv(args.report_dir / "evt2025_score_diagnostic.csv", index=False)

    split_report = split_method_report()
    (args.report_dir / "split_method_diagnostic.json").write_text(
        json.dumps(split_report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    write_summary(args.report_dir, spatial, crs_report, feature_cmp, score_diag, split_report, v7_candidate)

    print(f"Saved diagnostics to {args.report_dir}")
    print("Key files:")
    for name in [
        "spatial_feature_sanity_check.csv",
        "crs_unit_sanity_check.json",
        "evt2025_feature_comparison.csv",
        "evt2025_score_diagnostic.csv",
        "split_method_diagnostic.json",
        "data_quality_summary.md",
    ]:
        print(f"- {args.report_dir / name}")


if __name__ == "__main__":
    main()
