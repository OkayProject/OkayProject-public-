from fastapi import FastAPI
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from math import radians, sin, cos, sqrt, atan2
from pathlib import Path
import sys
import json
import os
import time
import uuid
import base64
import mimetypes
from datetime import datetime, timezone, timedelta
import re
import urllib.parse
import urllib.request
import urllib.error
import xml.etree.ElementTree as ET
try:
    import firebase_admin
    from firebase_admin import credentials, firestore
except ModuleNotFoundError:
    firebase_admin = None
    credentials = None
    firestore = None


BACKEND_DIR = Path(__file__).resolve().parent
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.append(str(REPO_ROOT))

GENERATED_IMAGE_DIR = BACKEND_DIR / "generated"
GENERATED_IMAGE_DIR.mkdir(parents=True, exist_ok=True)

REFERENCE_IMAGE_PROMPT_VERSION = "white_bg_large_person_v2"
MAX_FIRESTORE_REFERENCE_IMAGE_BYTES = 650_000


SAFE182_CACHE_TTL_SECONDS = 60 * 10
safe182_missing_person_cache = {
    "items": None,
    "cached_at": None,
}

firebase_firestore_client = None


def get_firestore_client():
    """
    Firebase Admin SDK를 초기화하고 Firestore client를 반환합니다.
    Render 환경변수 FIREBASE_SERVICE_ACCOUNT_JSON에 서비스 계정 JSON 전체 내용을 저장해 사용합니다.
    """
    global firebase_firestore_client

    if firebase_firestore_client is not None:
        return firebase_firestore_client

    if firebase_admin is None or credentials is None or firestore is None:
        raise RuntimeError("FIREBASE_ADMIN_NOT_INSTALLED")

    service_account_json = os.getenv("FIREBASE_SERVICE_ACCOUNT_JSON")

    if not service_account_json:
        raise RuntimeError("FIREBASE_SERVICE_ACCOUNT_JSON_MISSING")

    try:
        service_account_info = json.loads(service_account_json)
    except json.JSONDecodeError as error:
        raise RuntimeError("FIREBASE_SERVICE_ACCOUNT_JSON_INVALID") from error

    if not firebase_admin._apps:
        credential = credentials.Certificate(service_account_info)
        firebase_admin.initialize_app(credential)

    firebase_firestore_client = firestore.client()
    return firebase_firestore_client


def get_reference_image_collection():
    """
    실종자 AI 참고 이미지 생성 결과를 저장하는 Firestore collection을 반환합니다.
    """
    return get_firestore_client().collection("missing_person_reference_images")

def get_push_token_collection():
    """
    사용자 Expo Push Token을 저장하는 Firestore collection을 반환합니다.
    """
    return get_firestore_client().collection("user_push_tokens")


def get_user_collection():
    """
    사용자 프로필을 저장하는 Firestore collection을 반환합니다.
    """
    return get_firestore_client().collection("users")


def get_missing_person_api_cache_collection():
    """
    Safe182 API 호출 성공 결과를 저장하는 Firestore collection을 반환합니다.
    Render 재배포로 메모리 캐시가 사라져도 마지막 성공 데이터를 재사용하기 위해 사용합니다.
    """
    return get_firestore_client().collection("missing_person_api_cache")




def is_generated_image_url_available(reference_image_url: str | None) -> bool:
    """
    Firestore 캐시 URL이 /generated 로컬 파일을 가리키는 경우 실제 파일이 존재하는지 확인합니다.
    Render 재배포/재시작으로 파일이 사라졌으면 db_cached를 무시합니다.
    """
    if not reference_image_url:
        return False

    parsed_url = urllib.parse.urlparse(reference_image_url)
    image_path = parsed_url.path or reference_image_url

    if not image_path.startswith("/generated/"):
        return True

    filename = Path(urllib.parse.unquote(image_path)).name
    return (GENERATED_IMAGE_DIR / filename).exists()


def generated_image_filename_from_url(reference_image_url: str | None) -> str | None:
    if not reference_image_url:
        return None

    parsed_url = urllib.parse.urlparse(reference_image_url)
    image_path = parsed_url.path or reference_image_url

    if not image_path.startswith("/generated/"):
        return None

    return Path(urllib.parse.unquote(image_path)).name


def build_reference_image_blob_fields(image_bytes: bytes | None, mime_type: str | None) -> dict:
    if not image_bytes:
        return {
            "image_blob_saved": False,
            "image_blob_reason": "IMAGE_BYTES_EMPTY",
        }

    if len(image_bytes) > MAX_FIRESTORE_REFERENCE_IMAGE_BYTES:
        return {
            "image_blob_saved": False,
            "image_blob_reason": "IMAGE_TOO_LARGE_FOR_FIRESTORE_CACHE",
            "image_size_bytes": len(image_bytes),
        }

    return {
        "image_blob_saved": True,
        "image_blob_base64": base64.b64encode(image_bytes).decode("utf-8"),
        "image_mime_type": mime_type or "image/png",
        "image_size_bytes": len(image_bytes),
    }


def restore_generated_image_from_record(record: dict) -> bool:
    """
    Render 재배포로 /generated 로컬 파일이 사라진 경우,
    Firestore에 저장된 이미지 blob으로 같은 파일을 복원합니다.
    """
    filename = generated_image_filename_from_url(record.get("reference_image_url"))
    image_base64 = record.get("image_blob_base64")

    if not filename or not image_base64:
        return False

    image_path = GENERATED_IMAGE_DIR / filename
    if image_path.exists():
        return True

    try:
        image_path.write_bytes(base64.b64decode(str(image_base64), validate=False))
        return True
    except Exception:
        return False


def get_reference_image_record(missing_person_id: str):
    """
    missing_person_id 기준으로 Firestore에 저장된 AI 참고 이미지 생성 결과를 조회합니다.
    성공한 AI 이미지가 있고 prompt_version과 실제 파일이 유효할 때만 재사용합니다.
    """
    document = get_reference_image_collection().document(str(missing_person_id)).get()

    if not document.exists:
        return None

    record = document.to_dict()

    if record.get("status") != "success":
        return None

    if record.get("prompt_version") != REFERENCE_IMAGE_PROMPT_VERSION:
        return None

    reference_image_url = record.get("reference_image_url")
    if not reference_image_url:
        return None

    if not is_generated_image_url_available(reference_image_url):
        if not restore_generated_image_from_record(record):
            return None

    return record


def save_reference_image_record(
    missing_person_id: str,
    reference_image_url: str | None,
    status: str,
    is_ai_generated: bool,
    notice: str,
    image_generation_method: str,
    error_code: str | None = None,
    message: str | None = None,
    source: str | None = None,
    is_fallback: bool = False,
    fallback_reason: str | None = None,
    visual_prompt: str | None = None,
    prompt_version: str = REFERENCE_IMAGE_PROMPT_VERSION,
    source_image_attached: bool = False,
    image_bytes: bytes | None = None,
    mime_type: str | None = None,
):
    """
    AI 참고 이미지 생성 성공/실패 결과를 Firestore에 저장합니다.
    document id는 missing_person_id를 사용하며, 같은 id가 있으면 최신 상태로 갱신합니다.
    """
    document_ref = get_reference_image_collection().document(str(missing_person_id))
    existing_document = document_ref.get()

    record = {
        "missing_person_id": str(missing_person_id),
        "reference_image_url": reference_image_url,
        "status": status,
        "is_ai_generated": is_ai_generated,
        "notice": notice,
        "image_generation_method": image_generation_method,
        "error_code": error_code,
        "message": message,
        "source": source,
        "is_fallback": is_fallback,
        "fallback_reason": fallback_reason,
        "visual_prompt": visual_prompt,
        "prompt_version": prompt_version,
        "source_image_attached": source_image_attached,
        "updated_at": firestore.SERVER_TIMESTAMP,
        **build_reference_image_blob_fields(image_bytes, mime_type),
    }

    if not existing_document.exists:
        record["created_at"] = firestore.SERVER_TIMESTAMP

    document_ref.set(record, merge=True)

def get_safe182_cached_missing_persons():
    """
    최근 Safe182 API 호출 성공 결과가 있으면 캐시 데이터를 반환합니다.
    캐시 유효 시간은 SAFE182_CACHE_TTL_SECONDS 기준입니다.
    """
    cached_items = safe182_missing_person_cache.get("items")
    cached_at = safe182_missing_person_cache.get("cached_at")

    if cached_items is None or cached_at is None:
        return None

    if time.time() - cached_at > SAFE182_CACHE_TTL_SECONDS:
        return None

    return cached_items


def set_safe182_cached_missing_persons(items: list[dict]):
    """
    Safe182 API 호출 성공 결과를 메모리에 저장합니다.
    """
    safe182_missing_person_cache["items"] = items
    safe182_missing_person_cache["cached_at"] = time.time()


def get_safe182_firestore_cached_missing_persons():
    """
    Firestore에 저장된 마지막 Safe182 API 성공 결과를 반환합니다.
    Firestore 설정이 없거나 캐시가 없으면 None을 반환해 로컬 fallback으로 이어지게 합니다.
    """
    try:
        document = get_missing_person_api_cache_collection().document("latest").get()
    except Exception:
        return None

    if not getattr(document, "exists", False):
        return None

    record = document.to_dict() or {}
    items = record.get("items")
    if not isinstance(items, list) or not items:
        return None

    return items


def save_safe182_firestore_cached_missing_persons(items: list[dict]):
    """
    Safe182 API 호출 성공 결과를 Firestore에 저장합니다.
    저장 실패가 실종자 API 응답 실패로 이어지지 않도록 예외는 삼킵니다.
    """
    try:
        get_missing_person_api_cache_collection().document("latest").set(
            {
                "source": "police_api",
                "items": jsonable_encoder(items),
                "count": len(items),
                "updated_at": firestore.SERVER_TIMESTAMP,
            },
            merge=True,
        )
    except Exception:
        return

from backend.rainfall_provider import (
    CurrentRainfallFeatures,
    RAINFALL_FEATURE_COLUMNS,
    RainfallProviderError,
    extract_standard_rainfall_features,
    fetch_configured_rainfall_raw,
    get_current_rainfall_features,
    load_rainfall_provider_config,
)

app = FastAPI()


DEFAULT_CORS_ORIGINS = [
    "http://localhost:8081",
    "http://localhost:19006",
    "http://127.0.0.1:8081",
    "http://127.0.0.1:19006",
    "https://okayproject.onrender.com",
]
configured_cors_origins = [
    origin.strip()
    for origin in os.getenv("CORS_ALLOW_ORIGINS", "").split(",")
    if origin.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=[*DEFAULT_CORS_ORIGINS, *configured_cors_origins],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.mount("/generated", StaticFiles(directory=str(GENERATED_IMAGE_DIR)), name="generated")

class DisasterRiskRequest(BaseModel):
    user_id: int
    latitude: float
    longitude: float

# ----- Location Update Request Model -----
class LocationUpdateRequest(BaseModel):
    user_id: int
    latitude: float
    longitude: float
    address: str | None = None
    place_name: str | None = None


class LocationConfirmRequest(BaseModel):
    user_id: int
    is_current_location_correct: bool
    latitude: float
    longitude: float
    risk_location_type: str | None = None


class LocationCheckRequest(BaseModel):
    user_id: int
    latitude: float
    longitude: float


class FrequentPlaceRequest(BaseModel):
    name: str
    address: str | None = None
    latitude: float | None = None
    longitude: float | None = None


class UserProfileSaveRequest(BaseModel):
    user_id: int | None = None
    name: str
    phone: str | None = None
    address: str | None = None
    home_latitude: float | None = None
    home_longitude: float | None = None
    home_address: str | None = None
    frequent_places: list[FrequentPlaceRequest] = []
    has_disability: bool = False
    disability_type: str | None = None
    is_mobility_vulnerable: bool = False
    is_semi_basement_resident: bool = False
    notification_enabled: bool = True
    notification_methods: list[str] = []

def load_flood_risk_predictors():
    model_version = (
        os.getenv("FLOOD_RISK_MODEL_VERSION", "")
        or os.getenv("FLOOD_RISK_MODEL_NAME", "")
        or "v10_stage3"
    ).strip().lower()
    model_dir = os.getenv("FLOOD_RISK_MODEL_DIR", "").strip()
    if model_version in {"v10", "v10_stage3", "flood_xgb_v10_stage3_operational"} or "flood_xgb_v10_stage3_operational" in model_dir:
        try:
            from ai.src.flood_risk.predict_v10_stage3 import predict_flood_risk_v10_stage3

            return predict_flood_risk_v10_stage3
        except ImportError as error:
            raise RuntimeError(
                "AI v10 Stage3 inference module could not be imported. "
                "Render must deploy from the repository root and include ai/src/flood_risk/predict_v10_stage3.py."
            ) from error

    if model_version not in {"v9", "legacy_v9", "flood_xgb_v9"}:
        raise RuntimeError(f"Unsupported FLOOD_RISK_MODEL_VERSION: {model_version}")

    try:
        from ai.src.flood_risk.predict_v9 import predict_flood_risk_v9

        return predict_flood_risk_v9
    except ImportError as error:
        raise RuntimeError(
            "AI inference module could not be imported. "
            "Render must deploy from the repository root, not the backend directory."
        ) from error

class UserProfileRequest(BaseModel):
    lives_in_basement_or_semi_basement: bool = False
    has_mobility_difficulty: bool = False
    uses_wheelchair_or_walking_aid: bool = False
    needs_guardian_support: bool = False
    frequently_uses_underground_space: bool = False
    is_with_child_or_elderly: bool = False
    is_basement: bool = False
    is_mobility_limited: bool = False
    is_semi_basement_resident: bool = False
    is_mobility_vulnerable: bool = False
    has_visual_impairment: bool = False
    has_disability: bool = False
    disability_type: str | None = None
    notification_preference: str = "push"

class FloodRiskPredictRequest(BaseModel):
    lat: float | None = None
    lon: float | None = None
    latitude: float | None = None
    longitude: float | None = None
    user_id: int | None = None
    risk_location_type: str | None = None
    user_profile: UserProfileRequest | None = None
    rainfall_features: dict[str, float] | None = None
    rainfall_total: float | None = None
    rain_10m_max: float | None = None
    rain_1h_max: float | None = None
    rain_3h_max: float | None = None
    rain_6h_max: float | None = None
    rain_24h_max: float | None = None
    official_alert_active: bool = False
    mock_risk_levels: list[str] | None = None
    mock_risk_interval_seconds: int = 8
    mock_risk_sequence_key: str | None = None


# ----- Gemini Disaster Action Guide API -----
class NearestShelterRequest(BaseModel):
    name: str | None = None
    distance_m: int | None = None
    address: str | None = None

class ActionGuideRequest(BaseModel):
    user_id: int | None = None
    risk_level: str
    risk_score: float | None = None
    reasons: list[str] = []
    nearest_shelter: NearestShelterRequest | None = None
    user_profile: dict | None = None


class AlertPayloadPreviewRequest(BaseModel):
    user_id: int | None = None
    expo_push_token: str | None = None
    type: str
    risk_level: str | None = None
    title: str
    body: str
    meta: str | None = None


class PushTokenRegistrationRequest(BaseModel):
    user_id: int
    expo_push_token: str


class SendTestNotificationRequest(BaseModel):
    user_id: int | None = None
    expo_push_token: str | None = None
    type: str
    risk_level: str | None = None
    title: str
    body: str
    meta: str | None = None
# ---- Push Alert Payload Preview Helper Functions ----
KST = timezone(timedelta(hours=9))
EXPO_PUSH_SEND_URL = "https://exp.host/--/api/v2/push/send"


def normalize_push_alert_type(alert_type: str) -> str:
    normalized_type = str(alert_type or "").strip().lower()
    if normalized_type not in {"flood", "missing"}:
        raise ValueError("INVALID_ALERT_TYPE")
    return normalized_type


def normalize_push_risk_level(alert_type: str, risk_level: str | None) -> str | None:
    normalized_type = normalize_push_alert_type(alert_type)
    if normalized_type == "missing":
        return None

    level = str(risk_level or "").strip().lower()
    mapping = {
        "주의": "caution",
        "caution": "caution",
        "위험": "danger",
        "danger": "danger",
        "긴급": "emergency",
        "emergency": "emergency",
    }

    normalized_level = mapping.get(level)
    if normalized_level is None:
        raise ValueError("INVALID_RISK_LEVEL")

    return normalized_level


def is_valid_expo_push_token(expo_push_token: str | None) -> bool:
    token = str(expo_push_token or "").strip()
    return (
        token.startswith("ExponentPushToken[")
        or token.startswith("ExpoPushToken[")
    ) and token.endswith("]")


def create_push_alert_payload(
    *,
    expo_push_token: str | None,
    user_id: int | None,
    alert_type: str,
    risk_level: str | None,
    title: str,
    body: str,
    meta: str | None = None,
):
    normalized_type = normalize_push_alert_type(alert_type)
    normalized_risk_level = normalize_push_risk_level(normalized_type, risk_level)
    created_at_datetime = datetime.now(KST)
    created_at = created_at_datetime.isoformat(timespec="milliseconds")
    timestamp_ms = created_at_datetime.strftime("%Y%m%d%H%M%S%f")[:-3]
    unique_suffix = uuid.uuid4().hex[:8]
    target_id = user_id if user_id is not None else "anonymous"
    alert_id = f"{normalized_type}-{target_id}-{timestamp_ms}-{unique_suffix}"

    return {
        "to": expo_push_token,
        "sound": "default",
        "channelId": "alerts",
        "title": title,
        "body": body,
        "data": {
            "id": alert_id,
            "type": normalized_type,
            "risk_level": normalized_risk_level,
            "meta": meta or "",
            "created_at": created_at,
        },
    }


def save_user_expo_push_token(user_id: int, expo_push_token: str):
    """
    Expo Push Token을 Firestore에 저장합니다.
    로컬 Firebase 설정이 없으면 users.json에 fallback 저장합니다.
    """
    user_data = find_user_by_id(user_id)
    if user_data is None:
        return None

    try:
        get_push_token_collection().document(str(user_id)).set(
            {
                "user_id": int(user_id),
                "expo_push_token": expo_push_token,
                "updated_at": firestore.SERVER_TIMESTAMP,
            },
            merge=True,
        )
        return {
            **user_data,
            "expo_push_token": expo_push_token,
            "push_token_storage": "firestore",
        }
    except RuntimeError:
        pass

    users = load_json("data/users.json")

    for user in users:
        if int(user.get("user_id")) == int(user_id):
            user["expo_push_token"] = expo_push_token
            user["expo_push_token_updated_at"] = datetime.now(KST).isoformat(timespec="milliseconds")
            save_json("data/users.json", users)
            return {
                **user,
                "push_token_storage": "users_json",
            }

    return None


def get_user_expo_push_token(user_id: int | None) -> str | None:
    if user_id is None:
        return None

    try:
        document = get_push_token_collection().document(str(user_id)).get()
        if document.exists:
            token = document.to_dict().get("expo_push_token")
            if token:
                return token
    except RuntimeError:
        pass

    user_data = find_user_by_id(user_id)
    if user_data is None:
        return None

    return user_data.get("expo_push_token")


def send_expo_push_notification(payload: dict):
    request_data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        EXPO_PUSH_SEND_URL,
        data=request_data,
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            response_text = response.read().decode("utf-8")
    except urllib.error.HTTPError as error:
        error_text = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"EXPO_PUSH_HTTP_ERROR: {error.code}: {error_text}") from error
    except urllib.error.URLError as error:
        raise RuntimeError(f"EXPO_PUSH_REQUEST_FAILED: {error}") from error

    try:
        return json.loads(response_text)
    except json.JSONDecodeError as error:
        raise RuntimeError("EXPO_PUSH_RESPONSE_INVALID_JSON") from error


class MissingAlertClassifyRequest(BaseModel):
    user_id: int | None = None
    latitude: float | None = None
    longitude: float | None = None
    limit: int = 10
    max_distance_m: int | None = None
    frequent_places: list | dict | str | None = None


def load_json(path: str):
    """
    JSON 파일을 읽어서 파이썬 데이터로 바꿔주는 함수입니다.
    예: data/shelters.json 파일을 읽어서 리스트 형태로 반환합니다.
    """
    json_path = Path(path)
    if not json_path.is_absolute():
        json_path = BACKEND_DIR / json_path

    with open(json_path, "r", encoding="utf-8") as file:
        return json.load(file)

# ----- Save JSON Helper Function -----
def save_json(path: str, data):
    """
    파이썬 데이터를 JSON 파일로 저장합니다.
    사용자 위치 재조정 결과를 users.json에 반영할 때 사용합니다.
    """
    json_path = Path(path)
    if not json_path.is_absolute():
        json_path = BACKEND_DIR / json_path

    with open(json_path, "w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=2)


def calculate_distance_m(lat1: float, lon1: float, lat2: float, lon2: float) -> int:
    """
    두 지점의 위도/경도를 받아서 두 지점 사이의 거리를 미터 단위로 계산합니다.

    lat1, lon1: 사용자 현재 위치
    lat2, lon2: 대피소 위치
    """
    earth_radius = 6371000

    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)

    a = (
        sin(dlat / 2) ** 2
        + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    )

    c = 2 * atan2(sqrt(a), sqrt(1 - a))
    distance = earth_radius * c

    return round(distance)

def create_kakao_map_url(name: str, latitude: float, longitude: float) -> str:
    """
    대피소 이름과 좌표를 이용해 카카오맵에서 대피소 위치를 여는 URL을 생성합니다.
    """
    encoded_name = urllib.parse.quote(name)
    return f"https://map.kakao.com/link/to/{encoded_name},{latitude},{longitude}"


def create_kakao_walk_route_url(
    start_name: str,
    start_latitude: float,
    start_longitude: float,
    end_name: str,
    end_latitude: float,
    end_longitude: float,
) -> str:
    """
    사용자 현재 위치를 출발지로, 대피소를 도착지로 설정한 카카오맵 도보 길찾기 URL을 생성합니다.
    """
    encoded_start_name = urllib.parse.quote(start_name)
    encoded_end_name = urllib.parse.quote(end_name)
    return (
        "https://map.kakao.com/link/by/walk/"
        f"{encoded_start_name},{start_latitude},{start_longitude}/"
        f"{encoded_end_name},{end_latitude},{end_longitude}"
    )

def get_shelter_status_text(is_open: bool) -> str:
    """
    대피소 운영 여부를 화면에 표시할 문구로 변환합니다.
    """
    if is_open:
        return "개방중"
    return "운영 종료"


def find_user_by_id(user_id: int):
    """
    Firestore users collection에서 user_id에 해당하는 사용자 정보를 찾습니다.
    Firebase 설정이 없거나 조회에 실패하면 users.json을 fallback으로 사용합니다.
    """
    try:
        document = get_user_collection().document(str(user_id)).get()
        if document.exists:
            user_data = document.to_dict() or {}
            user_data["user_id"] = int(user_data.get("user_id", user_id))
            return user_data
    except Exception:
        pass

    users = load_json("data/users.json")

    for user in users:
        if int(user.get("user_id")) == int(user_id):
            return user

    return None


def build_user_profile_payload(request: UserProfileSaveRequest, user_id: int) -> dict:
    frequent_places = [
        {
            "name": place.name,
            "address": place.address,
            "latitude": place.latitude,
            "longitude": place.longitude,
        }
        for place in request.frequent_places
    ]

    return {
        "user_id": int(user_id),
        "name": request.name,
        "phone": request.phone,
        "address": request.address,
        "home_latitude": request.home_latitude,
        "home_longitude": request.home_longitude,
        "home_address": request.home_address or request.address,
        "frequent_places": frequent_places,
        "has_disability": request.has_disability,
        "disability_type": request.disability_type,
        "is_mobility_vulnerable": request.is_mobility_vulnerable,
        "is_semi_basement_resident": request.is_semi_basement_resident,
        "notification_enabled": request.notification_enabled,
        "notification_methods": request.notification_methods,
    }


def get_next_user_id_from_file(users: list[dict]) -> int:
    existing_ids = [
        int(user.get("user_id"))
        for user in users
        if user.get("user_id") is not None
    ]
    return max(existing_ids, default=0) + 1


def get_next_user_id_from_firestore() -> int:
    max_user_id = 0

    try:
        query = (
            get_user_collection()
            .order_by("user_id", direction=firestore.Query.DESCENDING)
            .limit(1)
        )
        for document in query.stream():
            user_data = document.to_dict() or {}
            max_user_id = max(max_user_id, int(user_data.get("user_id", 0)))
    except Exception:
        pass

    try:
        users = load_json("data/users.json")
        max_user_id = max(max_user_id, get_next_user_id_from_file(users) - 1)
    except Exception:
        pass

    return max_user_id + 1


def save_user_profile_to_firestore(request: UserProfileSaveRequest):
    """
    초기 사용자 정보 입력값을 Firestore users collection에 저장합니다.
    user_id가 있으면 기존 사용자 정보를 업데이트하고, 없으면 새 user_id를 생성합니다.
    """
    if request.user_id is None:
        user_id = get_next_user_id_from_firestore()
        mode = "created"
    else:
        user_id = int(request.user_id)
        mode = "updated" if find_user_by_id(user_id) is not None else "created"

    saved_user = build_user_profile_payload(request, user_id)
    document_ref = get_user_collection().document(str(user_id))
    document_ref.set(
        {
            **saved_user,
            "updated_at": firestore.SERVER_TIMESTAMP,
            **({"created_at": firestore.SERVER_TIMESTAMP} if mode == "created" else {}),
        },
        merge=True,
    )

    return {
        "mode": mode,
        "storage": "firestore",
        "user_id": user_id,
        "user": saved_user,
    }


def save_user_profile_to_file(request: UserProfileSaveRequest):
    """
    초기 사용자 정보 입력값을 users.json에 저장합니다.
    user_id가 있으면 기존 사용자 정보를 업데이트하고, 없으면 새 user_id를 생성합니다.
    """
    users = load_json("data/users.json")
    mode = "created"
    target_index = None

    if request.user_id is not None:
        for index, user in enumerate(users):
            if int(user.get("user_id")) == int(request.user_id):
                target_index = index
                mode = "updated"
                break

    if target_index is None and request.user_id is None:
        user_id = get_next_user_id_from_file(users)
    else:
        user_id = int(request.user_id)

    saved_user = build_user_profile_payload(request, user_id)

    if target_index is None:
        users.append(saved_user)
    else:
        users[target_index] = {
            **users[target_index],
            **saved_user,
        }

    save_json("data/users.json", users)

    return {
        "mode": mode,
        "storage": "users_json",
        "user_id": user_id,
        "user": saved_user,
    }


def save_user_profile_data(request: UserProfileSaveRequest):
    try:
        return save_user_profile_to_firestore(request)
    except Exception:
        return save_user_profile_to_file(request)

# ----- Update User Location Helper Function -----
def update_user_location(user_id: int, latitude: float, longitude: float, address: str | None = None, place_name: str | None = None):
    """
    Firestore users collection에서 user_id에 해당하는 사용자의 현재 위치 정보를 수정합니다.
    Firebase 설정이 없거나 대상 사용자가 없으면 users.json을 fallback으로 사용합니다.
    위치 재조정 화면에서 사용자가 선택한 좌표와 주소를 저장하는 데 사용합니다.
    """
    location_update = {
        "current_latitude": latitude,
        "current_longitude": longitude,
        "latitude": latitude,
        "longitude": longitude,
    }

    if address is not None:
        location_update["current_address"] = address
        location_update["address"] = address

    if place_name is not None:
        location_update["current_place_name"] = place_name

    try:
        document_ref = get_user_collection().document(str(user_id))
        document = document_ref.get()
        if document.exists:
            document_ref.set(
                {
                    **location_update,
                    "updated_at": firestore.SERVER_TIMESTAMP,
                },
                merge=True,
            )
            updated_user = document.to_dict() or {}
            updated_user.update(location_update)
            updated_user["user_id"] = int(updated_user.get("user_id", user_id))
            updated_user["profile_storage"] = "firestore"
            return updated_user
    except Exception:
        pass

    users = load_json("data/users.json")

    for user in users:
        if int(user.get("user_id")) == int(user_id):
            user.update(location_update)
            user["profile_storage"] = "users_json"

            save_json("data/users.json", users)
            return user

    return None


def get_user_display_location(user_data: dict | None) -> str:
    """
    위치 확인 배너에 표시할 사용자 위치 문구를 만듭니다.
    """
    if not user_data:
        return "현재 위치"

    for key in ("current_address", "address", "current_place_name", "place_name"):
        value = user_data.get(key)
        if value:
            return str(value)

    latitude = user_data.get("current_latitude") or user_data.get("latitude")
    longitude = user_data.get("current_longitude") or user_data.get("longitude")
    if latitude is not None and longitude is not None:
        return f"현재 위치 ({float(latitude):.4f}, {float(longitude):.4f})"

    return "현재 위치"


def get_text_value(data: dict, candidate_keys: list[str], default=None):
    """
    외부 API 응답에서 여러 후보 key 중 값이 존재하는 첫 번째 값을 반환합니다.
    경찰청 API 응답 필드명이 달라질 수 있어 변환 과정에서 사용합니다.
    """
    for key in candidate_keys:
        value = data.get(key)
        if value not in (None, ""):
            return value
    return default


def normalize_missing_person(raw_item: dict, index: int):
    """
    경찰청 실종자 API 응답 또는 fallback 데이터를 우리 서비스에서 사용하는 실종자 형식으로 변환합니다.
    실제 경찰청 API 필드명은 응답 확인 후 candidate_keys에 추가 보완할 수 있습니다.
    """
    missing_person_id = get_text_value(
        raw_item,
        ["id", "missing_person_id", "sn", "rnum", "msspsnId"],
        index + 1
    )

    name = get_text_value(
        raw_item,
        ["name", "nm", "msspsnNm", "missing_person_name"],
        "이름 미상"
    )

    age = get_text_value(
        raw_item,
        ["age", "ageNow", "msspsnAge", "ageText"],
        None
    )

    gender = get_text_value(
        raw_item,
        ["gender", "sex", "sexdstn", "sexdstnDscd", "msspsnSex", "sexCd"],
        "성별 미상"
    )

    last_seen_location = get_text_value(
        raw_item,
        ["last_seen_location", "occrAdres", "occrPlace", "missing_location", "place"],
        "마지막 목격 위치 정보 없음"
    )

    appearance_description = get_text_value(
        raw_item,
        ["appearance_description", "alldressingDscd", "wearing", "feature", "etcSpfeatr"],
        "착의 및 외형 정보 없음"
    )

    description = get_text_value(
        raw_item,
        ["description", "detail", "alshCn", "content"],
        appearance_description
    )

    image_url = get_text_value(
        raw_item,
        ["image_url", "photo", "photoUrl", "imgUrl", "tknphotoFile", "file1", "file2"],
        None
    )

    return {
        "id": missing_person_id,
        "stable_id": str(missing_person_id),
        "data_source": None,
        "name": name,
        "age": age,
        "missing_age": get_text_value(raw_item, ["missing_age", "age"], None),
        "current_age": get_text_value(raw_item, ["current_age", "ageNow"], age),
        "occurred_date": get_text_value(raw_item, ["occurred_date", "occrde"], None),
        "nationality": get_text_value(raw_item, ["nationality", "nation"], None),
        "height_cm": get_text_value(raw_item, ["height", "height_cm", "tall"], None),
        "weight_kg": get_text_value(raw_item, ["bdwgh", "weight", "weight_kg"], None),
        "gender": gender,
        "missing_person_category": get_text_value(
            raw_item,
            ["missing_person_category", "category", "msspsnKnd", "kind"],
            "실종자"
        ),
        "last_seen_location": last_seen_location,
        "last_seen_latitude": get_text_value(raw_item, ["last_seen_latitude", "latitude", "lat"], None),
        "last_seen_longitude": get_text_value(raw_item, ["last_seen_longitude", "longitude", "lon", "lng"], None),
        "missing_time_hours": get_text_value(raw_item, ["missing_time_hours"], None),
        "appearance_description": appearance_description,
        "body_features": get_text_value(raw_item, ["etcSpfeatr", "body_features", "physical_features"], None),
        "hair_shape": get_text_value(raw_item, ["hairshpeDscd", "hair_shape"], None),
        "hair_color": get_text_value(raw_item, ["haircolrDscd", "hair_color"], None),
        "face_shape": get_text_value(raw_item, ["faceshpeDscd", "face_shape"], None),
        "description": description,
        "progress_status": get_text_value(raw_item, ["progress_status", "status"], None),
        "source_note": get_text_value(raw_item, ["source_note"], None),
        "report_summary": get_text_value(
            raw_item,
            ["report_summary", "summary"],
            f"{name} 실종자는 {last_seen_location}에서 마지막으로 목격되었습니다. {appearance_description}"
        ),
        "image_url": image_url,
        "raw_source": raw_item
    }


# ---- Attach stable source-aware id for missing persons ----
def attach_missing_person_source(missing_persons: list[dict], source: str):
    """
    실종자 id가 데이터 출처별로 충돌하지 않도록 source를 포함한 stable_id를 추가합니다.
    예: police_api_1, missing_persons_json_1
    """
    return [
        {
            **missing_person,
            "data_source": source,
            "stable_id": f"{source}_{missing_person.get('id')}",
        }
        for missing_person in missing_persons
    ]


def extract_items_from_police_response(response_text: str):
    """
    경찰청/Safe182 API 응답을 JSON 또는 XML로 파싱해 실종자 목록을 추출합니다.
    """
    try:
        parsed_json = json.loads(response_text)

        result_code = str(parsed_json.get("result", "00"))
        if result_code not in ("00", "0"):
            message = parsed_json.get("msg", "경찰청 API 요청이 실패했습니다.")
            raise RuntimeError(f"POLICE_MISSING_API_RESULT_{result_code}: {message}")

        items = parsed_json.get("list", [])

        if isinstance(items, dict):
            return [items]

        if isinstance(items, list):
            return items

        return []
    except json.JSONDecodeError:
        pass

    root = ET.fromstring(response_text)
    result_node = root.find(".//result")
    if result_node is not None and result_node.text not in (None, "00", "0"):
        message_node = root.find(".//msg")
        message = message_node.text if message_node is not None else "경찰청 API 요청이 실패했습니다."
        raise RuntimeError(f"POLICE_MISSING_API_RESULT_{result_node.text}: {message}")

    item_nodes = root.findall(".//list")
    if not item_nodes:
        item_nodes = root.findall(".//item")
    if not item_nodes:
        item_nodes = root.findall(".//row")

    items = []
    for node in item_nodes:
        item = {}
        for child in list(node):
            item[child.tag] = child.text
        items.append(item)

    return items


def load_missing_persons_fallback():
    """
    경찰청 API 호출 실패 시 사용하는 fallback 실종자 데이터입니다.
    """
    try:
        return load_json("data/missing_persons.json")
    except FileNotFoundError:
        return []


def fetch_police_missing_persons(page: int = 1, per_page: int = 10):
    """
    Safe182 실종경보 Open API를 호출합니다.

    환경변수:
    - POLICE_MISSING_API_URL: Safe182 실종경보 API 요청 URL
    - POLICE_MISSING_USER_ID: Safe182에서 발급받은 고유아이디(esntlId)
    - POLICE_MISSING_API_KEY: Safe182에서 발급받은 인증키(authKey)

    Safe182 amberList.do는 POST 방식이며, 필수 파라미터는 esntlId, authKey, rowSize입니다.
    """
    api_url = os.getenv("POLICE_MISSING_API_URL")
    user_id = os.getenv("POLICE_MISSING_USER_ID") or os.getenv("POLICE_MISSING_ESNTL_ID")
    api_key = os.getenv("POLICE_MISSING_API_KEY")

    if not api_url or not user_id or not api_key:
        raise RuntimeError("POLICE_MISSING_API_CONFIG_MISSING")

    request_data = urllib.parse.urlencode({
        "esntlId": user_id,
        "authKey": api_key,
        "rowSize": per_page,
        "page": page,
        "xmlUseYN": "N",
    }).encode("utf-8")

    request = urllib.request.Request(
        api_url,
        data=request_data,
        headers={
            "Content-Type": "application/x-www-form-urlencoded; charset=utf-8",
            "User-Agent": "Mozilla/5.0",
        },
        method="POST"
    )

    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            response_text = response.read().decode("utf-8")
    except urllib.error.HTTPError as error:
        raise RuntimeError(f"POLICE_MISSING_API_HTTP_ERROR: {error.code}") from error
    except urllib.error.URLError as error:
        raise RuntimeError(f"POLICE_MISSING_API_REQUEST_FAILED: {error}") from error

    raw_items = extract_items_from_police_response(response_text)
    return [
        normalize_missing_person(raw_item, index)
        for index, raw_item in enumerate(raw_items)
    ]


def get_missing_persons_with_fallback(page: int = 1, per_page: int = 10):
    """
    경찰청 API를 우선 사용하고, 실패하면 최근 성공한 Safe182 캐시를 사용합니다.
    캐시도 없으면 missing_persons.json fallback 데이터를 반환합니다.
    """
    try:
        police_items = attach_missing_person_source(
            fetch_police_missing_persons(page, per_page),
            "police_api",
        )
        set_safe182_cached_missing_persons(police_items)
        save_safe182_firestore_cached_missing_persons(police_items)
        return {
            "source": "police_api",
            "is_fallback": False,
            "fallback_reason": None,
            "missing_persons": police_items
        }
    except Exception as error:
        cached_items = get_safe182_cached_missing_persons()

        if cached_items is not None:
            return {
                "source": "police_api_cache",
                "is_fallback": False,
                "fallback_reason": f"POLICE_API_FAILED_USING_CACHE: {error}",
                "missing_persons": attach_missing_person_source(cached_items, "police_api")
            }

        firestore_cached_items = get_safe182_firestore_cached_missing_persons()

        if firestore_cached_items is not None:
            set_safe182_cached_missing_persons(firestore_cached_items)
            return {
                "source": "police_api_firestore_cache",
                "is_fallback": False,
                "fallback_reason": f"POLICE_API_FAILED_USING_FIRESTORE_CACHE: {error}",
                "missing_persons": attach_missing_person_source(firestore_cached_items, "police_api")
            }

        fallback_items = load_missing_persons_fallback()
        return {
            "source": "missing_persons_json",
            "is_fallback": True,
            "fallback_reason": str(error),
            "missing_persons": attach_missing_person_source(
                [
                    normalize_missing_person(item, index)
                    for index, item in enumerate(fallback_items)
                ],
                "missing_persons_json",
            )
        }

# ----- Missing Person Detail Helper -----
def find_missing_person_detail(missing_person_id: str, source: str | None = None):
    """
    경찰청 API 또는 fallback 데이터에서 id/stable_id가 일치하는 실종자 정보를 찾습니다.
    source가 제공되면 해당 데이터 출처의 실종자만 조회합니다.
    """
    requested_id = str(missing_person_id)
    requested_source = source
    raw_id = requested_id

    for candidate_source in ("police_api", "police_api_cache", "missing_persons_json"):
        prefix = f"{candidate_source}_"
        if requested_id.startswith(prefix):
            requested_source = "police_api" if candidate_source == "police_api_cache" else candidate_source
            raw_id = requested_id[len(prefix):]
            break

    if requested_source == "missing_persons_json":
        fallback_items = attach_missing_person_source(
            [
                normalize_missing_person(item, index)
                for index, item in enumerate(load_missing_persons_fallback())
            ],
            "missing_persons_json",
        )
        result = {
            "source": "missing_persons_json",
            "is_fallback": True,
            "fallback_reason": "REQUESTED_SOURCE_MISSING_PERSONS_JSON",
            "missing_persons": fallback_items,
        }
    else:
        result = get_missing_persons_with_fallback(page=1, per_page=100)

    for missing_person in result["missing_persons"]:
        if requested_source and missing_person.get("data_source") != requested_source:
            continue

        candidate_ids = {
            str(missing_person.get("id")),
            str(missing_person.get("stable_id")),
        }

        if raw_id in candidate_ids or requested_id in candidate_ids:
            return {
                "source": result["source"],
                "is_fallback": result["is_fallback"],
                "fallback_reason": result["fallback_reason"],
                "missing_person": missing_person
            }

    return {
        "source": result["source"],
        "is_fallback": result["is_fallback"],
        "fallback_reason": result["fallback_reason"],
        "missing_person": None
    }

# ---- Relevant Missing Persons Helper ----
def get_float_value(value):
    """
    문자열 또는 숫자 값을 float로 변환합니다.
    좌표가 없거나 변환할 수 없으면 None을 반환합니다.
    """
    if value in (None, ""):
        return None

    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def parse_frequent_places_input(frequent_places):
    """
    프론트엔드 query/body 또는 users.json의 frequent_places 값을 위치 후보 목록으로 변환합니다.
    지원 형식:
    - [{"name": "집", "latitude": 37.0, "longitude": 127.0}]
    - {"frequent_places": [...]} 또는 {"places": [...]}
    - "장소A,장소B" 또는 JSON 문자열
    """
    if frequent_places in (None, ""):
        return []

    if isinstance(frequent_places, str):
        value = frequent_places.strip()
        if not value:
            return []
        try:
            return parse_frequent_places_input(json.loads(value))
        except json.JSONDecodeError:
            return [
                place.strip()
                for place in re.split(r"[|,]", value)
                if place.strip()
            ]

    if isinstance(frequent_places, dict):
        nested_places = (
            frequent_places.get("frequent_places")
            or frequent_places.get("places")
            or frequent_places.get("items")
        )
        if nested_places is not None:
            return parse_frequent_places_input(nested_places)
        return [frequent_places]

    if isinstance(frequent_places, list):
        places = []
        for item in frequent_places:
            places.extend(parse_frequent_places_input(item))
        return places

    return []


def geocode_reference_place(query: str):
    """
    좌표 없이 장소명만 들어온 자주 가는 장소를 카카오 Local API로 좌표화합니다.
    API 키가 없거나 실패하면 해당 장소는 거리 계산에서 제외합니다.
    """
    if not query:
        return None

    try:
        keyword_result = request_kakao_local_api(
            "/v2/local/search/keyword.json",
            {"query": query},
        )
        documents = keyword_result.get("documents", [])

        if not documents:
            address_result = request_kakao_local_api(
                "/v2/local/search/address.json",
                {"query": query},
            )
            documents = address_result.get("documents", [])

        if not documents:
            return None

        return normalize_kakao_geocode_document(documents[0], query)
    except Exception:
        return None


def normalize_reference_location(raw_place, source: str, index: int):
    """
    현재 위치 또는 자주 가는 장소를 거리 계산용 표준 위치 객체로 변환합니다.
    """
    if isinstance(raw_place, str):
        geocoded = geocode_reference_place(raw_place)
        if geocoded is None:
            return None

        latitude = get_float_value(geocoded.get("latitude"))
        longitude = get_float_value(geocoded.get("longitude"))
        if latitude is None or longitude is None:
            return None

        return {
            "name": geocoded.get("place_name") or raw_place,
            "address": geocoded.get("address"),
            "latitude": latitude,
            "longitude": longitude,
            "source": source,
            "source_index": index,
            "geocoded": True,
        }

    if not isinstance(raw_place, dict):
        return None

    latitude = get_float_value(
        raw_place.get("latitude")
        or raw_place.get("lat")
        or raw_place.get("y")
    )
    longitude = get_float_value(
        raw_place.get("longitude")
        or raw_place.get("lon")
        or raw_place.get("lng")
        or raw_place.get("x")
    )

    name = get_text_value(
        raw_place,
        ["name", "place_name", "label", "title", "address"],
        f"자주 가는 장소 {index + 1}",
    )

    if latitude is None or longitude is None:
        query = get_text_value(
            raw_place,
            ["address", "place_name", "name", "query"],
            None,
        )
        geocoded = geocode_reference_place(query) if query else None
        if geocoded is None:
            return None

        latitude = get_float_value(geocoded.get("latitude"))
        longitude = get_float_value(geocoded.get("longitude"))
        if latitude is None or longitude is None:
            return None

        return {
            "name": geocoded.get("place_name") or name,
            "address": geocoded.get("address") or raw_place.get("address"),
            "latitude": latitude,
            "longitude": longitude,
            "source": source,
            "source_index": index,
            "geocoded": True,
        }

    return {
        "name": name,
        "address": raw_place.get("address"),
        "latitude": latitude,
        "longitude": longitude,
        "source": source,
        "source_index": index,
        "geocoded": False,
    }


def build_missing_alert_reference_locations(
    latitude: float,
    longitude: float,
    user_data: dict | None = None,
    frequent_places_input=None,
):
    """
    현재 위치와 자주 가는 장소를 합쳐 실종자 거리 점수 계산 기준점 목록을 만듭니다.
    """
    reference_locations = [
        {
            "name": "현재 위치",
            "address": user_data.get("current_address") if user_data else None,
            "latitude": latitude,
            "longitude": longitude,
            "source": "current_location",
            "source_index": 0,
            "geocoded": False,
        }
    ]

    seen = {(round(latitude, 7), round(longitude, 7))}
    place_sources = [
        ("frontend_frequent_place", frequent_places_input),
        ("user_frequent_place", user_data.get("frequent_places") if user_data else None),
    ]

    for source, raw_places in place_sources:
        for index, raw_place in enumerate(parse_frequent_places_input(raw_places)):
            location = normalize_reference_location(raw_place, source, index)
            if location is None:
                continue

            key = (round(location["latitude"], 7), round(location["longitude"], 7))
            if key in seen:
                continue

            seen.add(key)
            reference_locations.append(location)

    return reference_locations


def calculate_missing_person_relevance_score(
    user_latitude: float,
    user_longitude: float,
    missing_person: dict,
    reference_locations: list[dict] | None = None,
):
    """
    사용자 위치와 실종자 마지막 목격 위치를 기준으로 관련도 점수를 계산합니다.
    현재 위치와 자주 가는 장소 중 가장 가까운 기준점을 사용합니다.
    좌표가 없는 경우 낮은 기본 점수를 반환합니다.
    추후 AI target_score 모델이 연결되면 이 함수 내부를 교체할 수 있습니다.
    """
    last_seen_latitude = get_float_value(missing_person.get("last_seen_latitude"))
    last_seen_longitude = get_float_value(missing_person.get("last_seen_longitude"))
    last_seen_location = missing_person.get("last_seen_location")

    if (last_seen_latitude is None or last_seen_longitude is None) and last_seen_location:
        geocoded_location = geocode_reference_place(str(last_seen_location))

        if geocoded_location is not None:
            last_seen_latitude = get_float_value(geocoded_location.get("latitude"))
            last_seen_longitude = get_float_value(geocoded_location.get("longitude"))

            if last_seen_latitude is not None and last_seen_longitude is not None:
                missing_person["last_seen_latitude"] = last_seen_latitude
                missing_person["last_seen_longitude"] = last_seen_longitude
                missing_person["last_seen_geocoded"] = True
                missing_person["last_seen_geocoding_source"] = geocoded_location.get("source")
                missing_person["last_seen_geocoded_address"] = geocoded_location.get("address")
                missing_person["last_seen_geocoded_place_name"] = geocoded_location.get("place_name")

    if last_seen_latitude is None or last_seen_longitude is None:
        return {
            "relevance_score": 0.1,
            "distance_m": None,
            "nearest_reference_location": None,
            "reference_distances": [],
            "score_reason": "실종자 마지막 목격 위치의 주소/장소를 좌표로 변환하지 못해 낮은 기본 관련도를 적용했습니다."
        }

    if not reference_locations:
        reference_locations = [
            {
                "name": "현재 위치",
                "latitude": user_latitude,
                "longitude": user_longitude,
                "source": "current_location",
            }
        ]

    reference_distances = []
    for reference_location in reference_locations:
        reference_latitude = get_float_value(reference_location.get("latitude"))
        reference_longitude = get_float_value(reference_location.get("longitude"))
        if reference_latitude is None or reference_longitude is None:
            continue

        distance_m = calculate_distance_m(
            reference_latitude,
            reference_longitude,
            last_seen_latitude,
            last_seen_longitude,
        )
        reference_distances.append({
            "name": reference_location.get("name"),
            "source": reference_location.get("source"),
            "latitude": reference_latitude,
            "longitude": reference_longitude,
            "distance_m": distance_m,
        })

    if not reference_distances:
        return {
            "relevance_score": 0.1,
            "distance_m": None,
            "nearest_reference_location": None,
            "reference_distances": [],
            "score_reason": "거리 계산에 사용할 사용자 위치 또는 자주 가는 장소 좌표가 없어 낮은 기본 관련도를 적용했습니다."
        }

    nearest_reference = min(reference_distances, key=lambda item: item["distance_m"])
    distance_m = nearest_reference["distance_m"]

    if distance_m <= 1000:
        relevance_score = 0.95
    elif distance_m <= 3000:
        relevance_score = 0.75
    elif distance_m <= 5000:
        relevance_score = 0.55
    elif distance_m <= 10000:
        relevance_score = 0.35
    else:
        relevance_score = 0.15

    return {
        "relevance_score": relevance_score,
        "distance_m": distance_m,
        "nearest_reference_location": nearest_reference,
        "reference_distances": reference_distances,
        "score_reason": "실종자 마지막 목격 위치를 좌표화한 뒤, 사용자 현재 위치와 자주 가는 장소 중 가장 가까운 기준점으로 관련도를 계산했습니다."
    }


# ----- Missing Alert Classification Helper -----
def classify_missing_alert_by_score(relevance_score: float):
    """
    관련도 점수를 기준으로 실종자 알림 발송 여부와 알림 단계를 분류합니다.
    추후 AI target_score 모델이 연결되면 이 기준은 교체할 수 있습니다.
    """
    if relevance_score >= 0.75:
        return {
            "should_notify": True,
            "alert_level": "high",
            "alert_priority": 1,
            "alert_message": "사용자 위치와 매우 가까운 실종자 정보입니다. 주변을 유심히 확인해 주세요."
        }

    if relevance_score >= 0.35:
        return {
            "should_notify": True,
            "alert_level": "medium",
            "alert_priority": 2,
            "alert_message": "사용자 생활권과 관련될 수 있는 실종자 정보입니다. 이동 중 주변을 확인해 주세요."
        }

    return {
        "should_notify": False,
        "alert_level": "low",
        "alert_priority": 3,
        "alert_message": "현재 위치와의 관련도가 낮아 즉시 알림 대상은 아닙니다."
    }

def request_kakao_local_api(path: str, params: dict):
    """
    카카오 Local REST API를 호출하는 공통 함수입니다.
    KAKAO_REST_API_KEY 환경변수에 저장된 REST API 키를 사용합니다.
    """
    kakao_rest_api_key = os.getenv("KAKAO_REST_API_KEY")

    if not kakao_rest_api_key:
        raise RuntimeError("KAKAO_REST_API_KEY_MISSING")

    query_string = urllib.parse.urlencode(params)
    request_url = f"https://dapi.kakao.com{path}?{query_string}"

    request = urllib.request.Request(
        request_url,
        headers={
            "Authorization": f"KakaoAK {kakao_rest_api_key}"
        }
    )

    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            response_text = response.read().decode("utf-8")
    except urllib.error.HTTPError as error:
        raise RuntimeError(f"KAKAO_LOCAL_API_HTTP_ERROR: {error.code}") from error
    except urllib.error.URLError as error:
        raise RuntimeError(f"KAKAO_LOCAL_API_REQUEST_FAILED: {error}") from error

    return json.loads(response_text)


def normalize_kakao_geocode_document(document: dict, query: str):
    """
    카카오 주소/키워드 검색 결과를 재난/실종자 공통 지도 응답 형식으로 변환합니다.
    """
    latitude = document.get("y")
    longitude = document.get("x")

    return {
        "query": query,
        "place_name": document.get("place_name") or document.get("address_name"),
        "address": document.get("address_name"),
        "road_address": document.get("road_address_name"),
        "latitude": float(latitude) if latitude is not None else None,
        "longitude": float(longitude) if longitude is not None else None,
        "source": "kakao",
        "raw_source": document
    }

def normalize_kakao_keyword_search_document(document: dict):
    """
    카카오 키워드/장소 검색 결과를 프론트 주소 선택 화면에서 사용하는 공통 형식으로 변환합니다.
    """
    latitude = document.get("y")
    longitude = document.get("x")

    return {
        "name": document.get("place_name") or document.get("address_name"),
        "address": document.get("address_name"),
        "road_address": document.get("road_address_name"),
        "lat": float(latitude) if latitude is not None else None,
        "lon": float(longitude) if longitude is not None else None,
        "source": "kakao_keyword",
    }


def normalize_kakao_address_search_document(document: dict):
    """
    카카오 주소 검색 결과를 프론트 주소 선택 화면에서 사용하는 공통 형식으로 변환합니다.
    """
    latitude = document.get("y")
    longitude = document.get("x")
    address_info = document.get("address") or {}
    road_address_info = document.get("road_address") or {}

    address_name = document.get("address_name")
    road_address_name = road_address_info.get("address_name")

    return {
        "name": road_address_name or address_name,
        "address": address_info.get("address_name") or address_name,
        "road_address": road_address_name,
        "lat": float(latitude) if latitude is not None else None,
        "lon": float(longitude) if longitude is not None else None,
        "source": "kakao_address",
    }


def normalize_kakao_reverse_geocode_document(document: dict, latitude: float, longitude: float):
    """
    카카오 좌표→주소 변환 결과를 공통 지도 응답 형식으로 변환합니다.
    """
    road_address = document.get("road_address") or {}
    address = document.get("address") or {}

    return {
        "latitude": latitude,
        "longitude": longitude,
        "address": road_address.get("address_name") or address.get("address_name"),
        "road_address": road_address.get("address_name"),
        "region_1depth_name": address.get("region_1depth_name"),
        "region_2depth_name": address.get("region_2depth_name"),
        "region_3depth_name": address.get("region_3depth_name"),
        "source": "kakao",
        "raw_source": document
    }

def analyze_risk_mock(user_data: dict, latitude: float, longitude: float):
    """
    실제 위험도 분석 모델이 연결되기 전까지 사용하는 임시 위험도 분석 함수입니다.

    현재는 사용자 특성과 현재 위치를 바탕으로 위험 단계를 임시로 생성합니다.
    추후 데이터 분석 모델 또는 실시간 재난 데이터 API로 교체할 수 있습니다.
    """
    if user_data.get("is_semi_basement_resident"):
        return {
            "risk_level": "위험",
            "risk_score": 68,
            "risk_reason": "현재 위치 주변에 강한 비가 이어지고 있으며, 반지하 거주 환경으로 인해 실내 침수 위험이 높습니다.",
            "rainfall_level": "발목",
            "location_name": "숙명여대 인근",
            "updated_at": "14시 25분",
            "latitude": latitude,
            "longitude": longitude,
            "risk_keywords": ["강한 비", "반지하", "침수 위험"]
        }

    if user_data.get("has_disability") or user_data.get("is_mobility_vulnerable"):
        return {
            "risk_level": "위험",
            "risk_score": 64,
            "risk_reason": "현재 위치 주변에 강한 비가 이어지고 있으며, 이동에 시간이 더 걸릴 수 있어 조기 대피 준비가 필요합니다.",
            "rainfall_level": "발목",
            "location_name": "숙명여대 인근",
            "updated_at": "14시 25분",
            "latitude": latitude,
            "longitude": longitude,
            "risk_keywords": ["강한 비", "이동약자", "조기 대피"]
        }

    return {
        "risk_level": "주의",
        "risk_score": 42,
        "risk_reason": "현재 위치 주변 기상과 지형 정보를 확인해 침수 가능성을 계속 관찰하고 있습니다.",
        "rainfall_level": "주의",
        "location_name": "현재 위치 인근",
        "updated_at": "14시 25분",
        "latitude": latitude,
        "longitude": longitude,
        "risk_keywords": ["침수 관찰", "현재 위치", "주의"]
    }
def build_user_profile(user_id: int | None, request_profile: UserProfileRequest | None, risk_location_type: str | None = None,) -> dict:
    if request_profile is None:
        profile = {}
    elif hasattr(request_profile, "model_dump"):
        profile = request_profile.model_dump()
    else:
        profile = request_profile.dict()
    user_data = find_user_by_id(user_id) if user_id is not None else None
    disability_type = str(
        profile.get("disability_type")
        or (user_data or {}).get("disability_type")
        or ""
    ).lower()
    notification_methods = (user_data or {}).get("notification_methods") or []
    notification_preference = profile.get("notification_preference", "push")
    if notification_preference == "push" and "voice" in notification_methods:
        notification_preference = "tts"

    normalized_risk_location_type = risk_location_type or "home"
    home_environment_applies = normalized_risk_location_type in {"home", "residence"}
    is_basement = bool(
        profile.get("lives_in_basement_or_semi_basement", False)
        or profile.get("is_basement", False)
        or profile.get("is_semi_basement_resident", False)
        or (user_data or {}).get("is_semi_basement_resident", False)
    )
    is_mobility_limited = bool(
        profile.get("has_mobility_difficulty", False)
        or profile.get("is_mobility_limited", False)
        or profile.get("is_mobility_vulnerable", False)
        or (user_data or {}).get("is_mobility_vulnerable", False)
    )
    has_visual_impairment = bool(
        profile.get("has_visual_impairment", False)
        or "visual" in disability_type
        or "시각" in disability_type
    )

    return {
        "lives_in_basement_or_semi_basement": is_basement,
        "has_mobility_difficulty": is_mobility_limited,
        "uses_wheelchair_or_walking_aid": bool(profile.get("uses_wheelchair_or_walking_aid", False)),
        "needs_guardian_support": bool(profile.get("needs_guardian_support", False)),
        "frequently_uses_underground_space": bool(profile.get("frequently_uses_underground_space", False)),
        "is_with_child_or_elderly": bool(profile.get("is_with_child_or_elderly", False)),
        "is_basement": is_basement,
        "is_mobility_limited": is_mobility_limited,
        "is_semi_basement_resident": is_basement,
        "is_mobility_vulnerable": is_mobility_limited,
        "has_visual_impairment": has_visual_impairment,
        "has_disability": bool(
            profile.get("has_disability", False)
            or (user_data or {}).get("has_disability", False)
            or has_visual_impairment
        ),
        "disability_type": profile.get("disability_type") or (user_data or {}).get("disability_type"),
        "notification_preference": notification_preference,
        "risk_location_type": normalized_risk_location_type,
        "home_environment_applied": home_environment_applies,
    }

def rainfall_error_response(error: RainfallProviderError) -> JSONResponse:
    return JSONResponse(
        status_code=503,
        content={
            "error": {
                "code": error.code,
                "message": error.message,
            }
        },
        media_type="application/json; charset=utf-8",
    )

def zero_rainfall_fallback(error: RainfallProviderError) -> CurrentRainfallFeatures:
    return CurrentRainfallFeatures(
        features={
            "rainfall_total": 0.0,
            "rain_10m_max": 0.0,
            "rain_1h_max": 0.0,
            "rain_3h_max": 0.0,
            "rain_6h_max": 0.0,
            "rain_24h_max": 0.0,
        },
        source="rainfall-provider-unconfigured-zero-fallback",
        observed_at=None,
        raw_provider=error.code,
    )

def request_lat_lon(request: FloodRiskPredictRequest) -> tuple[float, float]:
    lat = request.lat if request.lat is not None else request.latitude
    lon = request.lon if request.lon is not None else request.longitude
    if lat is None or lon is None:
        raise ValueError("LOCATION_REQUIRED")
    return float(lat), float(lon)

def flat_rainfall_features(request: FloodRiskPredictRequest) -> dict[str, float] | None:
    flat_values = {
        "rainfall_total": request.rainfall_total,
        "rain_10m_max": request.rain_10m_max,
        "rain_1h_max": request.rain_1h_max,
        "rain_3h_max": request.rain_3h_max,
        "rain_6h_max": request.rain_6h_max,
        "rain_24h_max": request.rain_24h_max,
    }
    if all(value is None for value in flat_values.values()):
        return None
    return {
        key: value
        for key, value in flat_values.items()
        if value is not None
    }


FLOOD_RISK_MOCK_ALLOWED_LEVELS = {"안전", "주의", "위험", "긴급"}
flood_risk_mock_sequence_state: dict[str, dict] = {}


def normalize_mock_flood_risk_levels(levels: list[str] | None) -> list[str]:
    if not levels:
        return []

    normalized_levels = []
    for level in levels:
        normalized_level = str(level).strip()
        if normalized_level not in FLOOD_RISK_MOCK_ALLOWED_LEVELS:
            raise ValueError("INVALID_MOCK_RISK_LEVEL")
        normalized_levels.append(normalized_level)

    return normalized_levels


def build_mock_risk_sequence_key(
    request: FloodRiskPredictRequest,
    lat: float,
    lon: float,
) -> str:
    if request.mock_risk_sequence_key:
        return request.mock_risk_sequence_key

    return f"user:{request.user_id or 'anonymous'}:{lat:.5f}:{lon:.5f}"


def get_mock_flood_risk_level(
    request: FloodRiskPredictRequest,
    lat: float,
    lon: float,
) -> tuple[str, dict] | None:
    levels = normalize_mock_flood_risk_levels(request.mock_risk_levels)
    if not levels:
        return None

    interval_seconds = max(1, int(request.mock_risk_interval_seconds or 8))
    sequence_key = build_mock_risk_sequence_key(request, lat, lon)
    now = time.time()
    state = flood_risk_mock_sequence_state.get(sequence_key)

    if state is None or state.get("levels") != levels:
        state = {
            "levels": levels,
            "index": 0,
            "updated_at": now,
        }
    else:
        elapsed_steps = int((now - state["updated_at"]) // interval_seconds)
        if elapsed_steps > 0:
            state["index"] = (state["index"] + elapsed_steps) % len(levels)
            state["updated_at"] += elapsed_steps * interval_seconds

    flood_risk_mock_sequence_state[sequence_key] = state
    current_level = levels[state["index"]]

    return current_level, {
        "enabled": True,
        "sequence_key": sequence_key,
        "levels": levels,
        "current_index": state["index"],
        "interval_seconds": interval_seconds,
    }


@app.get("/")
def home():
    """
    서버가 정상적으로 실행 중인지 확인하는 기본 API입니다.
    """
    return {
        "message": "OkayProject backend server is running."
    }


# ----- Push Alert Payload Preview Endpoint -----
@app.post("/notifications/payload-preview")
def preview_notification_payload(request: AlertPayloadPreviewRequest):
    """
    프론트 알림 내역 저장 구조에 맞춘 Expo Push payload를 미리 확인하는 테스트용 API입니다.
    실제 푸시 전송은 하지 않고 payload만 반환합니다.
    """
    try:
        payload = create_push_alert_payload(
            expo_push_token=request.expo_push_token,
            user_id=request.user_id,
            alert_type=request.type,
            risk_level=request.risk_level,
            title=request.title,
            body=request.body,
            meta=request.meta,
        )
    except ValueError as error:
        return JSONResponse(
            status_code=400,
            content={
                "error": {
                    "code": str(error),
                    "message": "알림 type 또는 risk_level 값이 올바르지 않습니다.",
                }
            },
            media_type="application/json; charset=utf-8",
        )

    return JSONResponse(
        content={
            "status": "success",
            "payload": payload,
            "note": "테스트용 payload preview이며 실제 푸시 알림은 전송하지 않습니다.",
        },
        media_type="application/json; charset=utf-8",
    )


@app.post("/notifications/push-token")
def register_push_token(request: PushTokenRegistrationRequest):
    """
    프론트에서 발급받은 Expo Push Token을 사용자 정보에 저장합니다.
    """
    expo_push_token = request.expo_push_token.strip()

    if not is_valid_expo_push_token(expo_push_token):
        return JSONResponse(
            status_code=400,
            content={
                "error": {
                    "code": "INVALID_EXPO_PUSH_TOKEN",
                    "message": "Expo Push Token 형식이 올바르지 않습니다.",
                }
            },
            media_type="application/json; charset=utf-8",
        )

    updated_user = save_user_expo_push_token(request.user_id, expo_push_token)
    if updated_user is None:
        return JSONResponse(
            status_code=404,
            content={
                "error": {
                    "code": "USER_NOT_FOUND",
                    "message": "해당 user_id의 사용자를 찾을 수 없습니다.",
                }
            },
            media_type="application/json; charset=utf-8",
        )

    return JSONResponse(
        content={
            "status": "success",
            "message": "Expo Push Token이 저장되었습니다.",
            "user_id": request.user_id,
            "expo_push_token": expo_push_token,
            "storage": updated_user.get("push_token_storage"),
        },
        media_type="application/json; charset=utf-8",
    )


@app.post("/notifications/send-test")
def send_test_notification(request: SendTestNotificationRequest):
    """
    저장된 Expo Push Token 또는 요청에 포함된 token으로 테스트 푸시 알림을 전송합니다.
    """
    expo_push_token = (request.expo_push_token or get_user_expo_push_token(request.user_id) or "").strip()

    if not expo_push_token:
        return JSONResponse(
            status_code=404,
            content={
                "error": {
                    "code": "EXPO_PUSH_TOKEN_NOT_FOUND",
                    "message": "저장된 Expo Push Token이 없습니다. 먼저 /notifications/push-token을 호출해 주세요.",
                }
            },
            media_type="application/json; charset=utf-8",
        )

    if not is_valid_expo_push_token(expo_push_token):
        return JSONResponse(
            status_code=400,
            content={
                "error": {
                    "code": "INVALID_EXPO_PUSH_TOKEN",
                    "message": "Expo Push Token 형식이 올바르지 않습니다.",
                }
            },
            media_type="application/json; charset=utf-8",
        )

    try:
        payload = create_push_alert_payload(
            expo_push_token=expo_push_token,
            user_id=request.user_id,
            alert_type=request.type,
            risk_level=request.risk_level,
            title=request.title,
            body=request.body,
            meta=request.meta,
        )
        expo_response = send_expo_push_notification(payload)
    except ValueError as error:
        return JSONResponse(
            status_code=400,
            content={
                "error": {
                    "code": str(error),
                    "message": "알림 type 또는 risk_level 값이 올바르지 않습니다.",
                }
            },
            media_type="application/json; charset=utf-8",
        )
    except RuntimeError as error:
        return JSONResponse(
            status_code=502,
            content={
                "error": {
                    "code": "EXPO_PUSH_SEND_FAILED",
                    "message": str(error),
                },
                "payload": payload if "payload" in locals() else None,
            },
            media_type="application/json; charset=utf-8",
        )

    return JSONResponse(
        content={
            "status": "success",
            "payload": payload,
            "expo_response": expo_response,
        },
        media_type="application/json; charset=utf-8",
    )


@app.post("/users/profile")
def save_user_profile(request: UserProfileSaveRequest):
    """
    초기 사용자 정보 입력값을 저장하거나 기존 사용자 정보를 업데이트합니다.
    user_id가 있으면 기존 사용자 업데이트, 없으면 새 user_id를 생성합니다.
    """
    saved_result = save_user_profile_data(request)

    return JSONResponse(
        content={
            "message": "사용자 프로필이 저장되었습니다.",
            "mode": saved_result["mode"],
            "storage": saved_result["storage"],
            "user_id": saved_result["user_id"],
            "user": saved_result["user"],
        },
        media_type="application/json; charset=utf-8"
    )


@app.get("/alerts/banner")
def get_alert_banner(user_id: int):
    """
    홈/재난 화면에서 현재 위치 확인 배너를 표시할지 결정합니다.
    """
    user_data = find_user_by_id(user_id)

    if user_data is None:
        return JSONResponse(
            status_code=404,
            content={
                "error": {
                    "code": "USER_NOT_FOUND",
                    "message": "해당 user_id의 사용자를 찾을 수 없습니다."
                }
            },
            media_type="application/json; charset=utf-8"
        )

    return JSONResponse(
        content={
            "user_id": user_id,
            "show_banner": True,
            "level": "info",
            "banner_title": "현재 위치가 맞나요?",
            "banner_message": "현재 위치를 기준으로 재난 위험 정보를 안내합니다.",
            "detected_location": get_user_display_location(user_data),
            "buttons": [
                {"label": "맞아요", "action": "CONFIRM_LOCATION"},
                {"label": "수정하기", "action": "OPEN_LOCATION_ADJUSTMENT"},
            ],
            "next_api": {
                "confirm_location": "/location/confirm"
            }
        },
        media_type="application/json; charset=utf-8"
    )


@app.post("/location/confirm")
def confirm_location(request: LocationConfirmRequest):
    """
    프론트엔드 위치 확인 배너에서 사용자가 현재 위치를 확인했는지 저장합니다.
    """
    user_data = find_user_by_id(request.user_id)

    if user_data is None:
        return JSONResponse(
            status_code=404,
            content={
                "error": {
                    "code": "USER_NOT_FOUND",
                    "message": "해당 user_id의 사용자를 찾을 수 없습니다."
                }
            },
            media_type="application/json; charset=utf-8"
        )

    detected_position = {
        "latitude": request.latitude,
        "longitude": request.longitude,
    }

    if not request.is_current_location_correct:
        return JSONResponse(
            content={
                "user_id": request.user_id,
                "location_confirmed": False,
                "message": "현재 위치 확인이 보류되었습니다.",
                "next_action": "OPEN_LOCATION_ADJUSTMENT",
                "confirmed_position": detected_position,
                "detected_position": detected_position,
            },
            media_type="application/json; charset=utf-8"
        )

    updated_user = update_user_location(
        user_id=request.user_id,
        latitude=request.latitude,
        longitude=request.longitude,
        address=user_data.get("current_address") or user_data.get("address"),
        place_name=user_data.get("current_place_name") or user_data.get("place_name"),
    )

    return JSONResponse(
        content=jsonable_encoder({
            "user_id": request.user_id,
            "location_confirmed": True,
            "message": "현재 위치가 확인되었습니다.",
            "next_action": "DISMISS_BANNER",
            "confirmed_position": {
                "latitude": request.latitude,
                "longitude": request.longitude,
            },
            "detected_position": detected_position,
            "updated_user": updated_user,
        }),
        media_type="application/json; charset=utf-8"
    )


# ----- Location Update Endpoint -----
@app.post("/location/update")
def update_location(request: LocationUpdateRequest):
    """
    사용자가 지도에서 재조정한 현재 위치를 users.json에 저장합니다.

    요청 예시:
    {
        "user_id": 1,
        "latitude": 37.5446,
        "longitude": 126.9647,
        "address": "서울특별시 용산구 청파동",
        "place_name": "숙명여대입구역 인근"
    }
    """
    updated_user = update_user_location(
        user_id=request.user_id,
        latitude=request.latitude,
        longitude=request.longitude,
        address=request.address,
        place_name=request.place_name,
    )

    if updated_user is None:
        return JSONResponse(
            status_code=404,
            content={
                "error": {
                    "code": "USER_NOT_FOUND",
                    "message": "해당 user_id의 사용자를 찾을 수 없습니다."
                }
            },
            media_type="application/json; charset=utf-8"
        )


    return JSONResponse(
        content=jsonable_encoder({
            "message": "사용자 위치가 저장되었습니다.",
            "user_id": request.user_id,
            "current_location": {
                "latitude": request.latitude,
                "longitude": request.longitude,
                "address": request.address,
                "place_name": request.place_name,
            },
            "updated_user": updated_user
        }),
        media_type="application/json; charset=utf-8"
    )


# ----- Current Location Risk Context Endpoint -----
@app.post("/location/check-current")
def check_current_location(request: LocationCheckRequest):
    """
    현재 GPS 위치와 저장된 거주지 위치를 비교해
    위험도 계산 시 주거환경 정보를 반영할지 판단합니다.
    """
    user_data = find_user_by_id(request.user_id)

    if user_data is None:
        return JSONResponse(
            status_code=404,
            content={
                "error": {
                    "code": "USER_NOT_FOUND",
                    "message": "해당 user_id의 사용자를 찾을 수 없습니다."
                }
            },
            media_type="application/json; charset=utf-8"
        )

    home_latitude = (
        user_data.get("home_latitude")
        or user_data.get("residence_latitude")
        or user_data.get("latitude")
    )
    home_longitude = (
        user_data.get("home_longitude")
        or user_data.get("residence_longitude")
        or user_data.get("longitude")
    )

    if home_latitude is None or home_longitude is None:
        return JSONResponse(
            status_code=400,
            content={
                "error": {
                    "code": "HOME_LOCATION_NOT_FOUND",
                    "message": "저장된 거주지 좌표가 없어 현재 위치와 비교할 수 없습니다."
                }
            },
            media_type="application/json; charset=utf-8"
        )

    home_latitude = float(home_latitude)
    home_longitude = float(home_longitude)

    distance_from_home_m = calculate_distance_m(
        request.latitude,
        request.longitude,
        home_latitude,
        home_longitude,
    )

    is_near_home = distance_from_home_m <= 300
    risk_location_type = "home" if is_near_home else "current"

    current_address = None
    try:
        kakao_result = request_kakao_local_api(
            "/v2/local/geo/coord2address.json",
            {
                "x": request.longitude,
                "y": request.latitude,
            }
        )
        documents = kakao_result.get("documents", [])
        if documents:
            current_address = normalize_kakao_reverse_geocode_document(
                documents[0],
                request.latitude,
                request.longitude,
            ).get("address")
    except Exception:
        current_address = None

    message = (
        "현재 위치가 저장된 거주지 근처로 확인됩니다. 이 위치 기준으로 재난 위험도를 확인할까요?"
        if is_near_home
        else "현재 위치가 저장된 거주지와 다릅니다. 현재 위치 기준으로 재난 위험도를 확인할까요?"
    )

    return JSONResponse(
        content={
            "user_id": request.user_id,
            "current_location": {
                "latitude": request.latitude,
                "longitude": request.longitude,
                "address": current_address,
            },
            "home_location": {
                "latitude": home_latitude,
                "longitude": home_longitude,
                "address": user_data.get("address") or user_data.get("current_address"),
            },
            "distance_from_home_m": distance_from_home_m,
            "is_near_home": is_near_home,
            "home_distance_threshold_m": 300,
            "risk_location_type": risk_location_type,
            "home_environment_applied": is_near_home,
            "message": message,
            "recommended_risk_location": {
                "type": risk_location_type,
                "latitude": request.latitude,
                "longitude": request.longitude,
            },
        },
        media_type="application/json; charset=utf-8"
    )

@app.get("/rainfall/current/raw")
def get_current_rainfall_raw(latitude: float, longitude: float):
    """
    설정된 현재 강수 API를 호출하고 원 응답 일부를 반환합니다.

    KMA처럼 응답이 텍스트인 API를 처음 붙일 때 parser 작성 전 연결 확인용으로 사용합니다.
    API key는 응답 URL에서 마스킹합니다.
    """
    try:
        config = load_rainfall_provider_config()
        raw = fetch_configured_rainfall_raw(config=config, lat=latitude, lon=longitude)
    except RainfallProviderError as error:
        return rainfall_error_response(error)

    preview = raw.text[:2000]
    return JSONResponse(
        content={
            "source": config.source,
            "url": raw.url,
            "content_type": raw.content_type,
            "is_json": raw.parsed_json is not None,
            "preview": preview,
            "parsed_json": raw.parsed_json,
        },
        media_type="application/json; charset=utf-8",
    )


# Gemini Action Guide Helper Functions
def get_level_title(level: str) -> str:
    """
    위험 단계별 행동요령 제목을 반환합니다.
    LLM이 위험 단계를 새로 판단하지 않도록, 입력된 risk_level을 기준으로만 제목을 구성합니다.
    """
    if level == "안전":
        return "현재는 비교적 안전한 상태입니다."
    if level == "주의":
        return "현재 주의가 필요한 상태입니다."
    if level == "위험":
        return "현재 침수 위험이 높습니다."
    if level == "긴급":
        return "즉시 안전한 장소로 이동해야 합니다."
    return "현재 재난 상황을 확인해 주세요."


def build_template_action_guide(
    risk_level: str,
    risk_score: float | None,
    reasons: list[str],
    user_profile: dict | None,
    nearest_shelter: NearestShelterRequest | None,
):
    """
    Gemini 호출 실패 또는 API 키 누락 시 사용하는 템플릿 기반 행동요령입니다.
    """
    user_profile = user_profile or {}
    reason_text = ", ".join(reasons) if reasons else "현재 위치와 기상 정보를 기준으로 위험도가 산출되었습니다."

    actions = []

    if risk_level == "안전":
        short_message = "현재는 큰 위험이 감지되지 않았지만, 기상 상황을 계속 확인하세요."
        detail_guide = f"현재 위험 단계는 안전입니다. {reason_text} 갑작스러운 기상 변화가 있을 수 있으니 알림을 켜두고 주변 상황을 확인해 주세요."
        actions.extend([
            "기상 정보를 주기적으로 확인하세요.",
            "위치 정보가 정확한지 확인하세요.",
            "비가 강해지면 대피소 위치를 미리 확인하세요."
        ])
    elif risk_level == "주의":
        short_message = "침수 가능성에 대비해 현재 위치와 가까운 대피소를 확인하세요."
        detail_guide = f"현재 위험 단계는 주의입니다. {reason_text} 아직 즉시 대피 단계는 아니지만, 저지대나 지하 공간에 있다면 주변 상황을 자주 확인하는 것이 좋습니다."
        actions.extend([
            "현재 위치가 정확한지 확인하세요.",
            "가까운 대피소 위치를 미리 확인하세요.",
            "저지대와 지하 공간 주변의 물 고임을 확인하세요."
        ])
    elif risk_level == "위험":
        short_message = "지하 공간을 피하고 가까운 대피소 이동 경로를 확인하세요."
        detail_guide = f"현재 위험 단계는 위험입니다. {reason_text} 침수 위험이 커질 수 있으므로 지하 공간에 머무르고 있다면 지상층으로 이동하고, 대피소 이동 경로를 확인해 주세요."
        actions.extend([
            "지하 공간에서 벗어나세요.",
            "가까운 대피소 이동 경로를 확인하세요.",
            "하천 주변과 침수 도로 접근을 피하세요."
        ])
    else:
        short_message = "즉시 지하 공간에서 벗어나 안전한 장소로 이동하세요."
        detail_guide = f"현재 위험 단계는 긴급입니다. {reason_text} 즉시 안전한 실내 또는 가까운 대피소로 이동하고, 위험 지역 접근을 피해야 합니다."
        actions.extend([
            "즉시 지하 공간에서 벗어나세요.",
            "가까운 안전 장소나 대피소로 이동하세요.",
            "긴급 상황이면 119 또는 112에 연락하세요."
        ])

    if user_profile.get("is_semi_basement_resident") or user_profile.get("is_basement"):
        actions.append("반지하 또는 지하 공간에 있다면 즉시 지상층으로 이동하세요.")

    if user_profile.get("is_mobility_vulnerable") or user_profile.get("is_mobility_limited"):
        actions.append("혼자 이동이 어렵다면 보호자나 주변 사람에게 도움을 요청하세요.")

    if user_profile.get("has_disability"):
        actions.append("음성 안내, 보호자 연락, 주변 도움 요청을 함께 활용하세요.")

    shelter_text = ""
    if nearest_shelter and nearest_shelter.name:
        shelter_text = f" 가까운 대피소는 {nearest_shelter.name}입니다."
        if nearest_shelter.distance_m is not None:
            shelter_text += f" 현재 위치에서 약 {nearest_shelter.distance_m}m 떨어져 있습니다."

    tts_script = f"{get_level_title(risk_level)} {short_message}{shelter_text}"

    return {
        "risk_level": risk_level,
        "risk_score": risk_score,
        "title": get_level_title(risk_level),
        "short_message": short_message,
        "detail_guide": detail_guide + shelter_text,
        "tts_script": tts_script,
        "actions": actions,
        "generation_method": "template"
    }


def build_gemini_action_guide_prompt(
    risk_level: str,
    risk_score: float | None,
    reasons: list[str],
    user_profile: dict | None,
    nearest_shelter: NearestShelterRequest | None,
) -> str:
    """
    Gemini가 위험 단계를 새로 판단하지 않고 문장만 구성하도록 제한하는 프롬프트를 생성합니다.
    """
    shelter_data = None
    if nearest_shelter:
        shelter_data = {
            "name": nearest_shelter.name,
            "distance_m": nearest_shelter.distance_m,
            "address": nearest_shelter.address,
        }

    input_data = {
        "risk_level": risk_level,
        "risk_score": risk_score,
        "reasons": reasons,
        "user_profile": user_profile or {},
        "nearest_shelter": shelter_data,
    }

    return f"""
너는 개인 맞춤형 재난 안전 안내 문구를 작성하는 도우미입니다.

중요한 규칙:
1. 위험 단계는 이미 AI 위험도 모델이 판단한 값입니다.
2. 너는 위험 단계를 새로 판단하거나 바꾸면 안 됩니다.
3. 입력된 risk_level을 그대로 사용해야 합니다.
4. reasons는 왜 해당 위험 단계가 나왔는지 설명하는 근거입니다.
5. 사용자를 과도하게 불안하게 만들지 말고, 구체적이고 실행 가능한 행동요령을 작성하세요.
6. 출력은 반드시 JSON 형식만 반환하세요.

입력 데이터:
{json.dumps(input_data, ensure_ascii=False)}

반드시 아래 JSON 구조로만 응답하세요.
{{
  "title": "화면 상단 제목",
  "short_message": "짧은 알림 문구",
  "detail_guide": "상세 행동요령 문단",
  "tts_script": "음성 안내용 짧은 문장",
  "actions": ["행동요령1", "행동요령2", "행동요령3"]
}}
"""


def call_gemini_action_guide(prompt: str):
    """
    Gemini API를 호출해 재난 행동요령 문구를 생성합니다.
    GEMINI_API_KEY 환경변수가 없으면 RuntimeError를 발생시킵니다.
    """
    gemini_api_key = os.getenv("GEMINI_API_KEY")

    if not gemini_api_key:
        raise RuntimeError("GEMINI_API_KEY_MISSING")

    gemini_model = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
    request_url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"{gemini_model}:generateContent?key={gemini_api_key}"
    )

    payload = {
        "contents": [
            {
                "parts": [
                    {"text": prompt}
                ]
            }
        ],
        "generationConfig": {
            "temperature": 0.4,
            "responseMimeType": "application/json"
        }
    }

    request = urllib.request.Request(
        request_url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST"
    )

    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            response_text = response.read().decode("utf-8")
    except urllib.error.HTTPError as error:
        error_body = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(
            f"GEMINI_API_HTTP_ERROR: {error.code}: {error_body}"
        ) from error
    except urllib.error.URLError as error:
        raise RuntimeError(f"GEMINI_API_REQUEST_FAILED: {error}") from error

    response_json = json.loads(response_text)
    candidates = response_json.get("candidates", [])
    if not candidates:
        raise RuntimeError("GEMINI_RESPONSE_EMPTY")

    parts = candidates[0].get("content", {}).get("parts", [])
    if not parts:
        raise RuntimeError("GEMINI_RESPONSE_PARTS_EMPTY")

    generated_text = parts[0].get("text", "")
    if not generated_text:
        raise RuntimeError("GEMINI_RESPONSE_TEXT_EMPTY")

    return json.loads(generated_text)

@app.get("/missing-persons/police")
def get_police_missing_persons(page: int = 1, per_page: int = 10):
    """
    경찰청 실종경보정보 API에서 실종자 목록을 가져옵니다.

    API 키 또는 외부 API 연결에 문제가 있으면 missing_persons.json fallback 데이터를 반환합니다.
    """
    result = get_missing_persons_with_fallback(page, per_page)

    return JSONResponse(
        content={
            "source": result["source"],
            "is_fallback": result["is_fallback"],
            "fallback_reason": result["fallback_reason"],
            "page": page,
            "per_page": per_page,
            "count": len(result["missing_persons"]),
            "missing_persons": result["missing_persons"]
        },
        media_type="application/json; charset=utf-8"
    )

# ----- Missing Person Detail Endpoint -----
def create_missing_person_visual_prompt(missing_person: dict):
    """
    경찰청 실종자 정보와 리원이 공유한 프롬프트 구조를 바탕으로
    AI 전신 참고 이미지 생성용 프롬프트를 만듭니다.
    """
    age = missing_person.get("age") or "나이 미상"
    missing_age = missing_person.get("missing_age")
    current_age = missing_person.get("current_age") or age
    occurred_date = missing_person.get("occurred_date")
    gender = missing_person.get("gender") or "성별 미상"
    height_cm = get_text_value(
        missing_person,
        ["height_cm", "height", "tall", "키"],
        "정보 없음"
    )
    weight_kg = get_text_value(
        missing_person,
        ["weight_kg", "weight", "wght", "몸무게"],
        "정보 없음"
    )
    body_features = get_text_value(
        missing_person,
        ["body_features", "physical_features", "feature", "appearance_description"],
        missing_person.get("appearance_description") or "정보 없음"
    )
    outerwear = get_text_value(
        missing_person,
        ["outerwear", "top", "상의", "alldressingDscd"],
        missing_person.get("appearance_description") or "정보 없음"
    )
    pants = get_text_value(
        missing_person,
        ["pants", "bottom", "하의"],
        "정보 없음"
    )
    shoes = get_text_value(
        missing_person,
        ["shoes", "신발"],
        "정보 없음"
    )
    accessories = get_text_value(
        missing_person,
        ["accessories", "hat", "cap", "모자", "액세서리"],
        "정보 없음"
    )
    special_features = get_text_value(
        missing_person,
        ["special_features", "description", "detail", "report_summary"],
        missing_person.get("description") or missing_person.get("report_summary") or "정보 없음"
    )

    return f"""
제공된 얼굴 사진과 인상착의 정보를 바탕으로 실종자의 현재 추정 전신 참고 이미지를 생성해 주세요.

얼굴 사진이 제공된 경우, 어린 시절 얼굴 사진은 얼굴 인상, 얼굴형, 이목구비 비율, 머리 모양, 전체적인 얼굴 분위기를 보존하기 위한 주요 기준으로 사용해 주세요.
단, 현재 나이에 맞춘 age-progressed reference image로 생성해 주세요.
어린 시절 사진을 그대로 복제하지 말고, 당시 얼굴 특징을 바탕으로 현재 나이의 자연스러운 성인 얼굴로 조심스럽게 추정해 주세요.
얼굴 사진이 제공되지 않은 경우에는 특정 신원을 단정할 수 있는 얼굴을 임의로 만들지 말고, 텍스트 정보에 기반한 일반적인 참고 이미지 수준으로 생성해 주세요.

전신 사진이 제공된 경우, 전신 사진은 신체적 특징 참고용으로만 사용해 주세요.
전신 사진에서는 체형, 신체 비율, 키 느낌, 자세, 전체적인 실루엣만 참고해 주세요.
전신 사진 속 의류, 색상, 소지품, 액세서리는 텍스트로 입력된 착장 정보에 포함되어 있지 않다면 반영하지 마세요.

의류, 신발, 모자, 액세서리 등 착장 정보는 반드시 입력된 텍스트 데이터 기준으로 생성해 주세요.

기본 정보:
- 현재 나이: {current_age}
- 당시 나이: {missing_age or "정보 없음"}
- 발생일: {occurred_date or "정보 없음"}
- 성별: {gender}

신체 정보:
- 키: {height_cm}cm
- 몸무게: {weight_kg}kg
- 신체적 특징: {body_features}

착장 및 특이사항:
- 상의/겉옷: {outerwear}
- 하의: {pants}
- 신발: {shoes}
- 모자/액세서리: {accessories}
- 기타 특이사항: {special_features}

정면 전신 구도로 자연스럽게 서 있는 모습을 생성해 주세요.
머리부터 신발까지 전체 착장이 잘 보이도록 해 주세요.
배경은 완전한 흰색 배경으로 해 주세요.
회색 배경, 그림자, 바닥, 벽, 소품, 스튜디오 배경을 넣지 마세요.
인물은 이미지 중앙에 크게 배치해 주세요.
머리부터 신발까지 전신이 보이되, 인물이 화면 높이의 대부분을 차지하도록 해 주세요.
여백은 최소화하고 인물의 얼굴과 착장이 잘 보이게 해 주세요.

얼굴, 체형, 나이, 성별 표현, 착장을 과장하거나 임의로 바꾸지 마세요.
현재 나이 추정은 보수적으로 표현하고, 실제 현재 모습과 다를 수 있음을 전제로 자연스럽게 생성해 주세요.
영화 포스터, 화보, 만화, 애니메이션 스타일로 만들지 마세요.
이 이미지는 신원 식별용, 수사 판단용, 경찰청 공식 사진이 아니라, 공식 실종 경보의 공개 정보와 과거 얼굴 사진이 있을 경우 그 사진을 바탕으로 신고자가 특징을 이해하도록 돕는 AI 추정 참고 이미지입니다.
""".strip()


# --- Gemini Reference Image Helper Functions ---
def safe_missing_person_image_filename(missing_person_id: str) -> str:
    """
    missing_person_id를 파일명에 안전하게 사용할 수 있는 문자열로 변환합니다.
    """
    safe_id = re.sub(r"[^0-9a-zA-Z_-]", "_", str(missing_person_id))
    return f"missing_person_reference_{safe_id}_{REFERENCE_IMAGE_PROMPT_VERSION}.png"


def build_generated_image_url(filename: str) -> str:
    """
    저장된 AI 생성 참고 이미지를 프론트에서 표시할 수 있는 URL로 변환합니다.
    PUBLIC_BASE_URL이 있으면 절대 URL을, 없으면 상대 URL을 반환합니다.
    """
    public_base_url = os.getenv("PUBLIC_BASE_URL", "").rstrip("/")
    image_path = f"/generated/{filename}"

    if public_base_url:
        return f"{public_base_url}{image_path}"

    return image_path


def download_image_as_gemini_part(image_url: str | None):
    """
    경찰청 image_url이 있으면 Gemini 요청에 첨부할 inline_data part로 변환합니다.
    image_url이 없거나 다운로드 실패 시 None을 반환합니다.

    경찰청 API가 URL이 아니라 JPEG base64 문자열(`/9j/...`)을 내려주는 경우도 있어,
    URL 다운로드, backend 내부 로컬 파일 경로, base64 문자열을 모두 지원합니다.
    """
    if not image_url:
        return None

    image_value = str(image_url).strip()
    if not image_value:
        return None

    # data URL 형식: data:image/jpeg;base64,...
    if image_value.startswith("data:image") and "," in image_value:
        header, base64_data = image_value.split(",", 1)
        mime_type = header.split(";")[0].replace("data:", "") or "image/jpeg"
        try:
            base64.b64decode(base64_data, validate=True)
        except Exception:
            return None
        return {
            "inline_data": {
                "mime_type": mime_type,
                "data": base64_data,
            }
        }

    # backend 내부 로컬 파일 경로: data/missing_persons/kim_eunji.jpg
    if not image_value.startswith(("http://", "https://")):
        local_image_path = Path(image_value)
        if not local_image_path.is_absolute():
            local_image_path = BACKEND_DIR / image_value

        try:
            resolved_local_path = local_image_path.resolve()
            resolved_backend_dir = BACKEND_DIR.resolve()

            if (
                resolved_local_path.exists()
                and resolved_local_path.is_file()
                and resolved_backend_dir in resolved_local_path.parents
            ):
                image_bytes = resolved_local_path.read_bytes()
                mime_type = mimetypes.guess_type(str(resolved_local_path))[0] or "image/jpeg"
                return {
                    "inline_data": {
                        "mime_type": mime_type,
                        "data": base64.b64encode(image_bytes).decode("utf-8"),
                    }
                }
        except OSError:
            pass

        # 순수 base64 형식: /9j/4AAQSkZJRgABA... 또는 iVBORw0KGgo...
        compact_base64 = re.sub(r"\s+", "", image_value)
        padded_base64 = compact_base64 + "=" * (-len(compact_base64) % 4)
        try:
            image_bytes = base64.b64decode(padded_base64, validate=False)
        except Exception:
            return None

        if image_bytes.startswith(b"\xff\xd8\xff"):
            mime_type = "image/jpeg"
        elif image_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
            mime_type = "image/png"
        elif image_bytes.startswith(b"RIFF") and image_bytes[8:12] == b"WEBP":
            mime_type = "image/webp"
        else:
            mime_type = "image/jpeg"

        return {
            "inline_data": {
                "mime_type": mime_type,
                "data": base64.b64encode(image_bytes).decode("utf-8"),
            }
        }

    try:
        with urllib.request.urlopen(image_value, timeout=15) as response:
            image_bytes = response.read()
            content_type = response.headers.get("Content-Type")
    except Exception:
        return None

    mime_type = content_type or mimetypes.guess_type(image_value)[0] or "image/jpeg"

    return {
        "inline_data": {
            "mime_type": mime_type,
            "data": base64.b64encode(image_bytes).decode("utf-8")
        }
    }


def call_gemini_missing_person_reference_image(prompt: str, image_url: str | None = None) -> tuple[bytes, str, bool]:
    """
    Gemini 이미지 생성 모델을 호출해 실종자 참고 이미지를 생성합니다.
    경찰청 image_url이 있으면 얼굴 참고 이미지로 함께 전달합니다.
    """
    gemini_api_key = os.getenv("GEMINI_API_KEY")

    if not gemini_api_key:
        raise RuntimeError("GEMINI_API_KEY_MISSING")

    gemini_image_model = os.getenv("GEMINI_IMAGE_MODEL", "gemini-2.5-flash-image")
    request_url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"{gemini_image_model}:generateContent?key={gemini_api_key}"
    )

    parts = [{"text": prompt}]
    image_part = download_image_as_gemini_part(image_url)
    source_image_attached = image_part is not None
    if image_part:
        parts.append(image_part)

    payload = {
        "contents": [
            {
                "parts": parts
            }
        ],
        "generationConfig": {
            "responseModalities": ["TEXT", "IMAGE"]
        }
    }

    request = urllib.request.Request(
        request_url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST"
    )

    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            response_text = response.read().decode("utf-8")
    except urllib.error.HTTPError as error:
        error_body = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(
            f"GEMINI_IMAGE_API_HTTP_ERROR: {error.code}: {error_body}"
        ) from error
    except urllib.error.URLError as error:
        raise RuntimeError(f"GEMINI_IMAGE_API_REQUEST_FAILED: {error}") from error

    response_json = json.loads(response_text)
    candidates = response_json.get("candidates", [])

    for candidate in candidates:
        response_parts = candidate.get("content", {}).get("parts", [])
        for part in response_parts:
            inline_data = part.get("inlineData") or part.get("inline_data")
            if inline_data and inline_data.get("data"):
                mime_type = inline_data.get("mimeType") or inline_data.get("mime_type") or "image/png"
                return base64.b64decode(inline_data["data"]), mime_type, source_image_attached

    raise RuntimeError("GEMINI_IMAGE_RESPONSE_EMPTY")


@app.get("/missing-persons/{missing_person_id}/detail")
def get_missing_person_detail(missing_person_id: str, source: str | None = None):
    """
    실종자 id를 기준으로 상세 정보를 반환합니다.

    경찰청 API를 우선 조회하고, 실패하면 missing_persons.json fallback 데이터를 사용합니다.

    요청 예시:
    /missing-persons/1/detail
    """
    result = find_missing_person_detail(missing_person_id, source)

    if result["missing_person"] is None:
        return JSONResponse(
            status_code=404,
            content={
                "status": "failed",
                "error_code": "MISSING_PERSON_NOT_FOUND",
                "message": "해당 id의 실종자 정보를 찾을 수 없습니다.",
                "source": result["source"],
                "is_fallback": result["is_fallback"],
                "fallback_reason": result["fallback_reason"],
                "reference_image_url": None,
                "is_ai_generated": False,
                "notice": "실종자 정보를 찾을 수 없어 AI 참고 이미지를 생성하지 못했습니다."
            },
            media_type="application/json; charset=utf-8"
        )

    missing_person = result["missing_person"]

    return JSONResponse(
        content={
            "source": result["source"],
            "is_fallback": result["is_fallback"],
            "fallback_reason": result["fallback_reason"],
            "missing_person": missing_person,
            "visual_prompt": create_missing_person_visual_prompt(missing_person),
        },
        media_type="application/json; charset=utf-8"
    )

# ----- Generate AI Reference Image Endpoint -----
@app.post("/missing-persons/{missing_person_id}/reference-image")
def generate_missing_person_reference_image(
    missing_person_id: str,
    source: str | None = None,
    force_regenerate: bool = False,
):
    """
    missing_person_id를 기준으로 실종자 정보를 조회하고,
    Gemini 이미지 생성 모델로 AI 참고 이미지를 생성한 뒤 reference_image_url을 반환합니다.

    프론트는 응답의 reference_image_url을 이미지 src로 사용하면 됩니다.
    """
    result = find_missing_person_detail(missing_person_id, source)

    if result["missing_person"] is None:
        return JSONResponse(
            status_code=404,
            content={
                "error": {
                    "code": "MISSING_PERSON_NOT_FOUND",
                    "message": "해당 id의 실종자 정보를 찾을 수 없습니다."
                },
                "source": result["source"],
                "is_fallback": result["is_fallback"],
                "fallback_reason": result["fallback_reason"],
            },
            media_type="application/json; charset=utf-8"
        )

    missing_person = result["missing_person"]
    prompt = create_missing_person_visual_prompt(missing_person)
    filename = safe_missing_person_image_filename(missing_person_id)
    image_path = GENERATED_IMAGE_DIR / filename

    saved_record = None if force_regenerate else get_reference_image_record(missing_person_id)
    if saved_record is not None:
        return JSONResponse(
            content={
                "source": saved_record.get("source") or result["source"],
                "is_fallback": bool(saved_record.get("is_fallback")),
                "fallback_reason": saved_record.get("fallback_reason"),
                "missing_person_id": missing_person_id,
                "reference_image_url": saved_record.get("reference_image_url"),
                "status": saved_record.get("status"),
                "is_ai_generated": bool(saved_record.get("is_ai_generated")),
                "notice": saved_record.get("notice"),
                "image_generation_method": "db_cached",
                "image_disclaimer": saved_record.get("notice"),
                "visual_prompt": saved_record.get("visual_prompt") or prompt,
                "prompt_version": saved_record.get("prompt_version"),
                "source_image_attached": bool(saved_record.get("source_image_attached")),
                "force_regenerate": force_regenerate,
            },
            media_type="application/json; charset=utf-8"
        )

    if image_path.exists() and not force_regenerate:
        reference_image_url = build_generated_image_url(filename)
        cached_image_bytes = image_path.read_bytes()
        cached_mime_type = mimetypes.guess_type(str(image_path))[0] or "image/png"
        save_reference_image_record(
            missing_person_id=missing_person_id,
            reference_image_url=reference_image_url,
            status="success",
            is_ai_generated=True,
            notice="AI 생성 참고 이미지이며 경찰청 공식 사진이 아닙니다.",
            image_generation_method="cached",
            source=result["source"],
            is_fallback=result["is_fallback"],
            fallback_reason=result["fallback_reason"],
            visual_prompt=prompt,
            image_bytes=cached_image_bytes,
            mime_type=cached_mime_type,
        )
        return JSONResponse(
            content={
                "source": result["source"],
                "is_fallback": result["is_fallback"],
                "fallback_reason": result["fallback_reason"],
                "missing_person_id": missing_person_id,
                "reference_image_url": reference_image_url,
                "status": "success",
                "is_ai_generated": True,
                "notice": "AI 생성 참고 이미지이며 경찰청 공식 사진이 아닙니다.",
                "image_generation_method": "cached",
                "image_disclaimer": "AI 생성 참고 이미지이며 경찰청 공식 사진이 아닙니다.",
                "visual_prompt": prompt,
                "prompt_version": REFERENCE_IMAGE_PROMPT_VERSION,
                "source_image_attached": False,
                "force_regenerate": force_regenerate,
            },
            media_type="application/json; charset=utf-8"
        )

    try:
        image_bytes, mime_type, source_image_attached = call_gemini_missing_person_reference_image(
            prompt,
            missing_person.get("image_url")
        )
        image_path.write_bytes(image_bytes)
    except Exception as error:
        error_message = str(error)
        save_reference_image_record(
            missing_person_id=missing_person_id,
            reference_image_url=None,
            status="failed",
            is_ai_generated=False,
            notice="AI 참고 이미지 생성에 실패했습니다. 프론트에서는 fallback UI를 표시해 주세요.",
            image_generation_method="fallback_original_image_url",
            error_code="GEMINI_REFERENCE_IMAGE_UNAVAILABLE",
            message=error_message,
            source=result["source"],
            is_fallback=result["is_fallback"],
            fallback_reason=result["fallback_reason"],
            visual_prompt=prompt,
        )
        return JSONResponse(
            status_code=503,
            content={
                "status": "failed",
                "error_code": "GEMINI_REFERENCE_IMAGE_UNAVAILABLE",
                "message": error_message,
                "source": result["source"],
                "is_fallback": result["is_fallback"],
                "fallback_reason": result["fallback_reason"],
                "missing_person_id": missing_person_id,
                "reference_image_url": None,
                "is_ai_generated": False,
                "notice": "AI 참고 이미지 생성에 실패했습니다. 프론트에서는 fallback UI를 표시해 주세요.",
                "image_generation_method": "fallback_original_image_url",
                "prompt_version": REFERENCE_IMAGE_PROMPT_VERSION,
                "source_image_attached": False,
                "force_regenerate": force_regenerate
            },
            media_type="application/json; charset=utf-8"
        )

    reference_image_url = build_generated_image_url(filename)
    save_reference_image_record(
        missing_person_id=missing_person_id,
        reference_image_url=reference_image_url,
        status="success",
        is_ai_generated=True,
        notice="AI 생성 참고 이미지이며 경찰청 공식 사진이 아닙니다.",
        image_generation_method="gemini",
        source=result["source"],
        is_fallback=result["is_fallback"],
        fallback_reason=result["fallback_reason"],
        visual_prompt=prompt,
        prompt_version=REFERENCE_IMAGE_PROMPT_VERSION,
        source_image_attached=source_image_attached,
        image_bytes=image_bytes,
        mime_type=mime_type,
    )
    return JSONResponse(
        content={
            "source": result["source"],
            "is_fallback": result["is_fallback"],
            "fallback_reason": result["fallback_reason"],
            "missing_person_id": missing_person_id,
            "reference_image_url": reference_image_url,
            "status": "success",
            "is_ai_generated": True,
            "notice": "AI 생성 참고 이미지이며 경찰청 공식 사진이 아닙니다.",
            "mime_type": mime_type,
            "image_generation_method": "gemini",
            "image_disclaimer": "AI 생성 참고 이미지이며 경찰청 공식 사진이 아닙니다.",
            "visual_prompt": prompt,
            "prompt_version": REFERENCE_IMAGE_PROMPT_VERSION,
            "source_image_attached": source_image_attached,
            "force_regenerate": force_regenerate,
        },
        media_type="application/json; charset=utf-8"
    )

# ----- Relevant Missing Persons Endpoint -----
@app.get("/missing-persons/relevant")
def get_relevant_missing_persons(
    user_id: int | None = None,
    latitude: float | None = None,
    longitude: float | None = None,
    limit: int = 10,
    max_distance_m: int | None = None,
    frequent_places: str | None = None,
):
    """
    사용자 위치를 기준으로 관련성이 높은 실종자 목록을 반환합니다.

    경찰청 API를 우선 조회하고, 실패하면 missing_persons.json fallback 데이터를 사용합니다.
    현재 위치와 자주 가는 장소를 함께 보는 거리 기반 관련도 점수를 사용합니다.
    추후 AI target_score 모델로 교체할 수 있습니다.

    요청 예시:
    /missing-persons/relevant?user_id=1&latitude=37.5446&longitude=126.9647&limit=10
    /missing-persons/relevant?latitude=37.5446&longitude=126.9647&frequent_places=[{"name":"숙명여대","latitude":37.5463,"longitude":126.9647}]
    """
    user_data = None

    if user_id is not None:
        user_data = find_user_by_id(user_id)

        if user_data is None:
            return JSONResponse(
                status_code=404,
                content={
                    "error": {
                        "code": "USER_NOT_FOUND",
                        "message": "해당 user_id의 사용자를 찾을 수 없습니다."
                    }
                },
                media_type="application/json; charset=utf-8"
            )

        if latitude is None:
            latitude = user_data.get("current_latitude") or user_data.get("latitude")

        if longitude is None:
            longitude = user_data.get("current_longitude") or user_data.get("longitude")

    if latitude is None or longitude is None:
        return JSONResponse(
            status_code=400,
            content={
                "error": {
                    "code": "LOCATION_REQUIRED",
                    "message": "관련 실종자 조회에는 latitude/longitude 또는 위치 정보가 저장된 user_id가 필요합니다."
                }
            },
            media_type="application/json; charset=utf-8"
        )

    latitude = float(latitude)
    longitude = float(longitude)
    reference_locations = build_missing_alert_reference_locations(
        latitude=latitude,
        longitude=longitude,
        user_data=user_data,
        frequent_places_input=frequent_places,
    )

    candidate_count = max(1, min(max(limit * 3, limit), 30))
    result = get_missing_persons_with_fallback(page=1, per_page=candidate_count)
    relevant_missing_persons = []

    for missing_person in result["missing_persons"]:
        score_result = calculate_missing_person_relevance_score(
            user_latitude=latitude,
            user_longitude=longitude,
            missing_person=missing_person,
            reference_locations=reference_locations,
        )

        if max_distance_m is not None:
            distance_m = score_result["distance_m"]
            if distance_m is None or distance_m > max_distance_m:
                continue

        relevant_missing_persons.append({
            **missing_person,
            "relevance_score": score_result["relevance_score"],
            "distance_m": score_result["distance_m"],
            "nearest_reference_location": score_result["nearest_reference_location"],
            "reference_distances": score_result["reference_distances"],
        })

    relevant_missing_persons.sort(
        key=lambda item: (
            -float(item.get("relevance_score", 0)),
            item.get("distance_m") if item.get("distance_m") is not None else 10**12,
        )
    )

    limited_missing_persons = relevant_missing_persons[:max(1, limit)]

    return JSONResponse(
        content={
            "source": result["source"],
            "is_fallback": result["is_fallback"],
            "fallback_reason": result["fallback_reason"],
            "user_id": user_id,
            "current_location": {
                "latitude": latitude,
                "longitude": longitude
            },
            "reference_locations": reference_locations,
            "count": len(limited_missing_persons),
            "candidate_count": candidate_count,
            "max_distance_m": max_distance_m,
            "missing_persons": limited_missing_persons,
            "scoring_method": "distance_based_v2_with_frequent_places"
        },
        media_type="application/json; charset=utf-8"
    )


# ----- Missing Alert Classification Endpoint -----
@app.get("/missing-alert/classify")
def classify_missing_alerts(
    user_id: int | None = None,
    latitude: float | None = None,
    longitude: float | None = None,
    limit: int = 10,
    max_distance_m: int | None = None,
    frequent_places: str | None = None,
):
    """
    사용자 위치를 기준으로 실종자 알림 발송 대상을 분류합니다.

    최신 실종자 목록 조회 구조를 사용해 현재 위치와 자주 가는 장소 기준 관련도를 계산한 뒤,
    relevance_score 기준으로 should_notify와 alert_level을 반환합니다.

    요청 예시:
    /missing-alert/classify?user_id=1&latitude=37.5446&longitude=126.9647&limit=10
    /missing-alert/classify?latitude=37.5446&longitude=126.9647&frequent_places=[{"name":"숙명여대","latitude":37.5463,"longitude":126.9647}]
    """
    user_data = None

    if user_id is not None:
        user_data = find_user_by_id(user_id)

        if user_data is None:
            return JSONResponse(
                status_code=404,
                content={
                    "error": {
                        "code": "USER_NOT_FOUND",
                        "message": "해당 user_id의 사용자를 찾을 수 없습니다."
                    }
                },
                media_type="application/json; charset=utf-8"
            )

        if latitude is None:
            latitude = user_data.get("current_latitude") or user_data.get("latitude")

        if longitude is None:
            longitude = user_data.get("current_longitude") or user_data.get("longitude")

    if latitude is None or longitude is None:
        return JSONResponse(
            status_code=400,
            content={
                "error": {
                    "code": "LOCATION_REQUIRED",
                    "message": "실종자 알림 분류에는 latitude/longitude 또는 위치 정보가 저장된 user_id가 필요합니다."
                }
            },
            media_type="application/json; charset=utf-8"
        )

    latitude = float(latitude)
    longitude = float(longitude)
    reference_locations = build_missing_alert_reference_locations(
        latitude=latitude,
        longitude=longitude,
        user_data=user_data,
        frequent_places_input=frequent_places,
    )

    candidate_count = max(1, min(max(limit * 3, limit), 30))
    result = get_missing_persons_with_fallback(page=1, per_page=candidate_count)
    alert_results = []

    for missing_person in result["missing_persons"]:
        score_result = calculate_missing_person_relevance_score(
            user_latitude=latitude,
            user_longitude=longitude,
            missing_person=missing_person,
            reference_locations=reference_locations,
        )
        if max_distance_m is not None:
            distance_m = score_result["distance_m"]
            if distance_m is None or distance_m > max_distance_m:
                continue
        classification = classify_missing_alert_by_score(score_result["relevance_score"])

        alert_results.append({
            **missing_person,
            "relevance_score": score_result["relevance_score"],
            "distance_m": score_result["distance_m"],
            "nearest_reference_location": score_result["nearest_reference_location"],
            "reference_distances": score_result["reference_distances"],
            "should_notify": classification["should_notify"],
            "alert_level": classification["alert_level"],
            "alert_priority": classification["alert_priority"],
            "alert_message": classification["alert_message"],
        })

    alert_results.sort(
        key=lambda item: (
            item.get("alert_priority", 99),
            item.get("distance_m") if item.get("distance_m") is not None else 10**12,
        )
    )

    limited_alerts = alert_results[:max(1, limit)]
    notify_targets = [item for item in limited_alerts if item.get("should_notify")]

    return JSONResponse(
        content={
            "source": result["source"],
            "is_fallback": result["is_fallback"],
            "fallback_reason": result["fallback_reason"],
            "user_id": user_id,
            "current_location": {
                "latitude": latitude,
                "longitude": longitude
            },
            "reference_locations": reference_locations,
            "count": len(limited_alerts),
            "candidate_count": candidate_count,
            "max_distance_m": max_distance_m,
            "alerts": limited_alerts,
            "notify_count": len(notify_targets),
            "classification_method": "distance_relevance_threshold_v2_with_frequent_places"
        },
        media_type="application/json; charset=utf-8"
    )


@app.post("/missing-alert/classify")
def classify_missing_alerts_from_body(request: MissingAlertClassifyRequest):
    """
    프론트엔드가 자주 가는 장소 배열을 JSON body로 넘길 수 있는 실종자 알림 분류 API입니다.

    요청 예시:
    {
      "user_id": 1,
      "latitude": 37.5446,
      "longitude": 126.9647,
      "frequent_places": [
        {"name": "숙명여대", "latitude": 37.5463, "longitude": 126.9647}
      ],
      "limit": 10
    }
    """
    return classify_missing_alerts(
        user_id=request.user_id,
        latitude=request.latitude,
        longitude=request.longitude,
        limit=request.limit,
        max_distance_m=request.max_distance_m,
        frequent_places=request.frequent_places,
    )


@app.post("/api/flood-risk/predict")
def predict_flood_risk_api(request: FloodRiskPredictRequest):
    """
    프론트엔드가 넘긴 위경도로 침수 상대 위험도를 산출합니다.

    - 표준 공개 요청은 latitude/longitude와 flat rainfall fields를 사용합니다.
    - 호환을 위해 lat/lon과 rainfall_features 중첩 형식도 받습니다.
    - 강수 필드가 없으면 CURRENT_RAINFALL_API_URL 설정을 이용해 현재 강수 provider에서 가져옵니다.
    - 현재 provider는 표준 강수 피처 JSON 또는 KMA APIHub 격자 RN1 응답을 지원합니다.
    """
    try:
        lat, lon = request_lat_lon(request)
    except ValueError as error:
        return JSONResponse(
            status_code=400,
            content={
                "error": {
                    "code": str(error),
                    "message": "위험도 산출에는 lat/lon 또는 latitude/longitude가 필요합니다.",
                }
            },
            media_type="application/json; charset=utf-8",
        )

    try:
        mock_risk_override = get_mock_flood_risk_level(request, lat, lon)
    except ValueError as error:
        return JSONResponse(
            status_code=400,
            content={
                "error": {
                    "code": str(error),
                    "message": "mock_risk_levels에는 안전, 주의, 위험, 긴급만 사용할 수 있습니다.",
                }
            },
            media_type="application/json; charset=utf-8",
        )

    rainfall_meta = None
    request_rainfall_features = request.rainfall_features or flat_rainfall_features(request)
    if request_rainfall_features is None:
        try:
            rainfall = get_current_rainfall_features(lat=lat, lon=lon)
        except RainfallProviderError as error:
            if error.code != "RAINFALL_PROVIDER_UNCONFIGURED":
                return rainfall_error_response(error)
            rainfall = zero_rainfall_fallback(error)
        rainfall_features = rainfall.features
        rainfall_meta = {
            "source": rainfall.source,
            "observed_at": rainfall.observed_at,
            "raw_provider": rainfall.raw_provider,
            "features": rainfall.features,
        }
    else:
        try:
            rainfall_features = extract_standard_rainfall_features(request_rainfall_features)
        except RainfallProviderError as error:
            return rainfall_error_response(error)
        rainfall_meta = {
            "source": "request.rainfall_features" if request.rainfall_features else "request.flat_rainfall_fields",
            "observed_at": None,
            "features": rainfall_features,
        }

    try:
        predict_flood_risk = load_flood_risk_predictors()
        resolved_user_profile = build_user_profile(request.user_id, request.user_profile, request.risk_location_type,)
        result = predict_flood_risk(
            lat=lat,
            lon=lon,
            rainfall_features=rainfall_features,
            user_profile=resolved_user_profile,
            official_alert_active=request.official_alert_active,
        )
    except ValueError as error:
        return JSONResponse(
            status_code=400,
            content={
                "error": {
                    "code": str(error),
                    "message": "위험도 산출에 필요한 입력값이 올바르지 않습니다.",
                }
            },
            media_type="application/json; charset=utf-8",
        )
    except RuntimeError as error:
        return JSONResponse(
            status_code=503,
            content={
                "error": {
                    "code": "AI_MODEL_UNAVAILABLE",
                    "message": str(error),
                }
            },
            media_type="application/json; charset=utf-8",
        )

    result["rainfall"] = rainfall_meta
    result["required_rainfall_features"] = RAINFALL_FEATURE_COLUMNS
    if mock_risk_override is not None:
        mock_risk_level, mock_risk_meta = mock_risk_override
        if mock_risk_level == "위험" and resolved_user_profile.get("is_basement"):
            mock_risk_level = "긴급"
            mock_risk_meta = {
                **mock_risk_meta,
                "profile_escalation_applied": True,
                "profile_escalation_reason": "반지하/지하 거주 설정으로 위험 mock 단계를 긴급으로 상향했습니다.",
            }
        original_final_risk_level = result.get("final_risk_level")
        result["original_final_risk_level"] = original_final_risk_level
        result["final_risk_level"] = mock_risk_level
        result["base_risk_level"] = mock_risk_level
        result["ai_risk_level"] = mock_risk_level
        result["mock_risk_sequence"] = mock_risk_meta
        reasons = result.get("reasons")
        if isinstance(reasons, list):
            reasons.append(f"테스트용 mock_risk_levels에 따라 {mock_risk_level} 단계로 응답했습니다.")
    result["level"] = result["final_risk_level"]
    result["risk_level"] = result["final_risk_level"]
    return JSONResponse(content=result, media_type="application/json; charset=utf-8")


# Gemini Disaster Action Guide Endpoint
@app.post("/disaster/action-guide")
def generate_disaster_action_guide(request: ActionGuideRequest):
    """
    AI 위험도 모델이 판단한 risk_level, risk_score, reasons를 바탕으로
    사용자 맞춤 재난 행동요령 문구를 생성합니다.

    Gemini는 위험 단계를 판단하지 않고, 이미 전달된 risk_level과 reasons를 바탕으로 문장만 구성합니다.
    Gemini API 키가 없거나 호출에 실패하면 템플릿 기반 문구를 반환합니다.
    """
    user_profile = request.user_profile or {}

    if request.user_id is not None:
        user_data = find_user_by_id(request.user_id)
        if user_data:
            user_profile = {
                **user_profile,
                "has_disability": user_data.get("has_disability", False),
                "disability_type": user_data.get("disability_type"),
                "is_mobility_vulnerable": user_data.get("is_mobility_vulnerable", False),
                "is_semi_basement_resident": user_data.get("is_semi_basement_resident", False),
            }

    template_result = build_template_action_guide(
        request.risk_level,
        request.risk_score,
        request.reasons,
        user_profile,
        request.nearest_shelter,
    )

    try:
        prompt = build_gemini_action_guide_prompt(
            request.risk_level,
            request.risk_score,
            request.reasons,
            user_profile,
            request.nearest_shelter,
        )
        gemini_result = call_gemini_action_guide(prompt)

        return JSONResponse(
            content={
                "risk_level": request.risk_level,
                "risk_score": request.risk_score,
                "title": gemini_result.get("title", template_result["title"]),
                "short_message": gemini_result.get("short_message", template_result["short_message"]),
                "detail_guide": gemini_result.get("detail_guide", template_result["detail_guide"]),
                "tts_script": gemini_result.get("tts_script", template_result["tts_script"]),
                "actions": gemini_result.get("actions", template_result["actions"]),
                "reasons": request.reasons,
                "user_context": user_profile,
                "nearest_shelter": request.nearest_shelter.model_dump() if request.nearest_shelter else None,
                "generation_method": "gemini",
                "fallback_reason": None
            },
            media_type="application/json; charset=utf-8"
        )
    except Exception as error:
        template_result["reasons"] = request.reasons
        template_result["user_context"] = user_profile
        template_result["nearest_shelter"] = request.nearest_shelter.model_dump() if request.nearest_shelter else None
        template_result["fallback_reason"] = str(error)

        return JSONResponse(
            content=template_result,
            media_type="application/json; charset=utf-8"
        )

@app.get("/map/search")
def search_map_places(query: str, size: int = 10):
    """
    장소명/건물명 검색을 우선 수행하고, 결과가 없으면 주소 검색으로 fallback합니다.

    요청 예시:
    /map/search?query=숙명여자대학교
    /map/search?query=서울역
    """
    normalized_query = query.strip()
    if not normalized_query:
        return JSONResponse(
            status_code=400,
            content={
                "error": {
                    "code": "QUERY_REQUIRED",
                    "message": "검색어 query가 필요합니다."
                }
            },
            media_type="application/json; charset=utf-8"
        )

    safe_size = max(1, min(size, 15))

    try:
        keyword_result = request_kakao_local_api(
            "/v2/local/search/keyword.json",
            {
                "query": normalized_query,
                "size": safe_size,
            },
        )
        keyword_documents = keyword_result.get("documents", [])
    except Exception as error:
        keyword_documents = []
        keyword_error = str(error)
    else:
        keyword_error = None

    if keyword_documents:
        return JSONResponse(
            content={
                "query": normalized_query,
                "search_type": "keyword",
                "fallback_used": False,
                "keyword_error": keyword_error,
                "count": len(keyword_documents),
                "results": [
                    normalize_kakao_keyword_search_document(document)
                    for document in keyword_documents
                ],
            },
            media_type="application/json; charset=utf-8"
        )

    try:
        address_result = request_kakao_local_api(
            "/v2/local/search/address.json",
            {
                "query": normalized_query,
                "size": safe_size,
            },
        )
        address_documents = address_result.get("documents", [])
    except Exception as error:
        return JSONResponse(
            status_code=503,
            content={
                "error": {
                    "code": "KAKAO_PLACE_SEARCH_FAILED",
                    "message": str(error),
                    "keyword_error": keyword_error,
                },
                "query": normalized_query,
                "results": [],
            },
            media_type="application/json; charset=utf-8"
        )

    return JSONResponse(
        content={
            "query": normalized_query,
            "search_type": "address",
            "fallback_used": True,
            "keyword_error": keyword_error,
            "count": len(address_documents),
            "results": [
                normalize_kakao_address_search_document(document)
                for document in address_documents
            ],
        },
        media_type="application/json; charset=utf-8"
    )

@app.get("/map/geocode")
def geocode_address(query: str):
    """
    주소 또는 장소명을 위도/경도로 변환합니다.
    재난 위치 재조정, 대피소 지도 표시, 실종자 마지막 목격 위치 변환에 공통으로 사용합니다.

    요청 예시:
    /map/geocode?query=숙명여대입구역
    """
    try:
        keyword_result = request_kakao_local_api(
            "/v2/local/search/keyword.json",
            {"query": query}
        )

        documents = keyword_result.get("documents", [])

        if not documents:
            address_result = request_kakao_local_api(
                "/v2/local/search/address.json",
                {"query": query}
            )
            documents = address_result.get("documents", [])

        if not documents:
            return JSONResponse(
                status_code=404,
                content={
                    "error": {
                        "code": "GEOCODING_RESULT_NOT_FOUND",
                        "message": "입력한 주소 또는 장소명에 대한 좌표를 찾을 수 없습니다."
                    }
                },
                media_type="application/json; charset=utf-8"
            )

        result = normalize_kakao_geocode_document(documents[0], query)

        return JSONResponse(
            content=result,
            media_type="application/json; charset=utf-8"
        )
    except RuntimeError as error:
        return JSONResponse(
            status_code=503,
            content={
                "error": {
                    "code": "KAKAO_MAP_API_UNAVAILABLE",
                    "message": str(error)
                }
            },
            media_type="application/json; charset=utf-8"
        )


@app.get("/map/reverse-geocode")
def reverse_geocode(latitude: float, longitude: float):
    """
    위도/경도를 주소로 변환합니다.
    사용자의 현재 위치 확인 및 위치 재조정 화면에서 공통으로 사용합니다.

    요청 예시:
    /map/reverse-geocode?latitude=37.5446&longitude=126.9647
    """
    try:
        kakao_result = request_kakao_local_api(
            "/v2/local/geo/coord2address.json",
            {
                "x": longitude,
                "y": latitude
            }
        )

        documents = kakao_result.get("documents", [])

        if not documents:
            return JSONResponse(
                status_code=404,
                content={
                    "error": {
                        "code": "REVERSE_GEOCODING_RESULT_NOT_FOUND",
                        "message": "입력한 좌표에 대한 주소를 찾을 수 없습니다."
                    }
                },
                media_type="application/json; charset=utf-8"
            )

        result = normalize_kakao_reverse_geocode_document(
            documents[0],
            latitude,
            longitude
        )

        return JSONResponse(
            content=result,
            media_type="application/json; charset=utf-8"
        )
    except RuntimeError as error:
        return JSONResponse(
            status_code=503,
            content={
                "error": {
                    "code": "KAKAO_MAP_API_UNAVAILABLE",
                    "message": str(error)
                }
            },
            media_type="application/json; charset=utf-8"
        )



@app.get("/shelters/nearby")
def get_nearby_shelters(latitude: float, longitude: float):
    """
    사용자의 현재 위치를 기준으로 가까운 대피소 목록을 반환합니다.

    요청 예시:
    /shelters/nearby?latitude=37.5446&longitude=126.9647
    """
    shelters = load_json("data/shelters.json")

    result = []

    for shelter in shelters:
        distance_m = calculate_distance_m(
            latitude,
            longitude,
            shelter["latitude"],
            shelter["longitude"]
        )

        result.append({
            "id": shelter["id"],
            "name": shelter["name"],
            "address": shelter["address"],
            "latitude": shelter["latitude"],
            "longitude": shelter["longitude"],
            "distance_m": distance_m,
            "walk_time_min": max(1, round(distance_m / 67)),
            "distance_source": "straight_line_fallback",
            "straight_distance_m": distance_m,
            "is_open": shelter["is_open"],
            "status_text": get_shelter_status_text(shelter["is_open"]),
            "map_url": create_kakao_map_url(
                shelter["name"],
                shelter["latitude"],
                shelter["longitude"]
            ),
            "route_url": create_kakao_walk_route_url(
                "현재위치",
                latitude,
                longitude,
                shelter["name"],
                shelter["latitude"],
                shelter["longitude"]
            )
        })

    result.sort(key=lambda shelter: shelter["distance_m"])

    nearest_shelter = result[0] if result else None

    return JSONResponse(
        content={
            "current_location": {
                "latitude": latitude,
                "longitude": longitude
            },
            "nearest_shelter": nearest_shelter,
            "shelters": result
        },
        media_type="application/json; charset=utf-8"
    )


# ----- Move get_shelter_detail endpoint after get_nearby_shelters -----

@app.get("/shelters/{shelter_id}")
def get_shelter_detail(
    shelter_id: int,
    latitude: float | None = None,
    longitude: float | None = None,
):
    """
    shelter_id를 기준으로 특정 대피소 상세 정보를 반환합니다.

    latitude/longitude를 함께 보내면 현재 위치 기준 거리와 도보 예상 시간을 함께 계산합니다.

    요청 예시:
    /shelters/1
    /shelters/1?latitude=37.5446&longitude=126.9647
    """
    shelters = load_json("data/shelters.json")

    for shelter in shelters:
        if shelter["id"] == shelter_id:
            result = {
                "id": shelter["id"],
                "name": shelter["name"],
                "address": shelter["address"],
                "latitude": shelter["latitude"],
                "longitude": shelter["longitude"],
                "is_open": shelter["is_open"],
                "status_text": get_shelter_status_text(shelter["is_open"]),
                "map_url": create_kakao_map_url(
                    shelter["name"],
                    shelter["latitude"],
                    shelter["longitude"]
                )
            }

            if latitude is not None and longitude is not None:
                distance_m = calculate_distance_m(
                    latitude,
                    longitude,
                    shelter["latitude"],
                    shelter["longitude"]
                )
                result["distance_m"] = distance_m
                result["walk_time_min"] = max(1, round(distance_m / 67))
                result["distance_source"] = "straight_line_fallback"
                result["straight_distance_m"] = distance_m
                result["current_location"] = {
                    "latitude": latitude,
                    "longitude": longitude
                }
                result["route_url"] = create_kakao_walk_route_url(
                    "현재위치",
                    latitude,
                    longitude,
                    shelter["name"],
                    shelter["latitude"],
                    shelter["longitude"]
                )

            return JSONResponse(
                content=result,
                media_type="application/json; charset=utf-8"
            )

    return JSONResponse(
        status_code=404,
        content={
            "error": {
                "code": "SHELTER_NOT_FOUND",
                "message": "해당 shelter_id의 대피소 정보를 찾을 수 없습니다."
            }
        },
        media_type="application/json; charset=utf-8"
    )
