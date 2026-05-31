from __future__ import annotations

import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def test_current_rainfall_features_are_cached(monkeypatch=None):
    import backend.rainfall_provider as rainfall_provider

    original_cache = dict(rainfall_provider.CURRENT_RAINFALL_CACHE)
    original_fetch = rainfall_provider.fetch_configured_rainfall_payload
    original_ttl = rainfall_provider.rainfall_cache_ttl_seconds
    calls = {"count": 0}

    def fake_fetch_configured_rainfall_payload(*, config, lat, lon):
        calls["count"] += 1
        return {
            "features": {
                "rainfall_total": 12.0,
                "rain_1h_max": 3.0,
            },
            "observed_at": "2026-05-28T00:00:00+09:00",
        }

    rainfall_provider.CURRENT_RAINFALL_CACHE.clear()
    rainfall_provider.fetch_configured_rainfall_payload = fake_fetch_configured_rainfall_payload
    rainfall_provider.rainfall_cache_ttl_seconds = lambda: 180.0

    config = rainfall_provider.RainfallProviderConfig(
        url="https://example.com/rainfall",
        source="test-rainfall",
    )

    try:
        first = rainfall_provider.get_current_rainfall_features(
            lat=37.5457,
            lon=126.9634,
            config=config,
        )
        second = rainfall_provider.get_current_rainfall_features(
            lat=37.54570001,
            lon=126.96340001,
            config=config,
        )
    finally:
        rainfall_provider.fetch_configured_rainfall_payload = original_fetch
        rainfall_provider.rainfall_cache_ttl_seconds = original_ttl
        rainfall_provider.CURRENT_RAINFALL_CACHE.clear()
        rainfall_provider.CURRENT_RAINFALL_CACHE.update(original_cache)

    assert calls["count"] == 1
    assert first.features == second.features


def test_load_rainfall_provider_config_reads_environment():
    import os
    import backend.rainfall_provider as rainfall_provider

    original_url = os.environ.get("CURRENT_RAINFALL_API_URL")
    original_source = os.environ.get("CURRENT_RAINFALL_API_SOURCE")

    os.environ["CURRENT_RAINFALL_API_URL"] = "https://example.com/rainfall"
    os.environ["CURRENT_RAINFALL_API_SOURCE"] = "test-source"

    try:
        config = rainfall_provider.load_rainfall_provider_config()
    finally:
        if original_url is None:
            os.environ.pop("CURRENT_RAINFALL_API_URL", None)
        else:
            os.environ["CURRENT_RAINFALL_API_URL"] = original_url

        if original_source is None:
            os.environ.pop("CURRENT_RAINFALL_API_SOURCE", None)
        else:
            os.environ["CURRENT_RAINFALL_API_SOURCE"] = original_source

    assert config.url == "https://example.com/rainfall"
    assert config.source == "test-source"


if __name__ == "__main__":
    test_current_rainfall_features_are_cached()
    test_load_rainfall_provider_config_reads_environment()
    print("rainfall provider cache tests passed")
