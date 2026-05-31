from __future__ import annotations

import sys
import json
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def test_location_confirm_serializes_firestore_timestamp_like_user():
    import backend.main as backend_main

    original_find_user_by_id = backend_main.find_user_by_id
    original_update_user_location = backend_main.update_user_location

    def fake_find_user_by_id(user_id):
        return {
            "user_id": user_id,
            "address": "서울 용산구 청파로47길 100",
            "updated_at": datetime(2026, 5, 27, 13, 55, tzinfo=timezone.utc),
        }

    def fake_update_user_location(user_id, latitude, longitude, address=None, place_name=None):
        return {
            "user_id": user_id,
            "current_latitude": latitude,
            "current_longitude": longitude,
            "updated_at": datetime(2026, 5, 27, 13, 55, tzinfo=timezone.utc),
        }

    backend_main.find_user_by_id = fake_find_user_by_id
    backend_main.update_user_location = fake_update_user_location

    try:
        response = backend_main.confirm_location(
            backend_main.LocationConfirmRequest(
                user_id=4,
                is_current_location_correct=True,
                latitude=37.54576959891323,
                longitude=126.96347128015695,
                risk_location_type="current",
            )
        )
    finally:
        backend_main.find_user_by_id = original_find_user_by_id
        backend_main.update_user_location = original_update_user_location

    assert response.status_code == 200
    body = json.loads(response.body)
    assert body["location_confirmed"] is True
    assert body["updated_user"]["updated_at"] == "2026-05-27T13:55:00+00:00"
