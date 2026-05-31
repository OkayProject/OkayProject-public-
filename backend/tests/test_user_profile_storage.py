from __future__ import annotations

import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def test_build_user_profile_payload_includes_frequent_places():
    import backend.main as backend_main

    request = backend_main.UserProfileSaveRequest(
        name="테스트",
        address="서울특별시 용산구",
        frequent_places=[
            backend_main.FrequentPlaceRequest(
                name="숙명여대",
                address="서울특별시 용산구 청파동",
                latitude=37.5463,
                longitude=126.9647,
            )
        ],
        has_disability=True,
        disability_type="시각장애",
        notification_methods=["push", "voice"],
    )

    payload = backend_main.build_user_profile_payload(request, user_id=10)

    assert payload["user_id"] == 10
    assert payload["name"] == "테스트"
    assert payload["home_address"] == "서울특별시 용산구"
    assert payload["frequent_places"][0]["name"] == "숙명여대"
    assert payload["notification_methods"] == ["push", "voice"]


def test_save_user_profile_data_falls_back_to_file_storage():
    import backend.main as backend_main

    original_firestore_saver = backend_main.save_user_profile_to_firestore
    original_file_saver = backend_main.save_user_profile_to_file

    def fake_firestore_saver(request):
        raise RuntimeError("firebase unavailable")

    def fake_file_saver(request):
        return {
            "mode": "created",
            "storage": "users_json",
            "user_id": 4,
            "user": {"user_id": 4, "name": request.name},
        }

    backend_main.save_user_profile_to_firestore = fake_firestore_saver
    backend_main.save_user_profile_to_file = fake_file_saver

    try:
        result = backend_main.save_user_profile_data(
            backend_main.UserProfileSaveRequest(name="fallback-user")
        )
    finally:
        backend_main.save_user_profile_to_firestore = original_firestore_saver
        backend_main.save_user_profile_to_file = original_file_saver

    assert result["storage"] == "users_json"
    assert result["user_id"] == 4
    assert result["user"]["name"] == "fallback-user"


def test_build_user_profile_applies_basement_for_current_location():
    import backend.main as backend_main

    original_find_user_by_id = backend_main.find_user_by_id

    def fake_find_user_by_id(user_id):
        return {
            "user_id": user_id,
            "is_semi_basement_resident": True,
            "is_mobility_vulnerable": False,
        }

    backend_main.find_user_by_id = fake_find_user_by_id

    try:
        current_profile = backend_main.build_user_profile(
            user_id=4,
            request_profile=None,
            risk_location_type="current",
        )
        home_profile = backend_main.build_user_profile(
            user_id=4,
            request_profile=None,
            risk_location_type="home",
        )
    finally:
        backend_main.find_user_by_id = original_find_user_by_id

    assert current_profile["is_basement"] is True
    assert current_profile["is_semi_basement_resident"] is True
    assert current_profile["home_environment_applied"] is False
    assert home_profile["is_basement"] is True
    assert home_profile["is_semi_basement_resident"] is True
    assert home_profile["home_environment_applied"] is True


if __name__ == "__main__":
    test_build_user_profile_payload_includes_frequent_places()
    test_save_user_profile_data_falls_back_to_file_storage()
    test_build_user_profile_applies_basement_for_current_location()
    print("user profile storage tests passed")
