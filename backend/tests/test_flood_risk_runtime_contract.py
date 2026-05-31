from __future__ import annotations

import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def test_flat_rainfall_features_omits_none_optional_fields():
    import backend.main as backend_main

    request = backend_main.FloodRiskPredictRequest(
        latitude=37.5,
        longitude=126.9,
        rainfall_total=10,
        rain_1h_max=5,
        rain_3h_max=None,
        rain_6h_max=None,
        rain_24h_max=None,
    )

    features = backend_main.flat_rainfall_features(request)

    assert features == {
        "rainfall_total": 10,
        "rain_1h_max": 5,
    }


def test_v10_personalization_inputs_is_defined_before_response_use():
    source = (REPO_ROOT / "ai/src/flood_risk/predict_v10_stage3.py").read_text()

    if '"inputs": personalization_inputs' not in source:
        return

    definition_index = source.index("personalization_inputs = {")
    response_use_index = source.index('"inputs": personalization_inputs')
    assert definition_index < response_use_index


def test_v10_defaults_to_nine_folds_per_stage():
    source = (REPO_ROOT / "ai/src/flood_risk/predict_v10_stage3.py").read_text()

    assert "DEFAULT_MAX_FOLDS = 9" in source
    assert "FLOOD_RISK_MAX_FOLDS" in source
    assert "@lru_cache(maxsize=1)" in source


if __name__ == "__main__":
    test_flat_rainfall_features_omits_none_optional_fields()
    test_v10_personalization_inputs_is_defined_before_response_use()
    test_v10_defaults_to_nine_folds_per_stage()
    print("flood risk runtime contract tests passed")
