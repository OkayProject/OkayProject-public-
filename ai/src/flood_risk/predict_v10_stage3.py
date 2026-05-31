from __future__ import annotations

import json
import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from scipy.spatial import cKDTree
import xgboost as xgb


MODEL_VERSION = "flood_xgb_v10_stage3_operational"
DATA_VERSION = "flood_dataset_v1"
REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_MODEL_DIR = REPO_ROOT / "ai/models/flood_xgb_v10_stage3_operational"
DEFAULT_GRID_STATIC_PATH = DEFAULT_MODEL_DIR / "grid_static_runtime.parquet"
DEFAULT_MAX_FOLDS = 9
RISK_LEVELS = ("일반", "주의", "위험", "긴급")
RISK_LEVEL_RANK = {level: idx for idx, level in enumerate(RISK_LEVELS)}
FORBIDDEN_RUNTIME_FEATURES = {
    "flood_overlap_ratio",
    "flood_overlap_area",
    "distance_to_flood_trace_m",
    "is_flooded",
    "y",
    "split",
    "event_id",
}

BASEMENT_PROFILE_KEYS = ("is_basement", "lives_in_basement_or_semi_basement", "is_semi_basement_resident")
MOBILITY_PROFILE_KEYS = ("is_mobility_limited", "has_mobility_difficulty", "is_mobility_vulnerable")
VISUAL_PROFILE_KEYS = ("has_visual_impairment",)
DISABILITY_PROFILE_KEYS = ("has_disability",)
RAINFALL_INPUT_KEYS = (
    "rainfall_total",
    "cumulative_rainfall_mm",
    "idw_rainfall_mm",
    "rain_10m_max",
    "rain_1h_max",
    "rainfall_1h",
    "rainfall_1h_max",
    "max_hourly_intensity",
    "rain_3h_max",
    "rainfall_3h",
    "rainfall_3h_max",
    "rain_6h_max",
    "rainfall_6h",
    "rainfall_6h_max",
    "rain_24h_max",
    "rain_24h_total",
    "rainfall_24h",
    "rainfall_24h_total",
)


@dataclass(frozen=True)
class V10ModelBundle:
    model_dir: Path
    thresholds: dict[str, Any]
    feature_schema: dict[str, Any]
    stage1_models: tuple[xgb.Booster, ...]
    stage2_models: tuple[xgb.Booster, ...]
    stage3_models: tuple[xgb.Booster, ...]
    grid_static: pd.DataFrame
    grid_tree: cKDTree
    grid_tree_coordinates: np.ndarray
    max_folds: int


def resolve_model_dir(model_dir: str | Path | None = None) -> Path:
    if model_dir is not None:
        path = Path(model_dir)
    else:
        env_path = os.getenv("FLOOD_RISK_MODEL_DIR", "").strip()
        if env_path:
            path = Path(env_path).expanduser()
        else:
            path = DEFAULT_MODEL_DIR
    if not path.is_absolute():
        path = REPO_ROOT / path
    return path


def resolve_grid_static_path(model_dir: Path, path: str | Path | None = None) -> Path:
    if path is not None:
        grid_path = Path(path)
    else:
        env_path = os.getenv("FLOOD_RISK_GRID_STATIC_PATH", "").strip()
        if env_path:
            grid_path = Path(env_path).expanduser()
        else:
            packaged_grid = model_dir / "grid_static_runtime.parquet"
            grid_path = packaged_grid if packaged_grid.exists() else DEFAULT_GRID_STATIC_PATH
    if not grid_path.is_absolute():
        grid_path = REPO_ROOT / grid_path
    return grid_path


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise RuntimeError(f"v10 model metadata file is missing: {path}")
    with path.open(encoding="utf-8") as file:
        return json.load(file)


def resolve_max_folds() -> int:
    raw_value = os.getenv("FLOOD_RISK_MAX_FOLDS", str(DEFAULT_MAX_FOLDS)).strip()
    try:
        max_folds = int(raw_value)
    except ValueError:
        max_folds = DEFAULT_MAX_FOLDS
    return min(max(max_folds, 1), 9)


def load_boosters(model_dir: Path, prefix: str, max_folds: int) -> tuple[xgb.Booster, ...]:
    models = []
    for fold in range(max_folds):
        path = model_dir / f"{prefix}_fold_{fold}.ubj"
        if not path.exists():
            raise RuntimeError(f"v10 {prefix} artifact is missing: {path}")
        booster = xgb.Booster()
        booster.load_model(path)
        models.append(booster)
    return tuple(models)


def validate_schema(schema: dict[str, Any]) -> None:
    if schema.get("model_version") != MODEL_VERSION:
        raise RuntimeError(
            f"v10 feature_schema model_version mismatch: expected {MODEL_VERSION}, "
            f"got {schema.get('model_version')}"
        )
    missing_sections = [
        key
        for key in ("stage1_features", "stage2_features", "stage3_features", "required_runtime_features")
        if not isinstance(schema.get(key), list)
    ]
    if missing_sections:
        raise RuntimeError(f"v10 feature_schema missing sections: {', '.join(missing_sections)}")
    forbidden = set(schema.get("forbidden_runtime_features", []))
    if not FORBIDDEN_RUNTIME_FEATURES.issubset(forbidden):
        missing = sorted(FORBIDDEN_RUNTIME_FEATURES - forbidden)
        raise RuntimeError(f"v10 feature_schema does not forbid required label/diagnostic fields: {missing}")


@lru_cache(maxsize=1)
def load_v10_model_bundle_cached(model_dir_text: str, grid_static_path_text: str, max_folds: int) -> V10ModelBundle:
    model_dir = Path(model_dir_text)
    grid_static_path = Path(grid_static_path_text)
    thresholds = load_json(model_dir / "thresholds.json")
    feature_schema = load_json(model_dir / "feature_schema.json")
    validate_schema(feature_schema)

    if thresholds.get("model_version") != MODEL_VERSION:
        raise RuntimeError(
            f"v10 thresholds model_version mismatch: expected {MODEL_VERSION}, "
            f"got {thresholds.get('model_version')}"
        )
    if not grid_static_path.exists():
        raise RuntimeError(f"v10 grid_static file is missing: {grid_static_path}")

    grid_static = pd.read_parquet(grid_static_path)
    for column in ("grid_id", "centroid_lat", "centroid_lon"):
        if column not in grid_static.columns:
            raise RuntimeError(f"v10 grid_static is missing required column: {column}")
    grid_tree_coordinates = grid_static[["centroid_lat", "centroid_lon"]].to_numpy(dtype="float64")
    if not np.isfinite(grid_tree_coordinates).all():
        raise RuntimeError("v10 grid_static contains non-finite centroid coordinates")
    grid_tree = cKDTree(grid_tree_coordinates)

    return V10ModelBundle(
        model_dir=model_dir,
        thresholds=thresholds,
        feature_schema=feature_schema,
        stage1_models=load_boosters(model_dir, "stage1", max_folds),
        stage2_models=load_boosters(model_dir, "stage2", max_folds),
        stage3_models=load_boosters(model_dir, "stage3", max_folds),
        grid_static=grid_static,
        grid_tree=grid_tree,
        grid_tree_coordinates=grid_tree_coordinates,
        max_folds=max_folds,
    )


def load_v10_model_bundle(model_dir: str | Path | None = None, grid_static_path: str | Path | None = None) -> V10ModelBundle:
    resolved_model_dir = resolve_model_dir(model_dir)
    resolved_grid_static_path = resolve_grid_static_path(resolved_model_dir, grid_static_path)
    max_folds = resolve_max_folds()
    return load_v10_model_bundle_cached(str(resolved_model_dir), str(resolved_grid_static_path), max_folds)


def nearest_grid_static(bundle: V10ModelBundle, lat: float, lon: float) -> dict[str, Any]:
    _, idx = bundle.grid_tree.query([float(lat), float(lon)], k=1)
    return bundle.grid_static.iloc[int(idx)].to_dict()


def first_numeric(source: dict[str, Any], keys: tuple[str, ...], default: float | None = None) -> float | None:
    for key in keys:
        if key not in source or source[key] is None:
            continue
        try:
            value = float(source[key])
        except (TypeError, ValueError):
            continue
        if np.isfinite(value):
            return max(value, 0.0)
    return default


def has_explicit_zero_rainfall(rainfall_features: dict[str, Any]) -> bool:
    values = []
    for key in RAINFALL_INPUT_KEYS:
        if key not in rainfall_features or rainfall_features[key] is None:
            continue
        try:
            value = float(rainfall_features[key])
        except (TypeError, ValueError):
            continue
        if np.isfinite(value):
            values.append(max(value, 0.0))
    return bool(values) and all(value == 0.0 for value in values)


def has_no_active_rainfall_signal(rainfall_features: dict[str, Any]) -> bool:
    rainfall_total = first_numeric(
        rainfall_features,
        ("rainfall_total", "cumulative_rainfall_mm", "idw_rainfall_mm"),
        0.0,
    ) or 0.0
    rain_1h = first_numeric(
        rainfall_features,
        ("rain_1h_max", "rainfall_1h", "rainfall_1h_max", "max_hourly_intensity"),
        0.0,
    ) or 0.0
    rain_3h = first_numeric(
        rainfall_features,
        ("rain_3h_max", "rainfall_3h", "rainfall_3h_max"),
        0.0,
    ) or 0.0

    return rainfall_total <= 5.0 and rain_1h <= 0.0 and rain_3h <= 0.0


def build_feature_row(lat: float, lon: float, rainfall_features: dict[str, Any], bundle: V10ModelBundle) -> dict[str, float]:
    static = nearest_grid_static(bundle, lat, lon)
    rainfall_total = first_numeric(rainfall_features, ("rainfall_total", "cumulative_rainfall_mm", "idw_rainfall_mm"), 0.0) or 0.0
    rain_1h = first_numeric(rainfall_features, ("rain_1h_max", "rainfall_1h", "rainfall_1h_max", "max_hourly_intensity"), 0.0) or 0.0
    rain_3h = first_numeric(rainfall_features, ("rain_3h_max", "rainfall_3h", "rainfall_3h_max"), None)
    rain_6h = first_numeric(rainfall_features, ("rain_6h_max", "rainfall_6h", "rainfall_6h_max"), None)
    rain_24h = first_numeric(rainfall_features, ("rain_24h_max", "rain_24h_total", "rainfall_24h", "rainfall_24h_total"), None)

    missing_rollups = any(value is None for value in (rain_3h, rain_6h, rain_24h))
    rain_3h = max(rain_3h if rain_3h is not None else rain_1h, rain_1h)
    rain_6h = max(rain_6h if rain_6h is not None else rainfall_total, rain_3h)
    rain_24h = max(rain_24h if rain_24h is not None else rainfall_total, rain_6h)
    cumulative = rainfall_total
    idw = rainfall_total

    elevation = float(static.get("elevation", np.nan))
    relative_elev = float(static.get("relative_elev", np.nan))
    mean_elevation = static.get("mean_elevation")
    if mean_elevation is None or pd.isna(mean_elevation):
        mean_elevation = elevation - relative_elev if np.isfinite(elevation) and np.isfinite(relative_elev) else np.nan
    relative_low = max(-relative_elev, 0.0) if np.isfinite(relative_elev) else np.nan
    relative_high = max(relative_elev, 0.0) if np.isfinite(relative_elev) else np.nan

    row = {
        "grid_id": static.get("grid_id"),
        "centroid_lat": float(static.get("centroid_lat", lat)),
        "centroid_lon": float(static.get("centroid_lon", lon)),
        "elevation": elevation,
        "slope": float(static.get("slope", np.nan)),
        "mean_elevation": float(mean_elevation),
        "relative_low": float(static.get("relative_low", relative_low) if not pd.isna(static.get("relative_low", np.nan)) else relative_low),
        "relative_high": float(static.get("relative_high", relative_high) if not pd.isna(static.get("relative_high", np.nan)) else relative_high),
        "relative_elev": relative_elev,
        "aspect": float(static.get("aspect", np.nan)),
        "curvature": float(static.get("curvature", np.nan)),
        "distance_to_stream": float(static.get("distance_to_stream", np.nan)),
        "idw_rainfall_mm": float(idw),
        "rainfall_1h": float(rain_1h),
        "rainfall_3h": float(rain_3h),
        "rainfall_6h": float(rain_6h),
        "rainfall_24h": float(rain_24h),
        "cumulative_rainfall_mm": float(cumulative),
        "max_hourly_intensity": float(rain_1h),
        "rainfall_missing_flag": float(missing_rollups),
    }
    row["rainfall_ratio_1h_24h"] = row["rainfall_1h"] / (row["rainfall_24h"] + 1e-6)
    row["elevation_x_rainfall"] = row["elevation"] * row["idw_rainfall_mm"]
    row["relative_low_x_rainfall"] = row["relative_low"] * row["idw_rainfall_mm"]
    row["risk_score"] = 0.0
    return row


def predict_mean(models: tuple[xgb.Booster, ...], row: dict[str, float], features: list[str]) -> float:
    missing = [feature for feature in features if feature not in row]
    if missing:
        raise RuntimeError(f"v10 runtime feature construction missed required features: {missing}")
    data = np.asarray([[row.get(feature, np.nan) for feature in features]], dtype="float32")
    values = [float(model.inplace_predict(data, validate_features=False)[0]) for model in models]
    return float(np.mean(values))


def bool_value(value: Any) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "on"}
    return bool(value)


def profile_has_any(profile: dict[str, Any], keys: tuple[str, ...]) -> bool:
    return any(bool_value(profile.get(key, False)) for key in keys)


def vulnerability_summary(user_profile: dict[str, Any] | None) -> dict[str, Any]:
    profile = user_profile or {}
    score = 0
    reasons = []
    is_basement = profile_has_any(profile, BASEMENT_PROFILE_KEYS)
    is_mobility_limited = profile_has_any(profile, MOBILITY_PROFILE_KEYS)
    has_visual_impairment = profile_has_any(profile, VISUAL_PROFILE_KEYS)
    has_disability = profile_has_any(profile, DISABILITY_PROFILE_KEYS) or is_mobility_limited or has_visual_impairment
    generic_disability = has_disability and not is_mobility_limited and not has_visual_impairment

    if is_basement:
        score += 1
        reasons.append("집 기준 반지하/지하 거주 정보가 있어 조기 알림에 보수적으로 반영했습니다.")
    if is_mobility_limited:
        score += 1
        reasons.append("이동에 시간이 더 필요할 수 있어 조기 알림에 보수적으로 반영했습니다.")
    if generic_disability:
        score += 1
        reasons.append("장애 정보가 있어 조기 알림에 보수적으로 반영했습니다.")
    if has_visual_impairment:
        reasons.append("시각 정보 접근 취약성을 고려해 음성 안내 채널을 함께 권장합니다.")

    return {
        "vulnerability_score": score,
        "applied_factors": {
            "is_basement": is_basement,
            "is_mobility_limited": is_mobility_limited,
            "has_visual_impairment": has_visual_impairment,
            "has_disability": has_disability,
        },
        "has_visual_impairment": has_visual_impairment,
        "reasons": reasons,
    }


def personalization_bonus(vulnerability_score: int, thresholds: dict[str, Any]) -> float:
    if vulnerability_score <= 0:
        return 0.0

    caution = float(thresholds["caution"])
    danger = float(thresholds["danger_candidate"])
    step = max(danger - caution, 0.0)
    if vulnerability_score == 1:
        multiplier = 0.10
    else:
        multiplier = 0.20
    return float(step * multiplier)


def level_from_score(score: float, thresholds: dict[str, Any]) -> str:
    if score >= float(thresholds["emergency"]):
        return "긴급"
    if score >= float(thresholds["danger_candidate"]):
        return "위험"
    if score >= float(thresholds["caution"]):
        return "주의"
    return "일반"


def max_risk_level(left: str, right: str) -> str:
    return left if RISK_LEVEL_RANK[left] >= RISK_LEVEL_RANK[right] else right


def apply_personalization(
    *,
    base_score: float,
    base_risk_level: str,
    thresholds: dict[str, Any],
    user_profile: dict[str, Any] | None,
    allow_score_adjustment: bool = True,
) -> dict[str, Any]:
    summary = vulnerability_summary(user_profile)
    vulnerability_score = int(summary["vulnerability_score"])
    bonus = personalization_bonus(vulnerability_score, thresholds) if allow_score_adjustment else 0.0
    personalized_score = min(max(base_score + bonus, base_score), 1.0)
    emergency_guard_applied = False
    reasons = list(summary["reasons"])

    if allow_score_adjustment and base_risk_level == "위험" and summary["applied_factors"]["is_basement"]:
        personalized_score = max(personalized_score, float(thresholds["emergency"]))
        emergency_guard_applied = True
        reasons.append("반지하/지하 거주자는 위험 단계에서 대피 여유 시간이 짧을 수 있어 긴급 단계로 상향했습니다.")

    score_level = level_from_score(personalized_score, thresholds)

    applied = vulnerability_score > 0 and (personalized_score > base_score or emergency_guard_applied)
    final_risk_level = base_risk_level
    if applied and base_risk_level != "일반":
        final_risk_level = max_risk_level(base_risk_level, score_level)

    return {
        "applied": applied,
        "included_in_model": False,
        "vulnerability_score": vulnerability_score,
        "score_adjustment": bonus,
        "base_score": base_score,
        "personalized_score": personalized_score,
        "base_risk_level": base_risk_level,
        "final_risk_level": final_risk_level,
        "applied_factors": summary["applied_factors"],
        "reasons": reasons if applied else [],
        "emergency_guard_applied": emergency_guard_applied,
        "message": (
            "강수량 없음으로 사용자 취약성 점수 보정은 적용하지 않았습니다."
            if not allow_score_adjustment
            else "사용자 취약성 정보는 모델 학습 feature가 아니라 운영 단계의 점수 보정으로만 반영되었습니다."
            if applied
            else "사용자 취약성 정보에 따른 점수 보정은 적용되지 않았습니다."
        ),
    }


def risk_reasons(row: dict[str, float], risk_level: str) -> list[str]:
    reasons = []
    if row.get("rainfall_6h", 0.0) >= 80 or row.get("rainfall_24h", 0.0) >= 120:
        reasons.append("최근 누적 강수량이 높습니다.")
    if row.get("distance_to_stream", np.inf) <= 300:
        reasons.append("하천과 가까운 지역입니다.")
    if row.get("relative_elev", 0.0) <= -3:
        reasons.append("주변보다 상대 고도가 낮은 편입니다.")
    if not reasons:
        if risk_level == "일반":
            reasons.append("현재 입력 기준으로 높은 침수 위험 신호는 제한적입니다.")
        else:
            reasons.append("모델 점수 기준으로 침수 가능성 신호가 확인되었습니다.")
    return reasons


def recommended_channels(risk_level: str, user_profile: dict[str, Any] | None = None) -> list[str]:
    if risk_level == "긴급":
        return ["push", "tts"]
    if risk_level in {"위험", "주의"}:
        channels = ["push"]
        profile = user_profile or {}
        prefers_tts = str(profile.get("notification_preference", "")).lower() in {"tts", "voice"}
        if profile_has_any(profile, ("has_visual_impairment",)) or prefers_tts:
            channels.append("tts")
        return channels
    return []


def predict_flood_risk_v10_stage3(
    *,
    lat: float,
    lon: float,
    rainfall_features: dict[str, Any],
    user_profile: dict[str, Any] | None = None,
    official_alert_active: bool = False,
    model_dir: str | Path | None = None,
) -> dict[str, Any]:

    bundle = load_v10_model_bundle(model_dir=model_dir)
    schema = bundle.feature_schema
    thresholds = bundle.thresholds
    rainfall_features = rainfall_features or {}
    row = build_feature_row(lat, lon, rainfall_features, bundle)

    # No active rainfall skips the model; terrain alone should not open the flood gate.
    no_rainfall = has_explicit_zero_rainfall(rainfall_features) or has_no_active_rainfall_signal(rainfall_features)

    if no_rainfall:
        stage1_score = 0.0
        raw_stage2_score = 0.0
        risk_score = 0.0
    else:
        stage1_score = predict_mean(bundle.stage1_models, row, schema["stage1_features"])
        if stage1_score >= float(thresholds["stage1_candidate"]):
            raw_stage2_score = predict_mean(bundle.stage2_models, row, schema["stage2_features"])
            risk_score = raw_stage2_score
        else:
            raw_stage2_score = 0.0
            risk_score = 0.0
    row["risk_score"] = risk_score

    stage3_score: float | None = None
    if risk_score >= float(thresholds["emergency"]):
        base_risk_level = "긴급"
    elif risk_score >= float(thresholds["danger_candidate"]):
        stage3_score = predict_mean(bundle.stage3_models, row, schema["stage3_features"])
        if stage3_score >= float(thresholds["stage3_danger_filter"]):
            base_risk_level = "위험"
        else:
            base_risk_level = "주의"
    elif risk_score >= float(thresholds["caution"]):
        base_risk_level = "주의"
    else:
        base_risk_level = "일반"

    personalization = apply_personalization(
        base_score=risk_score,
        base_risk_level=base_risk_level,
        thresholds=thresholds,
        user_profile=user_profile,
        allow_score_adjustment=not no_rainfall,
    )
    final_risk_level = str(personalization["final_risk_level"])
    personalized_score = float(personalization["personalized_score"])

    model_reasons = risk_reasons(row, base_risk_level)
    reasons = model_reasons + list(personalization["reasons"])
    threshold_response = {
        "caution": thresholds["caution"],
        "danger": thresholds["danger_candidate"],
        "danger_candidate": thresholds["danger_candidate"],
        "emergency": thresholds["emergency"],
        "stage1_candidate": thresholds["stage1_candidate"],
        "stage3_danger_filter": thresholds["stage3_danger_filter"],
    }
    notice = (
        "EVT_2025_FLOOD는 데이터 품질 의심 이벤트로 학습/임계값 선택에서 제외되고 "
        "suspect holdout으로만 평가되었습니다."
    )
    if no_rainfall:
        notice = "강수량 없음으로 침수 위험 모델 추론을 생략했습니다. " + notice

    return {
        "risk_score": personalized_score,
        "relative_risk_score": personalized_score,
        "base_probability": risk_score,
        "personalized_probability": personalized_score,
        "stage1_score": stage1_score,
        "stage2_score": raw_stage2_score,
        "stage3_danger_filter_score": stage3_score,
        "risk_level": final_risk_level,
        "base_risk_level": base_risk_level,
        "ai_risk_level": base_risk_level,
        "final_risk_level": final_risk_level,
        "thresholds": threshold_response,
        "model_version": MODEL_VERSION,
        "data_version": DATA_VERSION,
        "ensemble_folds_used": bundle.max_folds,
        "grid_id": row.get("grid_id"),
        "nearest_grid": {
            "grid_id": row.get("grid_id"),
            "centroid_lat": row.get("centroid_lat"),
            "centroid_lon": row.get("centroid_lon"),
        },
        "reasons": reasons,
        "model_reasons": model_reasons,
        "recommended_channels": recommended_channels(final_risk_level, user_profile),
        "suspect_event_policy": bundle.feature_schema.get("suspect_event_policy", {}),
        "model_notice": notice,
        "personalization": personalization,
    }


def predict_flood_risk_v10(*args: Any, **kwargs: Any) -> dict[str, Any]:
    return predict_flood_risk_v10_stage3(*args, **kwargs)
