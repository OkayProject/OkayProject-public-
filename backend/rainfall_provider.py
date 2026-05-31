from __future__ import annotations

import json
import math
import os
import time
from http.client import IncompleteRead
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit, urlunsplit, parse_qsl
from urllib.request import Request, urlopen


RAINFALL_FEATURE_COLUMNS = [
    "rainfall_total",
    "rain_1h_max",
]
OPTIONAL_RAINFALL_FEATURE_COLUMNS = [
    "rain_3h_max",
    "rain_6h_max",
    "rain_24h_max",
]

KST = timezone(timedelta(hours=9))
KMA_DFS_NX = 149
KMA_DFS_NY = 253
KMA_DFS_MISSING = -99.0
KMA_TIME_OBS_DEFAULT_URL = "https://apihub.kma.go.kr/api/typ01/url/kma_sfctm2.php"
KMA_TIME_OBS_DEFAULT_STATION_ID = "108"
KMA_TIME_OBS_SOURCE = "kma-time-observation"
KMA_MISSING_TEXT_VALUES = {"", "-9", "-9.0", "-99", "-99.0"}
FETCH_ATTEMPTS = 2
CURRENT_RAINFALL_CACHE: dict[tuple, tuple[float, CurrentRainfallFeatures]] = {}


@dataclass(frozen=True)
class RainfallProviderConfig:
    url: str
    api_key: str | None = None
    api_key_param: str = "authKey"
    lat_param: str | None = None
    lon_param: str | None = None
    timeout_seconds: float = 5.0
    source: str = "configured-rainfall-api"


@dataclass(frozen=True)
class CurrentRainfallFeatures:
    features: dict[str, float]
    source: str
    observed_at: str | None = None
    raw_provider: str | None = None


@dataclass(frozen=True)
class RawRainfallResponse:
    url: str
    content_type: str | None
    text: str
    parsed_json: dict[str, Any] | None


class RainfallProviderError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def load_rainfall_provider_config() -> RainfallProviderConfig:
    """Load a configurable rainfall API provider.

    The provider is intentionally API-agnostic. Once the team chooses KMA,
    Seoul Open Data, or another source, set CURRENT_RAINFALL_API_URL and map
    that response into the model rainfall features.
    """
    api_key = (
        os.environ.get("CURRENT_RAINFALL_API_KEY", "").strip()
        or os.environ.get("KMA_API_KEY", "").strip()
        or None
    )
    url = os.environ.get("CURRENT_RAINFALL_API_URL", "").strip()
    if not url:
        raise RainfallProviderError(
            "RAINFALL_PROVIDER_UNCONFIGURED",
            "CURRENT_RAINFALL_API_URL 환경변수가 설정되어 있지 않습니다.",
        )
    return RainfallProviderConfig(
        url=url,
        api_key=api_key,
        api_key_param=os.environ.get("CURRENT_RAINFALL_API_KEY_PARAM", "authKey").strip(),
        lat_param=os.environ.get("CURRENT_RAINFALL_API_LAT_PARAM", "").strip() or None,
        lon_param=os.environ.get("CURRENT_RAINFALL_API_LON_PARAM", "").strip() or None,
        timeout_seconds=float(os.environ.get("CURRENT_RAINFALL_API_TIMEOUT_SECONDS", "5")),
        source=os.environ.get("CURRENT_RAINFALL_API_SOURCE", "configured-rainfall-api").strip(),
    )


def rainfall_cache_ttl_seconds() -> float:
    try:
        return max(float(os.environ.get("CURRENT_RAINFALL_CACHE_TTL_SECONDS", "180")), 0.0)
    except ValueError:
        return 180.0


def rainfall_cache_key(config: RainfallProviderConfig, lat: float, lon: float) -> tuple:
    return (
        config.source,
        config.url,
        round(float(lat), 4),
        round(float(lon), 4),
        config.lat_param,
        config.lon_param,
    )


def get_current_rainfall_features(
    *,
    lat: float,
    lon: float,
    config: RainfallProviderConfig | None = None,
) -> CurrentRainfallFeatures:
    """Fetch current rainfall data and normalize it for the AI model.

    Supported response contract for now:

    {
      "features": {
        "rainfall_total": 10.0,
        "rain_10m_max": 1.0,
        "rain_1h_max": 3.0,
        "rain_3h_max": 5.0,
        "rain_6h_max": 8.0,
        "rain_24h_max": 10.0
      },
      "observed_at": "2026-05-09T12:00:00+09:00"
    }

    The fields may also be placed at the top level or under rainfall.features.
    If the chosen API returns a different schema, add a parser here instead of
    changing the AI model contract.
    """
    config = config or load_rainfall_provider_config()
    ttl_seconds = rainfall_cache_ttl_seconds()
    cache_key = rainfall_cache_key(config, lat, lon)
    now = time.time()

    if ttl_seconds > 0:
        cached = CURRENT_RAINFALL_CACHE.get(cache_key)
        if cached is not None:
            cached_at, cached_features = cached
            if now - cached_at <= ttl_seconds:
                return cached_features

    if is_kma_grid_provider(config):
        result = get_kma_combined_rainfall_features(lat=lat, lon=lon, config=config)
    else:
        payload = fetch_configured_rainfall_payload(config=config, lat=lat, lon=lon)
        features = extract_standard_rainfall_features(payload)
        result = CurrentRainfallFeatures(
            features=features,
            source=config.source,
            observed_at=extract_observed_at(payload),
            raw_provider=payload.get("provider") if isinstance(payload, dict) else None,
        )

    if ttl_seconds > 0:
        CURRENT_RAINFALL_CACHE[cache_key] = (now, result)

    return result


def build_kma_time_observation_url(
    *,
    api_key: str,
    station_id: str | None = None,
    observed_at: datetime | None = None,
    base_url: str | None = None,
) -> str:
    """Build a KMA APIHub hourly observation URL for one ASOS station."""
    observed_at = floor_to_previous_hour(observed_at or datetime.now(KST))
    station_id = station_id or os.environ.get("KMA_ASOS_STATION_ID", "").strip() or KMA_TIME_OBS_DEFAULT_STATION_ID
    base_url = base_url or os.environ.get("KMA_TIME_OBS_API_URL", "").strip() or KMA_TIME_OBS_DEFAULT_URL
    split_url = urlsplit(base_url)
    query = dict(parse_qsl(split_url.query, keep_blank_values=True))
    query.update({
        "tm": observed_at.strftime("%Y%m%d%H%M"),
        "stn": station_id,
        "help": "0",
        "authKey": api_key,
    })
    return urlunsplit((
        split_url.scheme,
        split_url.netloc,
        split_url.path,
        urlencode(query),
        split_url.fragment,
    ))


def fetch_kma_time_observation_raw(
    *,
    config: RainfallProviderConfig,
    observed_at: datetime | None = None,
) -> RawRainfallResponse:
    api_key = os.environ.get("KMA_API_KEY", "").strip() or config.api_key
    if not api_key:
        raise RainfallProviderError(
            "RAINFALL_PROVIDER_UNCONFIGURED",
            "KMA_API_KEY 환경변수가 설정되어 있지 않습니다.",
        )

    station_id = os.environ.get("KMA_ASOS_STATION_ID", "").strip() or KMA_TIME_OBS_DEFAULT_STATION_ID
    url = build_kma_time_observation_url(
        api_key=api_key,
        station_id=station_id,
        observed_at=observed_at,
        base_url=os.environ.get("KMA_TIME_OBS_API_URL", "").strip() or KMA_TIME_OBS_DEFAULT_URL,
    )
    request = Request(url, headers={"Accept": "text/plain, */*;q=0.8"})
    last_error: Exception | None = None
    for _ in range(FETCH_ATTEMPTS):
        try:
            with urlopen(request, timeout=config.timeout_seconds) as response:
                response_bytes = response.read()
                content_type = response.headers.get("Content-Type")
            break
        except HTTPError as error:
            raise RainfallProviderError(
                "RAINFALL_API_HTTP_ERROR",
                f"기상청 시간자료 API HTTP 오류: {error.code}",
            ) from error
        except TimeoutError as error:
            last_error = error
        except (URLError, IncompleteRead, ConnectionError) as error:
            last_error = error
    else:
        if isinstance(last_error, TimeoutError):
            raise RainfallProviderError(
                "RAINFALL_API_TIMEOUT",
                "기상청 시간자료 API 응답 시간이 초과되었습니다.",
            ) from last_error
        raise RainfallProviderError(
            "RAINFALL_API_NETWORK_ERROR",
            "기상청 시간자료 API에 연결할 수 없거나 응답을 끝까지 읽지 못했습니다.",
        ) from last_error

    return RawRainfallResponse(
        url=redact_auth_key(url),
        content_type=content_type,
        text=decode_response_body(response_bytes, content_type),
        parsed_json=None,
    )


def parse_kma_time_observation_response(text: str) -> dict[str, str | float | None]:
    """Parse KMA APIHub kma_sfctm2 text response.

    With help=0, the API can return only a data line. In the documented
    kma_sfctm2 order, the rainfall columns are:
    - index 15: RN, hourly rainfall
    - index 16: RN_DAY, daily accumulated rainfall
    - index 18: RN_INT, rainfall intensity

    If help=1 is used while inspecting the API, a commented header line may
    be present; this parser uses that header when available and falls back to
    the fixed positions above.
    """
    header: list[str] | None = None
    data_values: list[str] | None = None
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("="):
            continue
        if line.startswith("#"):
            candidate = line.lstrip("#").strip().split()
            if "YYMMDDHHMI" in candidate and "STN" in candidate:
                header = candidate
            continue
        values = [value.strip() for value in line.split(",")] if "," in line else line.split()
        if values:
            data_values = values
            break

    if not data_values:
        raise RainfallProviderError(
            "RAINFALL_DATA_EMPTY",
            "기상청 시간자료 API 응답에서 관측 데이터 라인을 찾지 못했습니다.",
        )

    by_name: dict[str, str] = {}
    if header and len(header) <= len(data_values):
        by_name = {name: data_values[index] for index, name in enumerate(header)}

    def value_at(name: str, fallback_index: int) -> str | None:
        if name in by_name:
            return by_name[name]
        if len(data_values) > fallback_index:
            return data_values[fallback_index]
        return None

    observed_at = value_at("YYMMDDHHMI", 0)
    station_id = value_at("STN", 1)
    rn_day = parse_kma_rainfall_value(value_at("RN_DAY", 16))
    rn = parse_kma_rainfall_value(value_at("RN", 15))
    rn_int = parse_kma_rainfall_value(value_at("RN_INT", 18))
    return {
        "rainfall_total": rn_day if rn_day is not None else rn if rn is not None else 0.0,
        "rainfall_1h": rn if rn is not None else 0.0,
        "rainfall_intensity": rn_int if rn_int is not None else 0.0,
        "source": KMA_TIME_OBS_SOURCE,
        "station_id": station_id,
        "observed_at": observed_at,
        "raw_rn_day": rn_day,
        "raw_rn": rn,
        "raw_rn_int": rn_int,
    }


def parse_kma_rainfall_value(value: str | None) -> float | None:
    if value is None:
        return None
    text = str(value).strip()
    if text in KMA_MISSING_TEXT_VALUES:
        return None
    try:
        parsed = float(text)
    except ValueError:
        return None
    if parsed < 0:
        return None
    return parsed


def fetch_kma_time_observation_rainfall(
    *,
    config: RainfallProviderConfig,
    observed_at: datetime | None = None,
) -> CurrentRainfallFeatures:
    raw = fetch_kma_time_observation_raw(config=config, observed_at=observed_at)
    parsed = parse_kma_time_observation_response(raw.text)
    rainfall_total = float(parsed["rainfall_total"] or 0.0)
    rainfall_1h = float(parsed["rainfall_1h"] or 0.0)
    features = {
        "rainfall_total": rainfall_total,
        "rain_10m_max": float(rainfall_1h / 6.0),
        "rain_1h_max": rainfall_1h,
        "rain_3h_max": rainfall_1h,
        "rain_6h_max": rainfall_total,
        "rain_24h_max": rainfall_total,
        "rainfall_1h": rainfall_1h,
        "rainfall_intensity": float(parsed["rainfall_intensity"] or 0.0),
    }
    return CurrentRainfallFeatures(
        features=features,
        source=KMA_TIME_OBS_SOURCE,
        observed_at=str(parsed["observed_at"]) if parsed["observed_at"] else None,
        raw_provider=f"kma-time-observation:stn={parsed['station_id'] or KMA_TIME_OBS_DEFAULT_STATION_ID}",
    )


def get_kma_combined_rainfall_features(
    *,
    lat: float,
    lon: float,
    config: RainfallProviderConfig,
) -> CurrentRainfallFeatures:
    """Use the original grid API for rain_1h_max and hourly ASOS API for rainfall_total."""
    grid = get_kma_grid_latest_rainfall_features(lat=lat, lon=lon, config=config)
    features = dict(grid.features)
    source_parts = [grid.source]
    raw_parts = [grid.raw_provider] if grid.raw_provider else []
    observed_at = grid.observed_at

    try:
        time_observation = fetch_kma_time_observation_rainfall(config=config)
    except RainfallProviderError:
        time_observation = None

    if time_observation is not None:
        features["rainfall_total"] = float(time_observation.features["rainfall_total"])
        features["rain_6h_max"] = float(time_observation.features.get("rain_6h_max", features["rainfall_total"]))
        features["rain_24h_max"] = float(time_observation.features.get("rain_24h_max", features["rainfall_total"]))
        features["rainfall_intensity"] = float(time_observation.features.get("rainfall_intensity", 0.0))
        source_parts.append(time_observation.source)
        if time_observation.raw_provider:
            raw_parts.append(time_observation.raw_provider)
        observed_at = time_observation.observed_at or observed_at

    return CurrentRainfallFeatures(
        features=features,
        source="+".join(source_parts),
        observed_at=observed_at,
        raw_provider="+".join(raw_parts) if raw_parts else None,
    )


def fetch_configured_rainfall_payload(
    *,
    config: RainfallProviderConfig,
    lat: float,
    lon: float,
) -> dict[str, Any]:
    raw = fetch_configured_rainfall_raw(config=config, lat=lat, lon=lon)
    if raw.parsed_json is not None:
        return raw.parsed_json

    raise RainfallProviderError(
        "RAINFALL_API_SCHEMA_UNSUPPORTED",
        "강수량 API 응답이 JSON이 아닙니다. 선택한 API에 맞는 parser를 추가해야 합니다.",
    )


def fetch_configured_rainfall_raw(
    *,
    config: RainfallProviderConfig,
    lat: float,
    lon: float,
    query_overrides: dict[str, str] | None = None,
) -> RawRainfallResponse:
    url = build_configured_url(
        config=config,
        lat=lat,
        lon=lon,
        query_overrides=query_overrides,
    )
    request = Request(url, headers={"Accept": "application/json, text/plain;q=0.9, */*;q=0.8"})
    last_error: Exception | None = None
    for _ in range(FETCH_ATTEMPTS):
        try:
            with urlopen(request, timeout=config.timeout_seconds) as response:
                response_bytes = response.read()
                content_type = response.headers.get("Content-Type")
            break
        except HTTPError as error:
            raise RainfallProviderError(
                "RAINFALL_API_HTTP_ERROR",
                f"강수량 API HTTP 오류: {error.code}",
            ) from error
        except TimeoutError as error:
            last_error = error
        except (URLError, IncompleteRead, ConnectionError) as error:
            last_error = error
    else:
        if isinstance(last_error, TimeoutError):
            raise RainfallProviderError(
                "RAINFALL_API_TIMEOUT",
                "강수량 API 응답 시간이 초과되었습니다.",
            ) from last_error
        raise RainfallProviderError(
            "RAINFALL_API_NETWORK_ERROR",
            "강수량 API에 연결할 수 없거나 응답을 끝까지 읽지 못했습니다.",
        ) from last_error

    body = decode_response_body(response_bytes, content_type)

    try:
        parsed = json.loads(body)
    except json.JSONDecodeError:
        parsed = None

    if parsed is not None and not isinstance(parsed, dict):
        raise RainfallProviderError(
            "RAINFALL_API_SCHEMA_UNSUPPORTED",
            "강수량 API 응답 최상위 타입이 object가 아닙니다.",
        )
    return RawRainfallResponse(
        url=redact_auth_key(url),
        content_type=content_type,
        text=body,
        parsed_json=parsed,
    )


def build_configured_url(
    *,
    config: RainfallProviderConfig,
    lat: float,
    lon: float,
    query_overrides: dict[str, str] | None = None,
) -> str:
    split_url = urlsplit(config.url)
    query = dict(parse_qsl(split_url.query, keep_blank_values=True))
    query.update(query_overrides or {})

    if config.api_key:
        query[config.api_key_param] = config.api_key
    if config.lat_param:
        query[config.lat_param] = str(lat)
    if config.lon_param:
        query[config.lon_param] = str(lon)

    return urlunsplit((
        split_url.scheme,
        split_url.netloc,
        split_url.path,
        urlencode(query),
        split_url.fragment,
    ))


def is_kma_grid_provider(config: RainfallProviderConfig) -> bool:
    path = urlsplit(config.url).path
    return (
        "apihub.kma.go.kr" in urlsplit(config.url).netloc
        and (
            path.endswith("nph-dfs_vsrt_grd")
            or path.endswith("nph-dfs_odam_grd")
        )
    )


def is_kma_forecast_provider(config: RainfallProviderConfig) -> bool:
    return urlsplit(config.url).path.endswith("nph-dfs_vsrt_grd")


def kma_observed_config_from_forecast(config: RainfallProviderConfig) -> RainfallProviderConfig:
    split_url = urlsplit(config.url)
    observed_path = split_url.path.removesuffix("nph-dfs_vsrt_grd") + "nph-dfs_odam_grd"
    observed_url = urlunsplit((
        split_url.scheme,
        split_url.netloc,
        observed_path,
        split_url.query,
        split_url.fragment,
    ))
    return RainfallProviderConfig(
        url=observed_url,
        api_key=config.api_key,
        api_key_param=config.api_key_param,
        lat_param=config.lat_param,
        lon_param=config.lon_param,
        timeout_seconds=config.timeout_seconds,
        source=f"{config.source}:observed-fallback",
    )


def get_kma_grid_rainfall_features(
    *,
    lat: float,
    lon: float,
    config: RainfallProviderConfig,
) -> CurrentRainfallFeatures:
    mode = "observed" if urlsplit(config.url).path.endswith("nph-dfs_odam_grd") else "forecast"
    grid_x, grid_y = lat_lon_to_kma_grid(lat=lat, lon=lon)
    requests = kma_rn1_query_sequence(config=config, mode=mode)
    hourly_values = []
    observed_times = []

    for query in requests:
        raw = fetch_configured_rainfall_raw(
            config=config,
            lat=lat,
            lon=lon,
            query_overrides=query,
        )
        value = extract_kma_grid_value(raw.text, grid_x=grid_x, grid_y=grid_y)
        if value is None:
            continue
        hourly_values.append(value)
        observed_times.append(query.get("tmef") or query.get("tmfc"))

    if not hourly_values:
        raise RainfallProviderError(
            "RAINFALL_DATA_EMPTY",
            "KMA RN1 격자에서 현재 위치의 유효 강수량 값을 찾지 못했습니다.",
        )

    features = aggregate_hourly_rainfall_features(hourly_values)
    return CurrentRainfallFeatures(
        features=features,
        source=f"{config.source}:{mode}:RN1",
        observed_at=max(observed_times) if observed_times else None,
        raw_provider=f"kma-grid-{mode}:x={grid_x}:y={grid_y}:hours={len(hourly_values)}",
    )


def get_kma_grid_latest_rainfall_features(
    *,
    lat: float,
    lon: float,
    config: RainfallProviderConfig,
) -> CurrentRainfallFeatures:
    mode = "observed" if urlsplit(config.url).path.endswith("nph-dfs_odam_grd") else "forecast"
    try:
        return fetch_kma_grid_latest_rainfall_features(lat=lat, lon=lon, config=config, mode=mode)
    except RainfallProviderError as error:
        if error.code != "RAINFALL_DATA_EMPTY" or not is_kma_forecast_provider(config):
            raise
        observed_config = kma_observed_config_from_forecast(config)
        return fetch_kma_grid_latest_rainfall_features(
            lat=lat,
            lon=lon,
            config=observed_config,
            mode="observed",
        )


def fetch_kma_grid_latest_rainfall_features(
    *,
    lat: float,
    lon: float,
    config: RainfallProviderConfig,
    mode: str,
) -> CurrentRainfallFeatures:
    grid_x, grid_y = lat_lon_to_kma_grid(lat=lat, lon=lon)
    for query in kma_rn1_query_sequence(config=config, mode=mode):
        raw = fetch_configured_rainfall_raw(
            config=config,
            lat=lat,
            lon=lon,
            query_overrides=query,
        )
        value = extract_kma_grid_value(raw.text, grid_x=grid_x, grid_y=grid_y)
        if value is None:
            continue
        rain_1h = float(value)
        return CurrentRainfallFeatures(
            features={
                "rainfall_total": rain_1h,
                "rain_10m_max": float(rain_1h / 6.0),
                "rain_1h_max": rain_1h,
                "rain_3h_max": rain_1h,
                "rain_6h_max": rain_1h,
                "rain_24h_max": rain_1h,
            },
            source=f"{config.source}:{mode}:RN1",
            observed_at=query.get("tmef") or query.get("tmfc"),
            raw_provider=f"kma-grid-{mode}:x={grid_x}:y={grid_y}:latest",
        )

    raise RainfallProviderError(
        "RAINFALL_DATA_EMPTY",
        "KMA RN1 격자에서 현재 위치의 유효 강수량 값을 찾지 못했습니다.",
    )


def kma_rn1_query_sequence(
    *,
    config: RainfallProviderConfig,
    mode: str,
    now: datetime | None = None,
) -> list[dict[str, str]]:
    now = now or datetime.now(KST)
    base_time = floor_to_previous_10_minutes(now)
    queries = []
    if mode == "forecast":
        base_times = [
            base_time - timedelta(minutes=10 * step)
            for step in range(0, 7)
        ]
        queries.extend([
            {
                "tmfc": forecast_base.strftime("%Y%m%d%H%M"),
                "tmef": (forecast_base + timedelta(hours=hour)).strftime("%Y%m%d%H"),
                "vars": "RN1",
            }
            for forecast_base in base_times
            for hour in range(1, 7)
        ])
        queries.extend(configured_kma_rn1_queries(config=config, mode=mode))
        return dedupe_queries(queries)

    queries.extend([
        {
            "tmfc": (base_time - timedelta(hours=hour)).strftime("%Y%m%d%H%M"),
            "vars": "RN1",
        }
        for hour in range(24)
    ])
    queries.extend(configured_kma_rn1_queries(config=config, mode=mode))
    return dedupe_queries(queries)


def configured_kma_rn1_queries(
    *,
    config: RainfallProviderConfig,
    mode: str,
) -> list[dict[str, str]]:
    query = dict(parse_qsl(urlsplit(config.url).query, keep_blank_values=True))
    if "tmfc" not in query:
        return []
    if mode == "forecast" and "tmef" not in query:
        return []
    return [{**query, "vars": "RN1"}]


def dedupe_queries(queries: list[dict[str, str]]) -> list[dict[str, str]]:
    seen = set()
    deduped = []
    for query in queries:
        key = tuple(sorted(query.items()))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(query)
    return deduped


def floor_to_previous_10_minutes(value: datetime) -> datetime:
    if value.tzinfo is None:
        value = value.replace(tzinfo=KST)
    value = value.astimezone(KST)
    minute = (value.minute // 10) * 10
    return value.replace(minute=minute, second=0, microsecond=0)


def floor_to_previous_hour(value: datetime) -> datetime:
    if value.tzinfo is None:
        value = value.replace(tzinfo=KST)
    value = value.astimezone(KST)
    return value.replace(minute=0, second=0, microsecond=0)


def parse_kma_grid_values(text: str) -> list[float]:
    values = []
    for token in text.replace(",", " ").split():
        try:
            values.append(float(token))
        except ValueError:
            continue

    expected_count = KMA_DFS_NX * KMA_DFS_NY
    if len(values) != expected_count:
        raise RainfallProviderError(
            "RAINFALL_API_SCHEMA_UNSUPPORTED",
            f"KMA 격자 값 개수가 예상과 다릅니다: expected={expected_count}, actual={len(values)}",
        )
    return values


def extract_kma_grid_value(text: str, *, grid_x: int, grid_y: int) -> float | None:
    if not (1 <= grid_x <= KMA_DFS_NX and 1 <= grid_y <= KMA_DFS_NY):
        raise RainfallProviderError(
            "LOCATION_OUT_OF_RANGE",
            f"KMA 격자 범위를 벗어난 위치입니다: x={grid_x}, y={grid_y}",
        )

    values = parse_kma_grid_values(text)
    index = (grid_y - 1) * KMA_DFS_NX + (grid_x - 1)
    value = values[index]
    if value == KMA_DFS_MISSING:
        return None
    return max(float(value), 0.0)


def aggregate_hourly_rainfall_features(hourly_values: list[float]) -> dict[str, float]:
    rain_1h_max = max(hourly_values)
    return {
        "rainfall_total": float(sum(hourly_values)),
        "rain_10m_max": float(rain_1h_max / 6.0),
        "rain_1h_max": float(rain_1h_max),
        "rain_3h_max": rolling_sum_max(hourly_values, 3),
        "rain_6h_max": rolling_sum_max(hourly_values, 6),
        "rain_24h_max": rolling_sum_max(hourly_values, 24),
    }


def rolling_sum_max(values: list[float], window_size: int) -> float:
    if not values:
        return 0.0
    bounded_window = min(window_size, len(values))
    return float(
        max(
            sum(values[index : index + bounded_window])
            for index in range(0, len(values) - bounded_window + 1)
        )
    )


def lat_lon_to_kma_grid(*, lat: float, lon: float) -> tuple[int, int]:
    re = 6371.00877
    grid = 5.0
    slat1 = 30.0
    slat2 = 60.0
    olon = 126.0
    olat = 38.0
    xo = 43
    yo = 136

    degrad = math.pi / 180.0
    re_grid = re / grid
    slat1_rad = slat1 * degrad
    slat2_rad = slat2 * degrad
    olon_rad = olon * degrad
    olat_rad = olat * degrad

    sn = math.tan(math.pi * 0.25 + slat2_rad * 0.5) / math.tan(math.pi * 0.25 + slat1_rad * 0.5)
    sn = math.log(math.cos(slat1_rad) / math.cos(slat2_rad)) / math.log(sn)
    sf = math.tan(math.pi * 0.25 + slat1_rad * 0.5)
    sf = (sf**sn) * math.cos(slat1_rad) / sn
    ro = math.tan(math.pi * 0.25 + olat_rad * 0.5)
    ro = re_grid * sf / (ro**sn)

    ra = math.tan(math.pi * 0.25 + float(lat) * degrad * 0.5)
    ra = re_grid * sf / (ra**sn)
    theta = float(lon) * degrad - olon_rad
    if theta > math.pi:
        theta -= 2.0 * math.pi
    if theta < -math.pi:
        theta += 2.0 * math.pi
    theta *= sn

    grid_x = int(math.floor(ra * math.sin(theta) + xo + 0.5))
    grid_y = int(math.floor(ro - ra * math.cos(theta) + yo + 0.5))
    return grid_x, grid_y


def extract_standard_rainfall_features(payload: dict[str, Any]) -> dict[str, float]:
    feature_source = payload
    if isinstance(payload.get("features"), dict):
        feature_source = payload["features"]
    elif isinstance(payload.get("rainfall"), dict) and isinstance(payload["rainfall"].get("features"), dict):
        feature_source = payload["rainfall"]["features"]

    missing = [column for column in RAINFALL_FEATURE_COLUMNS if column not in feature_source]
    if missing:
        raise RainfallProviderError(
            "RAINFALL_FEATURES_REQUIRED",
            "강수량 API 응답에서 모델 입력 강수 피처를 찾을 수 없습니다: "
            + ", ".join(missing),
        )

    features = {}
    for column in [*RAINFALL_FEATURE_COLUMNS, *OPTIONAL_RAINFALL_FEATURE_COLUMNS]:
        if column not in feature_source:
            continue
        try:
            value = float(feature_source[column])
        except (TypeError, ValueError) as error:
            raise RainfallProviderError(
                "RAINFALL_FEATURES_INVALID",
                f"{column} 값이 숫자가 아닙니다.",
            ) from error
        if value < 0:
            raise RainfallProviderError(
                "RAINFALL_FEATURES_INVALID",
                f"{column} 값은 0 이상이어야 합니다.",
            )
        features[column] = value
    return features


def extract_observed_at(payload: dict[str, Any]) -> str | None:
    if isinstance(payload.get("rainfall"), dict):
        observed_at = payload["rainfall"].get("observed_at")
        if observed_at:
            return str(observed_at)
    observed_at = payload.get("observed_at")
    return str(observed_at) if observed_at else None


def decode_response_body(response_bytes: bytes, content_type: str | None) -> str:
    encodings = []
    if content_type and "charset=" in content_type.lower():
        encodings.append(content_type.split("charset=", 1)[1].split(";")[0].strip())
    encodings.extend(["utf-8", "euc-kr", "cp949"])

    tried = set()
    for encoding in encodings:
        if not encoding or encoding in tried:
            continue
        tried.add(encoding)
        try:
            return response_bytes.decode(encoding)
        except UnicodeDecodeError:
            continue
    return response_bytes.decode("utf-8", errors="replace")


def redact_auth_key(url: str) -> str:
    split_url = urlsplit(url)
    query = []
    for key, value in parse_qsl(split_url.query, keep_blank_values=True):
        if key.lower() in {"authkey", "apikey", "api_key", "servicekey", "service_key"}:
            query.append((key, "***"))
        else:
            query.append((key, value))
    return urlunsplit((
        split_url.scheme,
        split_url.netloc,
        split_url.path,
        urlencode(query),
        split_url.fragment,
    ))
