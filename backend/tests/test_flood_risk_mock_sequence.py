from __future__ import annotations

import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def test_mock_flood_risk_sequence_advances_by_interval():
    import backend.main as backend_main

    backend_main.flood_risk_mock_sequence_state.clear()

    request = backend_main.FloodRiskPredictRequest(
        latitude=37.5,
        longitude=126.9,
        mock_risk_levels=["주의", "위험", "긴급"],
        mock_risk_interval_seconds=8,
        mock_risk_sequence_key="expo-go-test",
    )

    first_level, first_meta = backend_main.get_mock_flood_risk_level(request, 37.5, 126.9)
    assert first_level == "주의"
    assert first_meta["current_index"] == 0

    backend_main.flood_risk_mock_sequence_state["expo-go-test"]["updated_at"] -= 8

    second_level, second_meta = backend_main.get_mock_flood_risk_level(request, 37.5, 126.9)
    assert second_level == "위험"
    assert second_meta["current_index"] == 1


def test_mock_flood_risk_sequence_rejects_unknown_level():
    import backend.main as backend_main

    try:
        backend_main.normalize_mock_flood_risk_levels(["관심"])
    except ValueError:
        return

    raise AssertionError("Expected ValueError for unknown mock risk level")


def test_mock_danger_escalates_to_emergency_for_basement_profile():
    from fastapi.testclient import TestClient

    import backend.main as backend_main

    backend_main.flood_risk_mock_sequence_state.clear()
    response = TestClient(backend_main.app).post(
        "/api/flood-risk/predict",
        json={
            "latitude": 37.5599,
            "longitude": 126.9368,
            "risk_location_type": "current",
            "rainfall_features": {
                "rainfall_total": 0.0,
                "rain_1h_max": 0.0,
                "rain_3h_max": 0.0,
                "rain_6h_max": 0.0,
                "rain_24h_max": 0.0,
            },
            "user_profile": {
                "is_semi_basement_resident": True,
            },
            "mock_risk_levels": ["위험"],
            "mock_risk_sequence_key": "basement-demo",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["risk_level"] == "긴급"
    assert data["mock_risk_sequence"]["profile_escalation_applied"] is True


if __name__ == "__main__":
    test_mock_flood_risk_sequence_advances_by_interval()
    test_mock_flood_risk_sequence_rejects_unknown_level()
    test_mock_danger_escalates_to_emergency_for_basement_profile()
    print("flood risk mock sequence tests passed")
