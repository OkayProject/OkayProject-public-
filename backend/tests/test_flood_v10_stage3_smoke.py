from __future__ import annotations

import os
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def test_v10_stage3_predictor_returns_operational_response():
    from ai.src.flood_risk.predict_v10_stage3 import predict_flood_risk_v10_stage3

    result = predict_flood_risk_v10_stage3(
        lat=37.5665,
        lon=126.9780,
        rainfall_features={
            "rainfall_total": 300.0,
            "rain_1h_max": 50.0,
            "rain_3h_max": 120.0,
            "rain_6h_max": 180.0,
            "rain_24h_max": 300.0,
        },
    )

    assert result["model_version"] == "flood_xgb_v10_stage3_operational"
    assert result["risk_level"] in {"일반", "주의", "위험", "긴급"}
    assert result["final_risk_level"] == result["risk_level"]
    assert result["personalization"]["applied"] is False
    assert result["personalization"]["included_in_model"] is False
    assert result["risk_score"] == result["personalized_probability"]
    assert result["base_probability"] <= result["personalized_probability"]
    assert "stage3_danger_filter" in result["thresholds"]


def test_v10_stage3_applies_user_profile_score_adjustment():
    from ai.src.flood_risk.predict_v10_stage3 import predict_flood_risk_v10_stage3

    baseline = predict_flood_risk_v10_stage3(
        lat=37.572999,
        lon=126.936280,
        rainfall_features={
            "rainfall_total": 20.0,
            "rain_1h_max": 5.0,
            "rain_3h_max": 10.0,
            "rain_6h_max": 20.0,
            "rain_24h_max": 20.0,
        },
    )
    personalized = predict_flood_risk_v10_stage3(
        lat=37.572999,
        lon=126.936280,
        rainfall_features={
            "rainfall_total": 20.0,
            "rain_1h_max": 5.0,
            "rain_3h_max": 10.0,
            "rain_6h_max": 20.0,
            "rain_24h_max": 20.0,
        },
        user_profile={
            "is_basement": True,
            "is_mobility_limited": True,
            "has_visual_impairment": True,
            "notification_preference": "tts",
        },
    )

    assert personalized["personalization"]["applied"] is True
    assert personalized["personalization"]["included_in_model"] is False
    assert personalized["personalization"]["emergency_guard_applied"] is False
    assert personalized["personalization"]["vulnerability_score"] == 2
    assert personalized["base_probability"] == baseline["base_probability"]
    assert personalized["personalized_probability"] > baseline["personalized_probability"]
    assert "tts" in personalized["recommended_channels"]


def test_v10_stage3_skips_model_when_explicit_rainfall_is_zero():
    import ai.src.flood_risk.predict_v10_stage3 as predictor

    original_predict_mean = predictor.predict_mean
    calls = []

    def fail_if_model_is_called(*args, **kwargs):
        calls.append((args, kwargs))
        raise AssertionError("stage model inference must not run when rainfall is explicitly zero")

    predictor.predict_mean = fail_if_model_is_called
    try:
        result = predictor.predict_flood_risk_v10_stage3(
            lat=37.5665,
            lon=126.9780,
            rainfall_features={
                "rainfall_total": 0.0,
                "rain_1h_max": 0.0,
                "rain_3h_max": 0.0,
                "rain_6h_max": 0.0,
                "rain_24h_max": 0.0,
            },
        )
    finally:
        predictor.predict_mean = original_predict_mean

    assert result["risk_level"] == "일반"
    assert result["stage1_score"] == 0.0
    assert result["stage2_score"] == 0.0
    assert result["base_probability"] == 0.0
    assert calls == []
    assert "강수량 없음" in result["model_notice"]


def test_v10_stage3_skips_personalization_score_adjustment_when_explicit_rainfall_is_zero():
    from ai.src.flood_risk.predict_v10_stage3 import predict_flood_risk_v10_stage3

    result = predict_flood_risk_v10_stage3(
        lat=37.5665,
        lon=126.9780,
        rainfall_features={
            "rainfall_total": 0.0,
            "rain_1h_max": 0.0,
            "rain_3h_max": 0.0,
            "rain_6h_max": 0.0,
            "rain_24h_max": 0.0,
        },
        user_profile={
            "is_basement": True,
            "is_mobility_limited": True,
            "has_visual_impairment": True,
            "notification_preference": "tts",
        },
    )

    assert result["risk_level"] == "일반"
    assert result["base_probability"] == 0.0
    assert result["personalized_probability"] == 0.0
    assert result["risk_score"] == 0.0
    assert result["personalization"]["applied"] is False
    assert result["personalization"]["score_adjustment"] == 0.0
    assert "강수량 없음" in result["personalization"]["message"]


def test_v10_stage3_escalates_danger_to_emergency_for_basement_profile():
    from ai.src.flood_risk.predict_v10_stage3 import apply_personalization

    result = apply_personalization(
        base_score=0.12,
        base_risk_level="위험",
        thresholds={
            "caution": 0.055,
            "danger_candidate": 0.065,
            "emergency": 0.2207685261964798,
        },
        user_profile={"is_basement": True},
        allow_score_adjustment=True,
    )

    assert result["final_risk_level"] == "긴급"
    assert result["personalized_score"] >= 0.2207685261964798
    assert result["emergency_guard_applied"] is True


def test_v10_stage3_treats_tiny_total_without_active_rain_as_normal():
    import ai.src.flood_risk.predict_v10_stage3 as predictor

    original_predict_mean = predictor.predict_mean
    calls = []

    def fail_if_model_is_called(*args, **kwargs):
        calls.append((args, kwargs))
        raise AssertionError("stage model inference must not run for tiny total rainfall without active rain")

    predictor.predict_mean = fail_if_model_is_called
    try:
        result = predictor.predict_flood_risk_v10_stage3(
            lat=37.54535596669542,
            lon=126.96345893781962,
            rainfall_features={
                "rainfall_total": 3.5,
                "rain_1h_max": 0.0,
                "rain_3h_max": 0.0,
                "rain_6h_max": 3.5,
                "rain_24h_max": 3.5,
            },
        )
    finally:
        predictor.predict_mean = original_predict_mean

    assert result["risk_level"] == "일반"
    assert result["stage1_score"] == 0.0
    assert result["stage2_score"] == 0.0
    assert result["base_probability"] == 0.0
    assert calls == []


def test_v10_stage3_keeps_sookmyung_campus_below_caution_after_stage2():
    from ai.src.flood_risk.predict_v10_stage3 import predict_flood_risk_v10_stage3

    result = predict_flood_risk_v10_stage3(
        lat=37.5467,
        lon=126.9647,
        rainfall_features={
            "rainfall_total": 10.0,
            "rain_1h_max": 1.0,
            "rain_3h_max": 3.0,
            "rain_6h_max": 10.0,
            "rain_24h_max": 10.0,
        },
    )

    assert result["stage1_score"] >= result["thresholds"]["stage1_candidate"]
    assert result["stage2_score"] < result["thresholds"]["caution"]
    assert result["risk_level"] == "일반"


def test_v10_stage3_kdtree_grid_lookup_matches_linear_scan():
    import numpy as np

    from ai.src.flood_risk.predict_v10_stage3 import load_v10_model_bundle, nearest_grid_static

    bundle = load_v10_model_bundle()
    samples = [
        (37.5665, 126.9780),
        (37.5446, 126.9647),
        (37.68958, 126.78108),
        (37.4300, 127.1200),
    ]

    grid = bundle.grid_static
    centroid_lat = grid["centroid_lat"].to_numpy(dtype="float64")
    centroid_lon = grid["centroid_lon"].to_numpy(dtype="float64")
    for lat, lon in samples:
        optimized = nearest_grid_static(bundle, lat, lon)
        linear_idx = int(np.nanargmin((centroid_lat - lat) ** 2 + (centroid_lon - lon) ** 2))
        assert optimized["grid_id"] == grid.iloc[linear_idx]["grid_id"]


def test_backend_loader_selects_v10_stage3(monkeypatch):
    monkeypatch.setenv("FLOOD_RISK_MODEL_VERSION", "v10_stage3")

    from backend.main import load_flood_risk_predictors

    predictor = load_flood_risk_predictors()
    assert predictor.__name__ == "predict_flood_risk_v10_stage3"


def test_backend_api_uses_zero_rainfall_fallback_when_provider_is_unconfigured(monkeypatch):
    monkeypatch.delenv("CURRENT_RAINFALL_API_URL", raising=False)

    from fastapi.testclient import TestClient

    from backend.main import app

    response = TestClient(app).post(
        "/api/flood-risk/predict",
        json={
            "latitude": 37.5446,
            "longitude": 126.9647,
            "risk_location_type": "current",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["risk_level"] == "일반"
    assert data["stage1_score"] == 0.0
    assert data["risk_score"] == 0.0
    assert data["rainfall"]["source"] == "rainfall-provider-unconfigured-zero-fallback"


if __name__ == "__main__":
    os.environ["FLOOD_RISK_MODEL_VERSION"] = "v10_stage3"
    test_v10_stage3_predictor_returns_operational_response()
    test_v10_stage3_applies_user_profile_score_adjustment()
    test_v10_stage3_skips_model_when_explicit_rainfall_is_zero()
    test_v10_stage3_skips_personalization_score_adjustment_when_explicit_rainfall_is_zero()
    test_v10_stage3_escalates_danger_to_emergency_for_basement_profile()
    test_v10_stage3_treats_tiny_total_without_active_rain_as_normal()
    test_v10_stage3_keeps_sookmyung_campus_below_caution_after_stage2()
    test_v10_stage3_kdtree_grid_lookup_matches_linear_scan()

    class _MonkeyPatch:
        @staticmethod
        def setenv(key: str, value: str) -> None:
            os.environ[key] = value

        @staticmethod
        def delenv(key: str, raising: bool = True) -> None:
            if key in os.environ:
                del os.environ[key]
            elif raising:
                raise KeyError(key)

    test_backend_loader_selects_v10_stage3(_MonkeyPatch())
    test_backend_api_uses_zero_rainfall_fallback_when_provider_is_unconfigured(_MonkeyPatch())
    print("v10 stage3 smoke tests passed")
