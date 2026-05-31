from __future__ import annotations

import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def test_relevant_missing_persons_include_relevance_score_and_sort_by_it():
    import backend.main as backend_main

    original_get_missing_persons = backend_main.get_missing_persons_with_fallback
    original_calculate_score = backend_main.calculate_missing_person_relevance_score

    def fake_get_missing_persons_with_fallback(page=1, per_page=10):
        return {
            "source": "test",
            "is_fallback": False,
            "fallback_reason": None,
            "missing_persons": [
                {"id": "near-low-score", "name": "가까운 낮은 점수"},
                {"id": "far-high-score", "name": "먼 높은 점수"},
            ],
        }

    def fake_calculate_score(user_latitude, user_longitude, missing_person, reference_locations):
        if missing_person["id"] == "near-low-score":
            return {
                "relevance_score": 10,
                "distance_m": 100,
                "nearest_reference_location": None,
                "reference_distances": [],
            }
        return {
            "relevance_score": 90,
            "distance_m": 1000,
            "nearest_reference_location": None,
            "reference_distances": [],
        }

    backend_main.get_missing_persons_with_fallback = fake_get_missing_persons_with_fallback
    backend_main.calculate_missing_person_relevance_score = fake_calculate_score

    try:
        response = backend_main.get_relevant_missing_persons(
            latitude=37.5,
            longitude=126.9,
            limit=2,
        )
    finally:
        backend_main.get_missing_persons_with_fallback = original_get_missing_persons
        backend_main.calculate_missing_person_relevance_score = original_calculate_score

    assert response.status_code == 200
    body = json.loads(response.body)
    assert body["missing_persons"][0]["id"] == "far-high-score"
    assert body["missing_persons"][0]["relevance_score"] == 90
    assert body["missing_persons"][1]["relevance_score"] == 10


def test_classify_missing_alerts_include_relevance_score():
    import backend.main as backend_main

    original_get_missing_persons = backend_main.get_missing_persons_with_fallback
    original_calculate_score = backend_main.calculate_missing_person_relevance_score

    def fake_get_missing_persons_with_fallback(page=1, per_page=10):
        return {
            "source": "test",
            "is_fallback": False,
            "fallback_reason": None,
            "missing_persons": [{"id": "target", "name": "알림 대상"}],
        }

    def fake_calculate_score(user_latitude, user_longitude, missing_person, reference_locations):
        return {
            "relevance_score": 90,
            "distance_m": 100,
            "nearest_reference_location": None,
            "reference_distances": [],
        }

    backend_main.get_missing_persons_with_fallback = fake_get_missing_persons_with_fallback
    backend_main.calculate_missing_person_relevance_score = fake_calculate_score

    try:
        response = backend_main.classify_missing_alerts(
            latitude=37.5,
            longitude=126.9,
            limit=1,
        )
    finally:
        backend_main.get_missing_persons_with_fallback = original_get_missing_persons
        backend_main.calculate_missing_person_relevance_score = original_calculate_score

    assert response.status_code == 200
    body = json.loads(response.body)
    assert body["alerts"][0]["relevance_score"] == 90


def test_missing_persons_use_firestore_cache_when_police_api_fails():
    import backend.main as backend_main

    original_fetch_police = backend_main.fetch_police_missing_persons
    original_memory_cache = dict(backend_main.safe182_missing_person_cache)
    original_get_firestore_cache = backend_main.get_safe182_firestore_cached_missing_persons
    original_load_fallback = backend_main.load_missing_persons_fallback

    def fake_fetch_police_missing_persons(page=1, per_page=10):
        raise RuntimeError("POLICE_MISSING_API_REQUEST_FAILED")

    def fake_get_safe182_firestore_cached_missing_persons():
        return [{"id": "police-cache-1", "name": "김영수"}]

    def fail_if_fallback_is_used():
        raise AssertionError("missing_persons.json fallback should not be used when Firestore cache exists")

    backend_main.fetch_police_missing_persons = fake_fetch_police_missing_persons
    backend_main.safe182_missing_person_cache["items"] = None
    backend_main.safe182_missing_person_cache["cached_at"] = None
    backend_main.get_safe182_firestore_cached_missing_persons = fake_get_safe182_firestore_cached_missing_persons
    backend_main.load_missing_persons_fallback = fail_if_fallback_is_used

    try:
        result = backend_main.get_missing_persons_with_fallback(page=1, per_page=10)
    finally:
        backend_main.fetch_police_missing_persons = original_fetch_police
        backend_main.safe182_missing_person_cache.update(original_memory_cache)
        backend_main.get_safe182_firestore_cached_missing_persons = original_get_firestore_cache
        backend_main.load_missing_persons_fallback = original_load_fallback

    assert result["source"] == "police_api_firestore_cache"
    assert result["is_fallback"] is False
    assert result["missing_persons"][0]["name"] == "김영수"
    assert result["missing_persons"][0]["data_source"] == "police_api"


if __name__ == "__main__":
    test_relevant_missing_persons_include_relevance_score_and_sort_by_it()
    test_classify_missing_alerts_include_relevance_score()
    test_missing_persons_use_firestore_cache_when_police_api_fails()
    print("missing alert relevance tests passed")
