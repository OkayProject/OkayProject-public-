#!/usr/bin/env python3
"""Build the v11 rainfall feature repair artifact.

This artifact keeps the v10 staged model structure intact. It compares rainfall
features for flood-trace-positive grids against negative grids, then writes
runtime-safe rainfall feature candidates that are normalized within each event.
"""

from __future__ import annotations

import argparse
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score, roc_auc_score


EPS = 1e-6
SUSPECT_EVENT_ID = "EVT_2025_FLOOD"
RAW_RAINFALL_FEATURES = [
    "idw_rainfall_mm",
    "rainfall_1h",
    "rainfall_3h",
    "rainfall_6h",
    "rainfall_24h",
    "cumulative_rainfall_mm",
    "max_hourly_intensity",
    "rainfall_avg_intensity",
    "rainfall_ratio_1h_24h",
    "rainfall_ratio_3h_24h",
    "rainfall_ratio_6h_24h",
]
EVENT_RELATIVE_BASE_FEATURES = [
    "rainfall_1h",
    "rainfall_3h",
    "rainfall_6h",
    "rainfall_24h",
    "cumulative_rainfall_mm",
    "max_hourly_intensity",
    "rainfall_avg_intensity",
]
QUANTILES = [0.05, 0.25, 0.5, 0.75, 0.95]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build v11 rainfall feature repair artifact.")
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=Path("ai/processed/flood_dataset_v1"),
        help="Processed flood dataset directory. v1 matches the v10 operational data_version.",
    )
    parser.add_argument(
        "--v10-schema",
        type=Path,
        default=Path("ai/reports/flood_v10_stage3_operational/feature_schema.json"),
    )
    parser.add_argument(
        "--report-dir",
        type=Path,
        default=Path("ai/reports/flood_v11_rainfall_feature_repair"),
    )
    parser.add_argument(
        "--suspect-event-id",
        default=SUSPECT_EVENT_ID,
        help="Event excluded from train-fit aggregate recommendations.",
    )
    return parser.parse_args()


def finite_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def write_json(data: dict[str, Any], path: Path) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def load_joined_dataset(data_dir: Path) -> pd.DataFrame:
    rain = pd.read_parquet(data_dir / "grid_event_rainfall.parquet")
    label = pd.read_parquet(data_dir / "grid_event_label.parquet")
    event = pd.read_parquet(data_dir / "event_meta.parquet")
    df = label.merge(rain, on=["grid_id", "event_id"], how="inner")
    df = df.merge(event[["event_id", "event_year", "needs_manual_review"]], on="event_id", how="left")
    df["is_flooded"] = df["flood_overlap_ratio"].gt(0).astype("int8")
    add_v10_rainfall_aliases(df)
    return df


def add_v10_rainfall_aliases(df: pd.DataFrame) -> None:
    alias_map = {
        "idw_rainfall_mm": "rainfall_total",
        "rainfall_1h": "rainfall_1h_max",
        "rainfall_3h": "rainfall_3h_max",
        "rainfall_6h": "rainfall_6h_max",
        "rainfall_24h": "rainfall_24h_total",
        "cumulative_rainfall_mm": "rainfall_total",
        "max_hourly_intensity": "rainfall_1h_max",
    }
    for target, source in alias_map.items():
        if target not in df.columns and source in df.columns:
            df[target] = df[source]
    df["rainfall_ratio_1h_24h"] = df["rainfall_1h"] / (df["rainfall_24h"] + EPS)
    df["rainfall_ratio_3h_24h"] = df["rainfall_3h"] / (df["rainfall_24h"] + EPS)
    df["rainfall_ratio_6h_24h"] = df["rainfall_6h"] / (df["rainfall_24h"] + EPS)
    df["rainfall_missing_flag"] = df[["rainfall_1h", "rainfall_24h", "cumulative_rainfall_mm"]].isna().any(axis=1).astype("int8")


def numeric_summary(series: pd.Series, prefix: str) -> dict[str, float | int | None]:
    values = pd.to_numeric(series, errors="coerce")
    desc = values.describe(percentiles=QUANTILES)
    out: dict[str, float | int | None] = {
        f"{prefix}_count": int(values.count()),
        f"{prefix}_missing_count": int(values.isna().sum()),
        f"{prefix}_mean": finite_float(values.mean(skipna=True)),
        f"{prefix}_std": finite_float(values.std(skipna=True)),
        f"{prefix}_min": finite_float(values.min(skipna=True)),
        f"{prefix}_max": finite_float(values.max(skipna=True)),
    }
    for q in QUANTILES:
        key = f"{int(q * 100):02d}%"
        out[f"{prefix}_p{int(q * 100):02d}"] = finite_float(desc.get(key))
    return out


def comparison_scope(df: pd.DataFrame, scope: str, suspect_event_id: str) -> pd.DataFrame:
    if scope == "overall_trainfit":
        return df[df["event_id"].ne(suspect_event_id)].copy()
    if scope == "overall_all":
        return df.copy()
    event_df = df[df["event_id"].eq(scope)].copy()
    if event_df.empty:
        raise ValueError(f"Unknown comparison scope: {scope}")
    return event_df


def compare_positive_negative(df: pd.DataFrame, suspect_event_id: str) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    scopes = ["overall_trainfit", "overall_all"] + sorted(df["event_id"].dropna().unique().tolist())
    for scope in scopes:
        scoped = comparison_scope(df, scope, suspect_event_id)
        y = scoped["is_flooded"].to_numpy(dtype="int8")
        pos_count = int(y.sum())
        neg_count = int((y == 0).sum())
        if pos_count == 0 or neg_count == 0:
            continue
        for feature in RAW_RAINFALL_FEATURES:
            if feature not in scoped.columns:
                continue
            valid = scoped[[feature, "is_flooded"]].dropna()
            if valid.empty or valid["is_flooded"].nunique() < 2:
                continue
            pos = valid.loc[valid["is_flooded"].eq(1), feature]
            neg = valid.loc[valid["is_flooded"].eq(0), feature]
            if pos.empty or neg.empty:
                continue
            feature_values = valid[feature].to_numpy(dtype="float64")
            labels = valid["is_flooded"].to_numpy(dtype="int8")
            try:
                roc_auc = float(roc_auc_score(labels, feature_values))
            except ValueError:
                roc_auc = math.nan
            try:
                pr_auc = float(average_precision_score(labels, feature_values))
            except ValueError:
                pr_auc = math.nan
            neg_median = float(neg.median())
            pos_median = float(pos.median())
            rows.append(
                {
                    "scope": scope,
                    "event_id": scope if scope.startswith("EVT_") else "ALL",
                    "is_suspect_scope": bool(scope == suspect_event_id),
                    "feature": feature,
                    "positive_count": int(len(pos)),
                    "negative_count": int(len(neg)),
                    **numeric_summary(pos, "positive"),
                    **numeric_summary(neg, "negative"),
                    "median_lift_pos_minus_neg": pos_median - neg_median,
                    "median_ratio_pos_to_neg": float((pos_median + EPS) / (neg_median + EPS)),
                    "mean_lift_pos_minus_neg": float(pos.mean() - neg.mean()),
                    "positive_above_negative_median_rate": float((pos > neg_median).mean()),
                    "roc_auc_positive_by_feature": roc_auc,
                    "pr_auc_positive_by_feature": pr_auc,
                    "direction": direction_label(roc_auc),
                }
            )
    return pd.DataFrame(rows)


def direction_label(roc_auc: float) -> str:
    if not math.isfinite(roc_auc):
        return "unknown"
    if roc_auc >= 0.6:
        return "positive_higher"
    if roc_auc <= 0.4:
        return "positive_lower"
    return "weak_or_mixed"


def add_event_relative_features(df: pd.DataFrame) -> list[str]:
    created: list[str] = []
    for feature in EVENT_RELATIVE_BASE_FEATURES:
        values = pd.to_numeric(df[feature], errors="coerce")
        grouped = df.assign(_value=values).groupby("event_id")["_value"]
        event_median = grouped.transform("median")
        event_q25 = grouped.transform(lambda x: x.quantile(0.25))
        event_q75 = grouped.transform(lambda x: x.quantile(0.75))
        event_iqr = (event_q75 - event_q25).replace(0, np.nan)
        pct_name = f"{feature}_event_pct"
        z_name = f"{feature}_event_robust_z"
        centered_name = f"{feature}_event_centered_mm"
        df[pct_name] = grouped.rank(method="average", pct=True).astype("float32")
        df[z_name] = ((values - event_median) / (event_iqr + EPS)).astype("float32")
        df[centered_name] = (values - event_median).astype("float32")
        created.extend([pct_name, z_name, centered_name])

    df["rainfall_burst_ratio_1h_to_total"] = (
        df["rainfall_1h"] / (df["cumulative_rainfall_mm"] + EPS)
    ).astype("float32")
    df["rainfall_burst_ratio_3h_to_total"] = (
        df["rainfall_3h"] / (df["cumulative_rainfall_mm"] + EPS)
    ).astype("float32")
    df["rainfall_event_percentile_signal"] = (
        df[
            [
                "rainfall_1h_event_pct",
                "rainfall_3h_event_pct",
                "rainfall_6h_event_pct",
                "rainfall_24h_event_pct",
                "cumulative_rainfall_mm_event_pct",
                "max_hourly_intensity_event_pct",
            ]
        ]
        .mean(axis=1)
        .astype("float32")
    )
    created.extend(
        [
            "rainfall_burst_ratio_1h_to_total",
            "rainfall_burst_ratio_3h_to_total",
            "rainfall_event_percentile_signal",
        ]
    )
    return created


def make_repaired_feature_table(df: pd.DataFrame, created_features: list[str]) -> pd.DataFrame:
    columns = [
        "grid_id",
        "event_id",
        "event_year",
        "is_flooded",
        "flood_overlap_ratio",
        "rainfall_missing_flag",
        *RAW_RAINFALL_FEATURES,
        *created_features,
    ]
    existing = [col for col in columns if col in df.columns]
    out = df[existing].copy()
    for col in out.columns:
        if col in {"grid_id", "event_id"}:
            continue
        if pd.api.types.is_float_dtype(out[col]):
            out[col] = out[col].astype("float32")
        elif pd.api.types.is_integer_dtype(out[col]):
            out[col] = pd.to_numeric(out[col], downcast="integer")
    return out


def overall_top_features(comparison: pd.DataFrame, scope: str) -> list[dict[str, Any]]:
    scoped = comparison[comparison["scope"].eq(scope)].copy()
    if scoped.empty:
        return []
    scoped["auc_distance_from_random"] = (scoped["roc_auc_positive_by_feature"] - 0.5).abs()
    cols = [
        "feature",
        "direction",
        "roc_auc_positive_by_feature",
        "pr_auc_positive_by_feature",
        "median_lift_pos_minus_neg",
        "positive_above_negative_median_rate",
    ]
    return scoped.sort_values("auc_distance_from_random", ascending=False)[cols].head(8).to_dict("records")


def build_repair_spec(
    args: argparse.Namespace,
    row_count: int,
    positive_count: int,
    created_features: list[str],
    comparison: pd.DataFrame,
) -> dict[str, Any]:
    v10_schema: dict[str, Any] = {}
    if args.v10_schema.exists():
        v10_schema = json.loads(args.v10_schema.read_text(encoding="utf-8"))
    return {
        "artifact_version": "flood_v11_rainfall_feature_repair",
        "created_at": datetime.now(timezone.utc).astimezone().isoformat(),
        "inherits_model_structure_from": "flood_xgb_v10_stage3_operational",
        "changes_model_structure": False,
        "purpose": (
            "Compare rainfall distributions inside flood-trace-positive grids against negative grids "
            "and produce event-relative rainfall feature candidates for the next v10-structure model run."
        ),
        "source_dataset": str(args.data_dir),
        "suspect_event_policy": {
            args.suspect_event_id: "included in per-event diagnostics; excluded from train-fit aggregate recommendations"
        },
        "row_count": int(row_count),
        "positive_count": int(positive_count),
        "negative_count": int(row_count - positive_count),
        "v10_stage2_features": v10_schema.get("stage2_features", []),
        "v10_stage3_features": v10_schema.get("stage3_features", []),
        "v10_rainfall_aliases_preserved": {
            "idw_rainfall_mm": "rainfall_total",
            "rainfall_1h": "rainfall_1h_max",
            "rainfall_3h": "rainfall_3h_max",
            "rainfall_6h": "rainfall_6h_max",
            "rainfall_24h": "rainfall_24h_total",
            "cumulative_rainfall_mm": "rainfall_total",
            "max_hourly_intensity": "rainfall_1h_max",
        },
        "runtime_safe_v11_features": created_features,
        "runtime_safety_note": (
            "Event-relative percentiles and robust z-scores use only rainfall values within the current event/grid set. "
            "Positive/negative labels are used for diagnostics and feature selection only."
        ),
        "recommended_stage2_rainfall_overlay": [
            "rainfall_event_percentile_signal",
            "rainfall_1h_event_pct",
            "rainfall_3h_event_pct",
            "rainfall_6h_event_pct",
            "rainfall_24h_event_pct",
            "cumulative_rainfall_mm_event_pct",
            "max_hourly_intensity_event_pct",
            "rainfall_burst_ratio_1h_to_total",
            "rainfall_burst_ratio_3h_to_total",
        ],
        "recommended_stage3_rainfall_overlay": [
            "rainfall_event_percentile_signal",
            "rainfall_1h_event_robust_z",
            "rainfall_3h_event_robust_z",
            "rainfall_6h_event_robust_z",
            "cumulative_rainfall_mm_event_robust_z",
            "max_hourly_intensity_event_robust_z",
        ],
        "top_trainfit_rainfall_diagnostics": overall_top_features(comparison, "overall_trainfit"),
        "outputs": {
            "comparison_csv": "rainfall_positive_negative_comparison.csv",
            "repaired_feature_parquet": "grid_event_rainfall_features_v11.parquet",
            "spec_json": "rainfall_feature_repair_spec.json",
            "summary_md": "v11_rainfall_feature_repair_summary.md",
        },
    }


def format_number(value: Any, digits: int = 4) -> str:
    number = finite_float(value)
    if number is None:
        return "nan"
    return f"{number:.{digits}f}"


def write_summary(
    path: Path,
    args: argparse.Namespace,
    df: pd.DataFrame,
    comparison: pd.DataFrame,
    created_features: list[str],
) -> None:
    overall = comparison[comparison["scope"].eq("overall_trainfit")].copy()
    overall = overall.sort_values("roc_auc_positive_by_feature", ascending=False)
    top = overall.head(5)
    bottom = overall.tail(5).sort_values("roc_auc_positive_by_feature")
    event_mismatch = comparison[
        comparison["scope"].str.startswith("EVT_")
        & comparison["median_lift_pos_minus_neg"].lt(0)
        & comparison["feature"].isin(EVENT_RELATIVE_BASE_FEATURES)
    ]
    lines = [
        "# v11 Rainfall Feature Repair Artifact",
        "",
        "## Scope",
        "",
        "- v10 staged model structure is preserved. No v10 model files or thresholds are changed.",
        f"- Source dataset: `{args.data_dir}`",
        f"- Rows: `{len(df):,}` / positives: `{int(df['is_flooded'].sum()):,}` / negatives: `{int((df['is_flooded'] == 0).sum()):,}`",
        f"- Suspect holdout: `{args.suspect_event_id}` is kept in per-event diagnostics but excluded from train-fit aggregate ranking.",
        "",
        "## What Changed For v11",
        "",
        "- Raw v10 rainfall aliases are preserved for compatibility.",
        "- New event-relative rainfall features are added: percentile, robust z-score, and centered-mm variants.",
        "- Positive/negative labels are used to diagnose which rainfall signals separate flood-trace grids; labels are not required by the runtime-safe repaired features.",
        "",
        "## Stronger Train-Fit Rainfall Signals",
        "",
    ]
    for _, row in top.iterrows():
        lines.append(
            f"- `{row['feature']}`: ROC-AUC `{format_number(row['roc_auc_positive_by_feature'])}`, "
            f"median lift `{format_number(row['median_lift_pos_minus_neg'])}`, direction `{row['direction']}`"
        )
    lines.extend(["", "## Weak Or Reversed Train-Fit Signals", ""])
    for _, row in bottom.iterrows():
        lines.append(
            f"- `{row['feature']}`: ROC-AUC `{format_number(row['roc_auc_positive_by_feature'])}`, "
            f"median lift `{format_number(row['median_lift_pos_minus_neg'])}`, direction `{row['direction']}`"
        )
    lines.extend(
        [
            "",
            "## Event-Level Caution",
            "",
            f"- Event-feature pairs where positive median rainfall is below negative median rainfall: `{len(event_mismatch):,}`",
            "- This is the main reason v11 adds event-relative features instead of only increasing raw rainfall weight.",
            "",
            "## Outputs",
            "",
            "- `rainfall_positive_negative_comparison.csv`",
            "- `grid_event_rainfall_features_v11.parquet`",
            "- `rainfall_feature_repair_spec.json`",
            "- `v11_rainfall_feature_repair_summary.md`",
            "",
            "## Rebuild",
            "",
            "```bash",
            "cd /Users/kimleewon/Desktop/Project/okayproject",
            "ai/.venv/bin/python ai/scripts/data_quality/build_v11_rainfall_feature_repair.py",
            "```",
            "",
            "## Created Runtime-Safe Features",
            "",
        ]
    )
    lines.extend(f"- `{feature}`" for feature in created_features)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    args = parse_args()
    args.report_dir.mkdir(parents=True, exist_ok=True)

    df = load_joined_dataset(args.data_dir)
    created_features = add_event_relative_features(df)
    comparison = compare_positive_negative(df, args.suspect_event_id)
    repaired = make_repaired_feature_table(df, created_features)
    spec = build_repair_spec(
        args=args,
        row_count=len(df),
        positive_count=int(df["is_flooded"].sum()),
        created_features=created_features,
        comparison=comparison,
    )

    comparison.to_csv(args.report_dir / "rainfall_positive_negative_comparison.csv", index=False)
    repaired.to_parquet(
        args.report_dir / "grid_event_rainfall_features_v11.parquet",
        index=False,
        compression="zstd",
    )
    write_json(spec, args.report_dir / "rainfall_feature_repair_spec.json")
    write_summary(
        args.report_dir / "v11_rainfall_feature_repair_summary.md",
        args,
        df,
        comparison,
        created_features,
    )

    print(f"Wrote v11 rainfall feature repair artifact to {args.report_dir}")


if __name__ == "__main__":
    main()
