#!/usr/bin/env python3
"""Train a v11 rainfall-repair model with the v10 staged structure.

The model structure intentionally mirrors v10:

1. Stage1 terrain candidate classifier.
2. Stage2 risk classifier with rainfall features.
3. Stage3 danger-candidate false-positive filter.

v11 only changes the rainfall feature surface by adding the event-relative
features produced by build_v11_rainfall_feature_repair.py.
"""

from __future__ import annotations

import argparse
import json
import math
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import xgboost as xgb
from sklearn.metrics import average_precision_score, precision_recall_curve, roc_auc_score


SUSPECT_EVENT_ID = "EVT_2025_FLOOD"
EPS = 1e-6
RISK_LEVELS = {0: "일반", 1: "주의", 2: "위험", 3: "긴급"}


@dataclass
class TrainedFold:
    event_id: str
    stage1: xgb.XGBClassifier
    stage2: xgb.XGBClassifier
    stage3: xgb.XGBClassifier | None = None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train v11 rainfall repair with v10 staged model structure.")
    parser.add_argument(
        "--v11-feature-path",
        type=Path,
        default=Path("ai/reports/flood_v11_rainfall_feature_repair/grid_event_rainfall_features_v11.parquet"),
    )
    parser.add_argument(
        "--v11-spec",
        type=Path,
        default=Path("ai/reports/flood_v11_rainfall_feature_repair/rainfall_feature_repair_spec.json"),
    )
    parser.add_argument(
        "--grid-static-runtime",
        type=Path,
        default=Path("ai/models/flood_xgb_v10_stage3_operational/grid_static_runtime.parquet"),
    )
    parser.add_argument(
        "--v10-schema",
        type=Path,
        default=Path("ai/models/flood_xgb_v10_stage3_operational/feature_schema.json"),
    )
    parser.add_argument(
        "--model-dir",
        type=Path,
        default=Path("ai/models/flood_xgb_v11_rainfall_repair_stage3"),
    )
    parser.add_argument(
        "--report-dir",
        type=Path,
        default=Path("ai/reports/flood_v11_rainfall_repair_stage3_training"),
    )
    parser.add_argument("--suspect-event-id", default=SUSPECT_EVENT_ID)
    parser.add_argument("--stage1-min-recall", type=float, default=0.95)
    parser.add_argument("--caution-min-recall", type=float, default=0.95)
    parser.add_argument("--danger-min-recall", type=float, default=0.75)
    parser.add_argument("--emergency-min-recall", type=float, default=0.25)
    parser.add_argument("--emergency-max-alert-rate", type=float, default=0.02)
    parser.add_argument("--n-estimators", type=int, default=180)
    parser.add_argument("--stage3-n-estimators", type=int, default=140)
    parser.add_argument("--max-depth", type=int, default=4)
    parser.add_argument("--learning-rate", type=float, default=0.07)
    parser.add_argument("--subsample", type=float, default=0.9)
    parser.add_argument("--colsample-bytree", type=float, default=0.9)
    parser.add_argument("--n-jobs", type=int, default=4)
    return parser.parse_args()


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(data: dict[str, Any], path: Path) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def add_derived_static_features(df: pd.DataFrame) -> None:
    if "mean_elevation" not in df.columns and {"elevation", "relative_elev"}.issubset(df.columns):
        df["mean_elevation"] = df["elevation"] - df["relative_elev"]
    if "relative_low" not in df.columns and "relative_elev" in df.columns:
        df["relative_low"] = np.maximum(-df["relative_elev"], 0)
    if "relative_high" not in df.columns and "relative_elev" in df.columns:
        df["relative_high"] = np.maximum(df["relative_elev"], 0)


def add_v10_interactions(df: pd.DataFrame) -> None:
    df["rainfall_ratio_1h_24h"] = df["rainfall_1h"] / (df["rainfall_24h"] + EPS)
    df["elevation_x_rainfall"] = df["elevation"] * df["idw_rainfall_mm"]
    df["relative_low_x_rainfall"] = df["relative_low"] * df["idw_rainfall_mm"]


def load_dataset(args: argparse.Namespace) -> tuple[pd.DataFrame, dict[str, Any], dict[str, Any]]:
    v11 = pd.read_parquet(args.v11_feature_path)
    static = pd.read_parquet(args.grid_static_runtime)
    schema = read_json(args.v10_schema)
    spec = read_json(args.v11_spec)
    add_derived_static_features(static)
    df = v11.merge(static, on="grid_id", how="inner")
    add_derived_static_features(df)
    add_v10_interactions(df)
    df["label"] = df["is_flooded"].astype("int8")
    return df, schema, spec


def feature_matrix(df: pd.DataFrame, features: list[str]) -> np.ndarray:
    missing = [feature for feature in features if feature not in df.columns]
    if missing:
        raise KeyError(f"Missing required features: {missing}")
    out = df[features].replace([np.inf, -np.inf], np.nan).fillna(0.0)
    return out.to_numpy(dtype="float32")


def make_classifier(args: argparse.Namespace, scale_pos_weight: float, stage: str) -> xgb.XGBClassifier:
    n_estimators = args.stage3_n_estimators if stage == "stage3" else args.n_estimators
    return xgb.XGBClassifier(
        n_estimators=n_estimators,
        max_depth=args.max_depth,
        learning_rate=args.learning_rate,
        subsample=args.subsample,
        colsample_bytree=args.colsample_bytree,
        objective="binary:logistic",
        eval_metric="aucpr",
        tree_method="hist",
        random_state=42,
        n_jobs=args.n_jobs,
        scale_pos_weight=max(scale_pos_weight, 1.0),
        max_delta_step=1,
    )


def scale_pos_weight_for(y: np.ndarray) -> float:
    pos = int(y.sum())
    neg = int(len(y) - pos)
    if pos <= 0:
        return 1.0
    return min(float(neg / pos), 500.0)


def choose_threshold_for_recall(
    y_true: np.ndarray,
    score: np.ndarray,
    min_recall: float,
    prefer_high_precision: bool = True,
) -> tuple[float, dict[str, float]]:
    precision, recall, thresholds = precision_recall_curve(y_true, score)
    candidates: list[tuple[float, float, float]] = []
    for idx, threshold in enumerate(thresholds):
        if recall[idx] >= min_recall:
            candidates.append((float(threshold), float(precision[idx]), float(recall[idx])))
    if not candidates:
        idx = int(np.argmax(recall[:-1])) if len(thresholds) else 0
        threshold = float(thresholds[idx]) if len(thresholds) else 0.0
        selected = (threshold, float(precision[idx]), float(recall[idx]))
    elif prefer_high_precision:
        selected = max(candidates, key=lambda item: (item[1], item[0]))
    else:
        selected = min(candidates, key=lambda item: item[0])
    threshold, selected_precision, selected_recall = selected
    return threshold, {
        "threshold": threshold,
        "precision": selected_precision,
        "recall": selected_recall,
        "min_recall": float(min_recall),
    }


def binary_metrics(y_true: np.ndarray, pred: np.ndarray) -> dict[str, Any]:
    y_true = y_true.astype("int8")
    pred = pred.astype(bool)
    tp = int(((y_true == 1) & pred).sum())
    fp = int(((y_true == 0) & pred).sum())
    fn = int(((y_true == 1) & ~pred).sum())
    tn = int(((y_true == 0) & ~pred).sum())
    return {
        "TP": tp,
        "FP": fp,
        "FN": fn,
        "TN": tn,
        "recall": float(tp / max(tp + fn, 1)),
        "precision": float(tp / max(tp + fp, 1)),
        "alert_rate": float(pred.mean()) if len(pred) else 0.0,
    }


def score_metrics(y_true: np.ndarray, score: np.ndarray) -> dict[str, float]:
    if int(y_true.sum()) <= 0:
        return {"roc_auc": math.nan, "pr_auc": math.nan}
    return {
        "roc_auc": float(roc_auc_score(y_true, score)) if len(np.unique(y_true)) == 2 else math.nan,
        "pr_auc": float(average_precision_score(y_true, score)),
    }


def choose_emergency_threshold(
    y_true: np.ndarray,
    score: np.ndarray,
    min_recall: float,
    max_alert_rate: float,
) -> tuple[float, dict[str, Any]]:
    quantiles = np.unique(np.quantile(score, np.linspace(0.80, 0.9995, 240)))
    candidates: list[dict[str, Any]] = []
    for threshold in quantiles:
        pred = score >= float(threshold)
        metrics = binary_metrics(y_true, pred)
        if metrics["alert_rate"] <= max_alert_rate and metrics["recall"] >= min_recall:
            candidates.append({"threshold": float(threshold), **metrics})
    if not candidates:
        for threshold in quantiles:
            pred = score >= float(threshold)
            metrics = binary_metrics(y_true, pred)
            if metrics["alert_rate"] <= max_alert_rate:
                f05 = (1.25 * metrics["precision"] * metrics["recall"]) / (
                    0.25 * metrics["precision"] + metrics["recall"] + EPS
                )
                candidates.append({"threshold": float(threshold), "f0_5": float(f05), **metrics})
        selected = max(candidates, key=lambda row: (row.get("f0_5", 0.0), row["precision"], row["recall"]))
    else:
        selected = max(candidates, key=lambda row: (row["precision"], row["recall"], row["threshold"]))
    return float(selected["threshold"]), selected


def assign_severity(
    risk_score: np.ndarray,
    stage3_score: np.ndarray,
    thresholds: dict[str, float],
) -> np.ndarray:
    severity = np.zeros(len(risk_score), dtype="int8")
    severity[risk_score >= thresholds["caution"]] = 1
    danger_zone = (risk_score >= thresholds["danger_candidate"]) & (risk_score < thresholds["emergency"])
    severity[danger_zone & (stage3_score >= thresholds["stage3_danger_filter"])] = 2
    severity[risk_score >= thresholds["emergency"]] = 3
    return severity


def level_metrics(y_true: np.ndarray, severity: np.ndarray) -> dict[str, Any]:
    metrics = {
        "caution_or_above": binary_metrics(y_true, severity >= 1),
        "danger_or_above": binary_metrics(y_true, severity >= 2),
        "emergency": binary_metrics(y_true, severity >= 3),
    }
    exact_rows = {}
    for level_id, level_name in RISK_LEVELS.items():
        pred = severity == level_id
        exact_rows[level_name] = {
            "row_count": int(pred.sum()),
            "positive_count": int(((y_true == 1) & pred).sum()),
            "precision_within_level": float(((y_true == 1) & pred).sum() / max(pred.sum(), 1)),
        }
    metrics["exact_level_distribution"] = exact_rows
    return metrics


def event_level_metrics(df: pd.DataFrame, severity: np.ndarray) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    work = df[["event_id", "label"]].copy()
    work["severity"] = severity
    for event_id, group in work.groupby("event_id", sort=True):
        y = group["label"].to_numpy(dtype="int8")
        sev = group["severity"].to_numpy(dtype="int8")
        row: dict[str, Any] = {
            "event_id": event_id,
            "row_count": int(len(group)),
            "positive_count": int(y.sum()),
        }
        for key, pred in {
            "caution_or_above": sev >= 1,
            "danger_or_above": sev >= 2,
            "emergency": sev >= 3,
        }.items():
            m = binary_metrics(y, pred)
            row[f"{key}_recall"] = m["recall"]
            row[f"{key}_precision"] = m["precision"]
            row[f"{key}_alert_rate"] = m["alert_rate"]
            row[f"{key}_TP"] = m["TP"]
            row[f"{key}_FP"] = m["FP"]
        rows.append(row)
    return pd.DataFrame(rows)


def select_stage3_threshold(
    y_true: np.ndarray,
    risk_score: np.ndarray,
    stage3_score: np.ndarray,
    caution: float,
    danger_candidate: float,
    emergency: float,
    min_danger_recall: float,
) -> tuple[float, dict[str, Any], pd.DataFrame]:
    candidate_mask = (risk_score >= danger_candidate) & (risk_score < emergency)
    raw_scores = stage3_score[candidate_mask]
    if len(raw_scores) == 0:
        return 1.0, {"reason": "no_danger_candidates"}, pd.DataFrame()
    thresholds = np.unique(np.quantile(raw_scores, np.linspace(0.0, 0.95, 120)))
    rows: list[dict[str, Any]] = []
    for threshold in thresholds:
        sev = assign_severity(
            risk_score,
            stage3_score,
            {
                "caution": caution,
                "danger_candidate": danger_candidate,
                "emergency": emergency,
                "stage3_danger_filter": float(threshold),
            },
        )
        danger = binary_metrics(y_true, sev >= 2)
        caution_m = binary_metrics(y_true, sev >= 1)
        emergency_m = binary_metrics(y_true, sev >= 3)
        rows.append(
            {
                "stage3_danger_filter": float(threshold),
                "caution_or_above_recall": caution_m["recall"],
                "caution_or_above_precision": caution_m["precision"],
                "danger_or_above_recall": danger["recall"],
                "danger_or_above_precision": danger["precision"],
                "danger_or_above_alert_rate": danger["alert_rate"],
                "emergency_recall": emergency_m["recall"],
                "emergency_precision": emergency_m["precision"],
            }
        )
    sweep = pd.DataFrame(rows)
    passing = sweep[sweep["danger_or_above_recall"] >= min_danger_recall].copy()
    if passing.empty:
        selected = sweep.sort_values(["danger_or_above_recall", "danger_or_above_precision"], ascending=False).iloc[0]
    else:
        selected = passing.sort_values(
            ["danger_or_above_precision", "danger_or_above_recall", "stage3_danger_filter"],
            ascending=False,
        ).iloc[0]
    return float(selected["stage3_danger_filter"]), selected.to_dict(), sweep


def train_stage12_oof(
    args: argparse.Namespace,
    df: pd.DataFrame,
    trusted_mask: np.ndarray,
    suspect_mask: np.ndarray,
    stage1_features: list[str],
    stage2_features: list[str],
) -> tuple[list[TrainedFold], np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    trusted_idx = np.flatnonzero(trusted_mask)
    suspect_idx = np.flatnonzero(suspect_mask)
    events = sorted(df.loc[trusted_idx, "event_id"].unique().tolist())
    stage1_oof = np.zeros(len(df), dtype="float32")
    stage2_oof = np.zeros(len(df), dtype="float32")
    suspect_stage1_parts: list[np.ndarray] = []
    suspect_stage2_parts: list[np.ndarray] = []
    folds: list[TrainedFold] = []

    for event_id in events:
        holdout_mask = trusted_mask & df["event_id"].eq(event_id).to_numpy()
        train_mask = trusted_mask & ~holdout_mask
        y_train = df.loc[train_mask, "label"].to_numpy(dtype="int8")
        y_holdout = df.loc[holdout_mask, "label"].to_numpy(dtype="int8")
        print(f"[stage12] holdout={event_id} train={len(y_train):,} holdout={len(y_holdout):,}")

        stage1 = make_classifier(args, scale_pos_weight_for(y_train), "stage1")
        stage1.fit(feature_matrix(df.loc[train_mask], stage1_features), y_train)
        stage1_oof[holdout_mask] = stage1.predict_proba(feature_matrix(df.loc[holdout_mask], stage1_features))[:, 1]

        stage2 = make_classifier(args, scale_pos_weight_for(y_train), "stage2")
        stage2.fit(feature_matrix(df.loc[train_mask], stage2_features), y_train)
        stage2_oof[holdout_mask] = stage2.predict_proba(feature_matrix(df.loc[holdout_mask], stage2_features))[:, 1]

        if len(suspect_idx):
            suspect_stage1_parts.append(stage1.predict_proba(feature_matrix(df.loc[suspect_mask], stage1_features))[:, 1])
            suspect_stage2_parts.append(stage2.predict_proba(feature_matrix(df.loc[suspect_mask], stage2_features))[:, 1])

        folds.append(TrainedFold(event_id=event_id, stage1=stage1, stage2=stage2))

    suspect_stage1 = np.mean(suspect_stage1_parts, axis=0).astype("float32") if suspect_stage1_parts else np.array([])
    suspect_stage2 = np.mean(suspect_stage2_parts, axis=0).astype("float32") if suspect_stage2_parts else np.array([])
    return folds, stage1_oof, stage2_oof, suspect_stage1, suspect_stage2


def train_stage3_oof(
    args: argparse.Namespace,
    df: pd.DataFrame,
    folds: list[TrainedFold],
    trusted_mask: np.ndarray,
    suspect_mask: np.ndarray,
    risk_score: np.ndarray,
    suspect_risk_score: np.ndarray,
    danger_candidate: float,
    emergency: float,
    stage3_features: list[str],
) -> tuple[np.ndarray, np.ndarray]:
    stage3_oof = np.zeros(len(df), dtype="float32")
    suspect_parts: list[np.ndarray] = []

    df_for_stage3 = df.copy()
    df_for_stage3["risk_score"] = risk_score
    suspect_df = df.loc[suspect_mask].copy()
    if len(suspect_df):
        suspect_df["risk_score"] = suspect_risk_score

    for fold in folds:
        holdout_mask = trusted_mask & df["event_id"].eq(fold.event_id).to_numpy()
        train_mask = trusted_mask & ~holdout_mask
        train_candidate = train_mask & (risk_score >= danger_candidate) & (risk_score < emergency)
        holdout_candidate = holdout_mask & (risk_score >= danger_candidate) & (risk_score < emergency)
        y_train = df.loc[train_candidate, "label"].to_numpy(dtype="int8")
        print(f"[stage3] holdout={fold.event_id} train_candidates={len(y_train):,} holdout_candidates={int(holdout_candidate.sum()):,}")
        if len(y_train) == 0 or len(np.unique(y_train)) < 2:
            continue
        stage3 = make_classifier(args, scale_pos_weight_for(y_train), "stage3")
        stage3.fit(feature_matrix(df_for_stage3.loc[train_candidate], stage3_features), y_train)
        fold.stage3 = stage3
        if holdout_candidate.any():
            stage3_oof[holdout_candidate] = stage3.predict_proba(
                feature_matrix(df_for_stage3.loc[holdout_candidate], stage3_features)
            )[:, 1]
        if len(suspect_df):
            suspect_candidate = (suspect_risk_score >= danger_candidate) & (suspect_risk_score < emergency)
            suspect_scores = np.zeros(len(suspect_df), dtype="float32")
            if suspect_candidate.any():
                suspect_scores[suspect_candidate] = stage3.predict_proba(
                    feature_matrix(suspect_df.loc[suspect_candidate], stage3_features)
                )[:, 1]
            suspect_parts.append(suspect_scores)

    suspect_stage3 = np.mean(suspect_parts, axis=0).astype("float32") if suspect_parts else np.zeros(len(suspect_df), dtype="float32")
    return stage3_oof, suspect_stage3


def save_models(folds: list[TrainedFold], model_dir: Path) -> None:
    model_dir.mkdir(parents=True, exist_ok=True)
    for idx, fold in enumerate(folds):
        fold.stage1.save_model(model_dir / f"stage1_fold_{idx}.ubj")
        fold.stage2.save_model(model_dir / f"stage2_fold_{idx}.ubj")
        if fold.stage3 is not None:
            fold.stage3.save_model(model_dir / f"stage3_fold_{idx}.ubj")


def write_summary(report_dir: Path, selected: dict[str, Any], suspect: dict[str, Any] | None) -> None:
    lines = [
        "# v11 Rainfall Repair Stage3 Training Summary",
        "",
        "v10 staged model structure was preserved. v11 adds event-relative rainfall features to Stage2 and Stage3.",
        "",
        "## Trusted OOF Metrics",
        "",
    ]
    for key, label in [
        ("caution_or_above", "주의 이상"),
        ("danger_or_above", "위험 이상"),
        ("emergency", "긴급"),
    ]:
        metrics = selected["trusted_metrics"][key]
        lines.append(
            f"- {label}: recall `{metrics['recall']:.4f}`, precision `{metrics['precision']:.4f}`, "
            f"alert_rate `{metrics['alert_rate']:.4f}`, TP `{metrics['TP']}`, FP `{metrics['FP']}`, FN `{metrics['FN']}`"
        )
    lines.extend(
        [
            "",
            "## Thresholds",
            "",
            f"- stage1_candidate: `{selected['thresholds']['stage1_candidate']:.10f}`",
            f"- caution: `{selected['thresholds']['caution']:.10f}`",
            f"- danger_candidate: `{selected['thresholds']['danger_candidate']:.10f}`",
            f"- emergency: `{selected['thresholds']['emergency']:.10f}`",
            f"- stage3_danger_filter: `{selected['thresholds']['stage3_danger_filter']:.10f}`",
        ]
    )
    if suspect is not None:
        lines.extend(["", "## Suspect Holdout Metrics", ""])
        for key, label in [
            ("caution_or_above", "주의 이상"),
            ("danger_or_above", "위험 이상"),
            ("emergency", "긴급"),
        ]:
            metrics = suspect[key]
            lines.append(
                f"- {label}: recall `{metrics['recall']:.4f}`, precision `{metrics['precision']:.4f}`, "
                f"alert_rate `{metrics['alert_rate']:.4f}`, TP `{metrics['TP']}`, FP `{metrics['FP']}`, FN `{metrics['FN']}`"
            )
    lines.extend(
        [
            "",
            "## Rebuild",
            "",
            "```bash",
            "cd /Users/kimleewon/Desktop/Project/okayproject",
            "ai/.venv/bin/python ai/scripts/data_quality/train_v11_rainfall_repair_stage3.py",
            "```",
            "",
        ]
    )
    (report_dir / "training_summary.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    args = parse_args()
    args.model_dir.mkdir(parents=True, exist_ok=True)
    args.report_dir.mkdir(parents=True, exist_ok=True)

    df, schema, spec = load_dataset(args)
    trusted_mask = df["event_id"].ne(args.suspect_event_id).to_numpy()
    suspect_mask = df["event_id"].eq(args.suspect_event_id).to_numpy()
    y_trusted = df.loc[trusted_mask, "label"].to_numpy(dtype="int8")

    stage1_features = schema["stage1_features"]
    stage2_features = list(dict.fromkeys(schema["stage2_features"] + spec["recommended_stage2_rainfall_overlay"]))
    stage3_features = list(dict.fromkeys(schema["stage3_features"] + spec["recommended_stage3_rainfall_overlay"]))

    folds, stage1_oof, stage2_oof, suspect_stage1, suspect_stage2 = train_stage12_oof(
        args,
        df,
        trusted_mask,
        suspect_mask,
        stage1_features,
        stage2_features,
    )
    stage1_threshold, stage1_selection = choose_threshold_for_recall(
        y_trusted,
        stage1_oof[trusted_mask],
        args.stage1_min_recall,
    )
    risk_score = np.where(stage1_oof >= stage1_threshold, stage2_oof, 0.0).astype("float32")
    suspect_risk_score = np.where(suspect_stage1 >= stage1_threshold, suspect_stage2, 0.0).astype("float32")

    caution, caution_selection = choose_threshold_for_recall(
        y_trusted,
        risk_score[trusted_mask],
        args.caution_min_recall,
    )
    danger_candidate, danger_selection = choose_threshold_for_recall(
        y_trusted,
        risk_score[trusted_mask],
        args.danger_min_recall,
    )
    emergency, emergency_selection = choose_emergency_threshold(
        y_trusted,
        risk_score[trusted_mask],
        args.emergency_min_recall,
        args.emergency_max_alert_rate,
    )
    if emergency < danger_candidate:
        emergency = float(np.quantile(risk_score[trusted_mask], 0.99))

    stage3_oof, suspect_stage3 = train_stage3_oof(
        args,
        df,
        folds,
        trusted_mask,
        suspect_mask,
        risk_score,
        suspect_risk_score,
        danger_candidate,
        emergency,
        stage3_features,
    )
    stage3_threshold, stage3_selection, stage3_sweep = select_stage3_threshold(
        y_trusted,
        risk_score[trusted_mask],
        stage3_oof[trusted_mask],
        caution,
        danger_candidate,
        emergency,
        args.danger_min_recall,
    )

    thresholds = {
        "caution": float(caution),
        "danger_candidate": float(danger_candidate),
        "emergency": float(emergency),
        "stage1_candidate": float(stage1_threshold),
        "stage3_danger_filter": float(stage3_threshold),
    }
    trusted_severity = assign_severity(risk_score[trusted_mask], stage3_oof[trusted_mask], thresholds)
    trusted_metrics = level_metrics(y_trusted, trusted_severity)

    suspect_metrics = None
    suspect_severity = np.array([], dtype="int8")
    if suspect_mask.any():
        y_suspect = df.loc[suspect_mask, "label"].to_numpy(dtype="int8")
        suspect_severity = assign_severity(suspect_risk_score, suspect_stage3, thresholds)
        suspect_metrics = level_metrics(y_suspect, suspect_severity)

    save_models(folds, args.model_dir)

    trusted_predictions = df.loc[trusted_mask, ["grid_id", "event_id", "label", "flood_overlap_ratio"]].copy()
    trusted_predictions["stage1_score"] = stage1_oof[trusted_mask]
    trusted_predictions["stage2_score"] = stage2_oof[trusted_mask]
    trusted_predictions["risk_score"] = risk_score[trusted_mask]
    trusted_predictions["stage3_score"] = stage3_oof[trusted_mask]
    trusted_predictions["severity"] = trusted_severity
    trusted_predictions["risk_level"] = [RISK_LEVELS[int(level)] for level in trusted_severity]
    trusted_predictions.to_parquet(args.report_dir / "trusted_oof_predictions.parquet", index=False, compression="zstd")

    if suspect_mask.any():
        suspect_predictions = df.loc[suspect_mask, ["grid_id", "event_id", "label", "flood_overlap_ratio"]].copy()
        suspect_predictions["stage1_score"] = suspect_stage1
        suspect_predictions["stage2_score"] = suspect_stage2
        suspect_predictions["risk_score"] = suspect_risk_score
        suspect_predictions["stage3_score"] = suspect_stage3
        suspect_predictions["severity"] = suspect_severity
        suspect_predictions["risk_level"] = [RISK_LEVELS[int(level)] for level in suspect_severity]
        suspect_predictions.to_parquet(args.report_dir / "suspect_holdout_predictions.parquet", index=False, compression="zstd")

    event_metrics = event_level_metrics(df.loc[trusted_mask], trusted_severity)
    event_metrics.to_csv(args.report_dir / "trusted_event_level_metrics.csv", index=False)
    if suspect_mask.any():
        event_level_metrics(df.loc[suspect_mask], suspect_severity).to_csv(
            args.report_dir / "suspect_event_level_metrics.csv",
            index=False,
        )
    stage3_sweep.to_csv(args.report_dir / "stage3_threshold_sweep.csv", index=False)

    selected = {
        "model_version": "flood_xgb_v11_rainfall_repair_stage3",
        "created_at": datetime.now(timezone.utc).astimezone().isoformat(),
        "inherits_model_structure_from": "flood_xgb_v10_stage3_operational",
        "changes_model_structure": False,
        "suspect_event_id": args.suspect_event_id,
        "row_count_trusted": int(trusted_mask.sum()),
        "positive_count_trusted": int(y_trusted.sum()),
        "row_count_suspect": int(suspect_mask.sum()),
        "stage1_features": stage1_features,
        "stage2_features": stage2_features,
        "stage3_features": stage3_features,
        "thresholds": thresholds,
        "threshold_selection": {
            "stage1": stage1_selection,
            "caution": caution_selection,
            "danger_candidate": danger_selection,
            "emergency": emergency_selection,
            "stage3": stage3_selection,
        },
        "score_metrics": {
            "stage1_oof": score_metrics(y_trusted, stage1_oof[trusted_mask]),
            "risk_score_oof": score_metrics(y_trusted, risk_score[trusted_mask]),
        },
        "trusted_metrics": trusted_metrics,
        "suspect_metrics": suspect_metrics,
    }
    write_json(selected, args.report_dir / "metrics.json")
    write_json(
        {
            "model_version": selected["model_version"],
            **thresholds,
            "selection_note": "v11 rainfall repair trained with v10 staged structure; thresholds selected on trusted event OOF only.",
        },
        args.model_dir / "thresholds.json",
    )
    write_json(
        {
            "model_version": selected["model_version"],
            "inherits_model_structure_from": "flood_xgb_v10_stage3_operational",
            "stage1_features": stage1_features,
            "stage2_features": stage2_features,
            "stage3_features": stage3_features,
            "required_runtime_features": sorted(set(stage1_features + stage2_features + stage3_features)),
            "forbidden_runtime_features": schema.get("forbidden_runtime_features", []),
            "suspect_event_policy": {
                args.suspect_event_id: "excluded from training and threshold selection; reported as holdout"
            },
        },
        args.model_dir / "feature_schema.json",
    )
    write_summary(args.report_dir, selected, suspect_metrics)

    print(json.dumps(selected["trusted_metrics"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
