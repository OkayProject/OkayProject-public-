from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import xgboost as xgb
from sklearn.metrics import average_precision_score, roc_auc_score


REPO_ROOT = Path(__file__).resolve().parents[3]
DATA_DIR = REPO_ROOT / "data/processed/flood_dataset_v1"
MODEL_DIR = REPO_ROOT / "ai/models/flood_xgb_v10_stage3_operational"
REPORT_DIR = REPO_ROOT / "ai/reports/flood_v10_stage3_operational"
SUSPECT_EVENT_ID = "EVT_2025_FLOOD"
EPS = 1e-6


def load_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as file:
        return json.load(file)


def write_json(data: dict[str, Any], path: Path) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def load_joined_dataset() -> pd.DataFrame:
    grid_static = pd.read_parquet(DATA_DIR / "grid_static.parquet")
    rainfall = pd.read_parquet(DATA_DIR / "grid_event_rainfall.parquet")
    label = pd.read_parquet(DATA_DIR / "grid_event_label.parquet")
    event_meta = pd.read_parquet(DATA_DIR / "event_meta.parquet")

    df = (
        label.rename(columns={"flood_overlap_ratio": "overlap_ratio"})
        .merge(rainfall, on=["grid_id", "event_id"], how="inner")
        .merge(grid_static, on="grid_id", how="inner")
        .merge(event_meta[["event_id", "event_year"]], on="event_id", how="left")
        .reset_index(drop=True)
    )
    df["row_id"] = np.arange(len(df), dtype="int64")
    df["label"] = df["overlap_ratio"].gt(0).astype("int8")
    add_feature_mappings(df)
    add_derived_features(df)
    return df


def add_feature_mappings(df: pd.DataFrame) -> None:
    invalid_elev = df["elevation"] <= -1000
    if invalid_elev.any():
        for col in ["elevation", "slope", "relative_elev", "curvature", "aspect"]:
            if col in df.columns:
                df.loc[invalid_elev, col] = np.nan

    df["mean_elevation"] = df["elevation"] - df["relative_elev"]
    df["relative_low"] = np.maximum(-df["relative_elev"], 0)
    df["relative_high"] = np.maximum(df["relative_elev"], 0)
    df["idw_rainfall_mm"] = df["rainfall_total"]
    df["rainfall_1h"] = df["rainfall_1h_max"]
    df["rainfall_3h"] = df["rainfall_3h_max"]
    df["rainfall_6h"] = df["rainfall_6h_max"]
    df["rainfall_24h"] = df["rainfall_24h_total"]
    df["cumulative_rainfall_mm"] = df["rainfall_total"]
    df["max_hourly_intensity"] = df["rainfall_1h_max"]
    missing_cols = [
        "idw_rainfall_mm",
        "rainfall_1h",
        "rainfall_3h",
        "rainfall_6h",
        "rainfall_24h",
        "cumulative_rainfall_mm",
        "max_hourly_intensity",
    ]
    df["rainfall_missing_flag"] = df[missing_cols].isna().any(axis=1).astype("int8")


def add_derived_features(df: pd.DataFrame) -> None:
    df["rainfall_ratio_1h_24h"] = df["rainfall_1h"] / (df["rainfall_24h"] + EPS)
    df["elevation_x_rainfall"] = df["elevation"] * df["idw_rainfall_mm"]
    df["relative_low_x_rainfall"] = df["relative_low"] * df["idw_rainfall_mm"]


def event_table(df: pd.DataFrame) -> pd.DataFrame:
    return (
        df[["event_id", "event_year"]]
        .drop_duplicates()
        .sort_values(["event_year", "event_id"])
        .reset_index(drop=True)
    )


def load_booster(path: Path) -> xgb.Booster:
    booster = xgb.Booster()
    booster.load_model(path)
    return booster


def predict_stage1(model: xgb.Booster, frame: pd.DataFrame, features: list[str]) -> np.ndarray:
    matrix = xgb.DMatrix(frame[features], feature_names=features)
    return model.predict(matrix).astype("float32")


def binary_metrics(y_true: np.ndarray, score: np.ndarray, threshold: float) -> dict[str, Any]:
    y_true = y_true.astype("int8")
    pred = score >= threshold
    pos = y_true == 1
    neg = ~pos
    tp = int((pred & pos).sum())
    fp = int((pred & neg).sum())
    fn = int((~pred & pos).sum())
    tn = int((~pred & neg).sum())
    precision = float(tp / max(tp + fp, 1))
    recall = float(tp / max(tp + fn, 1))
    return {
        "threshold": float(threshold),
        "row_count": int(len(y_true)),
        "positive_count": int(pos.sum()),
        "negative_count": int(neg.sum()),
        "predicted_positive_count": int(pred.sum()),
        "pass_rate": float(pred.mean()) if len(pred) else 0.0,
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "tn": tn,
        "recall": recall,
        "precision": precision,
        "f1": float(2 * precision * recall / max(precision + recall, EPS)),
        "pr_auc": safe_average_precision(y_true, score),
        "roc_auc": safe_roc_auc(y_true, score),
        "score_mean": float(np.mean(score)) if len(score) else 0.0,
        "score_median": float(np.median(score)) if len(score) else 0.0,
        "score_p95": float(np.quantile(score, 0.95)) if len(score) else 0.0,
    }


def safe_average_precision(y_true: np.ndarray, score: np.ndarray) -> float | None:
    if int(np.sum(y_true)) <= 0:
        return None
    return float(average_precision_score(y_true, score))


def safe_roc_auc(y_true: np.ndarray, score: np.ndarray) -> float | None:
    if len(np.unique(y_true)) < 2:
        return None
    return float(roc_auc_score(y_true, score))


def per_event_metrics(df: pd.DataFrame, score_col: str, threshold: float) -> pd.DataFrame:
    rows = []
    for event_id, group in df.groupby("event_id", sort=True):
        metrics = binary_metrics(
            group["label"].to_numpy(dtype="int8"),
            group[score_col].to_numpy(dtype="float32"),
            threshold,
        )
        metrics["event_id"] = event_id
        metrics["event_year"] = int(group["event_year"].iloc[0])
        rows.append(metrics)
    return pd.DataFrame(rows).sort_values(["event_year", "event_id"]).reset_index(drop=True)


def stage1_oof_predictions(df: pd.DataFrame, features: list[str]) -> tuple[pd.DataFrame, list[dict[str, Any]]]:
    trusted = df[df["event_id"].ne(SUSPECT_EVENT_ID)].copy()
    events = event_table(trusted)
    oof = np.full(len(trusted), np.nan, dtype="float32")
    fold_rows = []

    for fold_idx, row in enumerate(events.itertuples(index=False)):
        event_id = str(row.event_id)
        model = load_booster(MODEL_DIR / f"stage1_fold_{fold_idx}.ubj")
        mask = trusted["event_id"].eq(event_id).to_numpy()
        pred = predict_stage1(model, trusted.loc[mask], features)
        oof[mask] = pred
        fold_rows.append(
            {
                "fold": int(fold_idx),
                "event_id": event_id,
                "event_year": int(row.event_year),
                "holdout_rows": int(mask.sum()),
                "holdout_positive": int(trusted.loc[mask, "label"].sum()),
            }
        )

    if np.isnan(oof).any():
        raise RuntimeError("Recreated v10 stage1 OOF contains NaN values.")
    trusted["stage1_oof_score"] = oof
    return trusted, fold_rows


def stage1_ensemble_predictions(df: pd.DataFrame, features: list[str]) -> np.ndarray:
    predictions = []
    for fold_idx in range(9):
        model = load_booster(MODEL_DIR / f"stage1_fold_{fold_idx}.ubj")
        predictions.append(predict_stage1(model, df, features))
    return np.mean(np.vstack(predictions), axis=0).astype("float32")


def build_markdown(report: dict[str, Any]) -> str:
    oof = report["stage1_oof_metrics"]
    app = report["stage1_final_ensemble_apparent_metrics"]
    suspect = report["stage1_suspect_evt2025_final_ensemble_metrics"]
    lines = [
        "# v10 Stage1 Metrics Report",
        "",
    "This report recreates Stage1 metrics for `flood_xgb_v10_stage3_operational` from the packaged model files.",
        "",
        "## Threshold",
        "",
        f"- stage1_candidate: `{report['stage1_candidate']:.10f}`",
        f"- trusted events: `{', '.join(report['trusted_event_ids'])}`",
        f"- suspect holdout: `{SUSPECT_EVENT_ID}`",
        "",
        "## Recreated Fold-Holdout Metrics",
        "",
        "The original `stage12_v4_oof_predictions.parquet` threshold-selection artifact is not packaged in the repository. These metrics are recreated from the saved `stage1_fold_N.ubj` files using the v10 LOEO training script order sorted by `event_year,event_id`.",
        "",
        f"- recall: `{oof['recall']:.6f}`",
        f"- precision: `{oof['precision']:.6f}`",
        f"- pass_rate: `{oof['pass_rate']:.6f}`",
        f"- PR-AUC: `{oof['pr_auc']:.6f}`",
        f"- ROC-AUC: `{oof['roc_auc']:.6f}`",
        f"- TP/FP/FN/TN: `{oof['tp']:,}` / `{oof['fp']:,}` / `{oof['fn']:,}` / `{oof['tn']:,}`",
        "",
        "## Final Ensemble Apparent Metrics",
        "",
        "These are not validation metrics; they apply the saved 9-fold Stage1 ensemble back onto the trusted dataset.",
        "",
        f"- recall: `{app['recall']:.6f}`",
        f"- precision: `{app['precision']:.6f}`",
        f"- pass_rate: `{app['pass_rate']:.6f}`",
        f"- PR-AUC: `{app['pr_auc']:.6f}`",
        "",
        "## EVT_2025 Suspect Holdout",
        "",
        f"- recall: `{suspect['recall']:.6f}`",
        f"- precision: `{suspect['precision']:.6f}`",
        f"- pass_rate: `{suspect['pass_rate']:.6f}`",
        f"- positive_count: `{suspect['positive_count']:,}`",
        "",
        "## Outputs",
        "",
        "- `stage1_metrics_report.json`",
        "- `stage1_event_metrics.csv`",
        "- `stage1_metrics_report.md`",
        "",
    ]
    return "\n".join(lines)


def main() -> None:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    thresholds = load_json(MODEL_DIR / "thresholds.json")
    schema = load_json(MODEL_DIR / "feature_schema.json")
    features = schema["stage1_features"]
    stage1_threshold = float(thresholds["stage1_candidate"])

    df = load_joined_dataset()
    trusted, fold_mapping = stage1_oof_predictions(df, features)
    trusted["stage1_final_ensemble_score"] = stage1_ensemble_predictions(trusted, features)

    suspect = df[df["event_id"].eq(SUSPECT_EVENT_ID)].copy()
    suspect["stage1_final_ensemble_score"] = stage1_ensemble_predictions(suspect, features)

    trusted_event_ids = event_table(trusted)["event_id"].tolist()
    oof_metrics = binary_metrics(
        trusted["label"].to_numpy(dtype="int8"),
        trusted["stage1_oof_score"].to_numpy(dtype="float32"),
        stage1_threshold,
    )
    apparent_metrics = binary_metrics(
        trusted["label"].to_numpy(dtype="int8"),
        trusted["stage1_final_ensemble_score"].to_numpy(dtype="float32"),
        stage1_threshold,
    )
    suspect_metrics = binary_metrics(
        suspect["label"].to_numpy(dtype="int8"),
        suspect["stage1_final_ensemble_score"].to_numpy(dtype="float32"),
        stage1_threshold,
    )

    event_metrics = per_event_metrics(trusted, "stage1_oof_score", stage1_threshold)
    event_metrics.to_csv(REPORT_DIR / "stage1_event_metrics.csv", index=False)

    report = {
        "model_version": thresholds["model_version"],
        "data_version": thresholds.get("data_version"),
        "stage1_candidate": stage1_threshold,
        "stage1_features": features,
        "trusted_event_ids": trusted_event_ids,
        "suspect_event_id": SUSPECT_EVENT_ID,
        "fold_event_mapping": fold_mapping,
        "metric_definitions": {
        "stage1_oof_metrics": "Fold-holdout metrics recreated from saved stage1_fold_N models and sorted trusted events. The original stage12_v4_oof_predictions.parquet is not packaged.",
            "stage1_final_ensemble_apparent_metrics": "Saved 9-fold Stage1 ensemble applied back to trusted rows; not a validation metric.",
            "stage1_suspect_evt2025_final_ensemble_metrics": "Saved 9-fold Stage1 ensemble on suspect EVT_2025 holdout.",
        },
        "stage1_oof_metrics": oof_metrics,
        "stage1_final_ensemble_apparent_metrics": apparent_metrics,
        "stage1_suspect_evt2025_final_ensemble_metrics": suspect_metrics,
    }
    write_json(report, REPORT_DIR / "stage1_metrics_report.json")
    (REPORT_DIR / "stage1_metrics_report.md").write_text(build_markdown(report), encoding="utf-8")
    print(build_markdown(report))


if __name__ == "__main__":
    main()
