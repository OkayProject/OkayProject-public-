# OkayProject

OkayProject는 개인 맞춤형 재난 및 실종 안전 알림 Android 앱 프로젝트입니다. 현재 핵심 MVP는 서울 지역 침수 위험을 예측하고, 앱/백엔드가 사용할 수 있는 위험 점수, 위험 단계, 근거, 권장 알림 채널을 안정적으로 제공하는 것입니다.

모델 점수와 위험 단계는 공식 대피 판단을 대체하지 않는 보조 정보입니다. 사용자에게 "절대 안전"처럼 확정적인 안전 표현을 하지 않습니다.

## Repository Structure

- `ai/`: 침수 위험 AI 파이프라인, 모델 산출물, 리포트, API 스펙
- `ai/src/flood_risk/`: 백엔드가 호출하는 침수 위험 추론 모듈
- `ai/models/flood_xgb_v10_stage3_operational/`: 현재 운영 기준 v10 stage3 모델 패키지
- `ai/reports/flood_v10_stage3_operational/`: v10 운영 모델 리포트와 threshold/metric 문서
- `ai/docs/`: 모델 구조, API 계약, AI 요약 문서
- `backend/`: FastAPI 백엔드, 현재 강수 provider, 알림/실종/지도/대피소 API
- `frontend/`: Expo/React Native Android 앱
- `data/raw/`: 원본 공공데이터
- `data/processed/`: 학습/연동용 처리 데이터
- `docs/`: 기획, 회의, 디자인 자료

## Current Flood Model

현재 표준 운영 모델은 `flood_xgb_v10_stage3_operational`입니다.

- Runtime module: `ai/src/flood_risk/predict_v10_stage3.py`
- Model artifacts: `ai/models/flood_xgb_v10_stage3_operational/`
- Data version: `flood_dataset_v1`
- Score meaning: 공식 확률이 아니라 침수 위험 판단을 위한 모델 상대 점수
- Risk levels: `일반`, `주의`, `위험`, `긴급`
- API spec: `ai/docs/api/flood-risk-api-spec.md`
- Model structure: `ai/docs/flood-v10-final-model-structure.md`

v10은 3개 stage로 구성된 XGBoost binary classifier pipeline입니다.

1. Stage1은 지형/공간 feature로 침수 후보 여부를 넓게 거릅니다.
2. Stage2는 지형/공간 feature와 강우 feature를 함께 보고 `risk_score`를 산출합니다.
3. Stage3는 `위험` 후보의 false positive를 줄이는 danger filter입니다.
4. 최종 위험 단계는 threshold와 Stage3 통과 여부로 결정합니다.

운영 threshold는 모델 패키지의 `thresholds.json`을 기준으로 합니다.

```text
stage1_candidate = 0.3747505248
caution = 0.055
danger_candidate = 0.065
stage3_danger_filter = 0.0124278469
emergency = 0.2207685262
```

최종 단계 결정 흐름:

```text
stage1_score < stage1_candidate
  -> risk_score = 0, 일반

risk_score >= emergency
  -> 긴급

danger_candidate <= risk_score < emergency
  -> Stage3 실행
  -> Stage3 통과: 위험
  -> Stage3 미통과: 주의

risk_score >= caution
  -> 주의

otherwise
  -> 일반
```

## API Contract

침수 위험 예측 endpoint:

```text
POST /api/flood-risk/predict
```

기본 요청:

```json
{
  "user_id": 1,
  "latitude": 37.5446,
  "longitude": 126.9647
}
```

테스트나 강수 provider fallback 용도로 강수 feature를 직접 넘길 수 있습니다.

```json
{
  "user_id": 1,
  "latitude": 37.5446,
  "longitude": 126.9647,
  "rainfall_total": 72.5,
  "rainfall_1h": 35.0,
  "rainfall_3h": 52.0,
  "rainfall_6h": 80.0,
  "rainfall_24h": 120.0,
  "max_hourly_intensity": 35.0
}
```

대표 응답:

```json
{
  "risk_score": 0.1884,
  "relative_risk_score": 0.1884,
  "base_probability": 0.1884,
  "personalized_probability": 0.1884,
  "base_risk_level": "위험",
  "ai_risk_level": "위험",
  "final_risk_level": "위험",
  "risk_level": "위험",
  "thresholds": {
    "stage1_candidate": 0.3747505247592926,
    "caution": 0.055,
    "danger": 0.065,
    "danger_candidate": 0.065,
    "stage3_danger_filter": 0.012427846901118755,
    "emergency": 0.2207685261964798
  },
  "stage1_score": 0.42,
  "stage2_score": 0.1884,
  "stage3_danger_filter_score": 0.04,
  "model_version": "flood_xgb_v10_stage3_operational",
  "data_version": "flood_dataset_v1",
  "reasons": ["최근 누적 강수량이 높습니다."],
  "recommended_channels": ["push"],
  "personalization": {
    "applied": false,
    "included_in_model": false
  }
}
```

프론트엔드는 위험 단계를 자체 계산하지 않고 `risk_level` 또는 `final_risk_level`을 그대로 사용합니다. LLM은 위험 단계나 대피 여부를 새로 판단하지 않고, 이미 산출된 단계에 맞는 안내 문구만 생성합니다.

## Setup

### AI

AI 개발 환경은 `ai/pyproject.toml`과 `ai/requirements.txt`에서 관리합니다.

```bash
cd ai
uv sync
```

기존 `ai/.venv`를 직접 쓰는 경우:

```bash
cd ai
env UV_CACHE_DIR=../.uv-cache python3 -m uv pip install --python .venv -r requirements.txt
.venv/bin/python -c "import pandas, geopandas, rasterio, sklearn, xgboost"
```

### Backend

```bash
python3 -m venv backend/.venv
backend/.venv/bin/pip install -r backend/requirements.txt
FLOOD_RISK_MODEL_VERSION=v10_stage3 \
FLOOD_RISK_MODEL_DIR=ai/models/flood_xgb_v10_stage3_operational \
backend/.venv/bin/uvicorn backend.main:app --reload
```

주요 환경변수 이름은 `.env.example`을 기준으로 합니다. API key, 서비스 계정 JSON, 개인 토큰은 저장소에 커밋하지 않습니다.

### Frontend

```bash
cd frontend
npm install
npm run start
```

프론트 API base URL은 `frontend/.env.example`의 `EXPO_PUBLIC_API_BASE_URL` 형식을 따릅니다.

## Useful Commands

v10 stage3 백엔드 smoke test:

```bash
python -m pytest backend/tests/test_flood_v10_stage3_smoke.py
```

백엔드 테스트:

```bash
python -m pytest backend/tests
```

프론트 lint:

```bash
cd frontend
npm run lint
```

AI 데이터 파이프라인은 작업 대상 데이터셋에 맞는 `ai/scripts/data_pipeline/` 스크립트를 사용합니다. 큰 데이터 파일을 새로 추가하면 README나 리포트에 필요 이유와 재생성 방법을 남깁니다.

## Data Notes

학습/평가용 과거 강수량은 API 호출이 아니라 다운로드 원자료를 사용합니다. 서비스 추론용 현재 강수량은 백엔드의 current rainfall provider가 담당합니다.

주요 데이터/산출물:

- `data/raw/flood-traces/seoul/`: 연도별 서울 침수흔적도 원본
- `data/raw/rainfall/`: 과거 강수 원자료 안내와 아카이브
- `data/raw/dem/seoul_dem.tif`: 서울 DEM
- `data/raw/hydrography/rivers/`: 하천 데이터
- `data/processed/flood_dataset_v1/`: v10 운영 모델 데이터셋 산출물
- `ai/models/flood_xgb_v10_stage3_operational/grid_static_runtime.parquet`: 런타임 격자 static feature

## Notification Payload Preview

`POST /notifications/payload-preview`는 실제 푸시를 보내지 않고 프론트 알림 내역 저장용 Expo Push payload만 반환합니다.

공통 `payload.data` 구조:

```json
{
  "id": "flood-1-20260527123000123-ab12cd34",
  "type": "flood",
  "risk_level": "emergency",
  "meta": "{}",
  "created_at": "2026-05-27T12:30:00.123+09:00"
}
```

- `type`: `flood` 또는 `missing`
- `flood` 알림의 `risk_level`: `주의`, `위험`, `긴급` 입력을 각각 `caution`, `danger`, `emergency`로 변환합니다.
- `missing` 알림의 `risk_level`: 위험 단계 개념이 없으므로 `null`을 반환하며, 프론트 표시 판단에 사용하지 않습니다.

실제 Expo Push 수신 테스트용 API:

- `POST /notifications/push-token`: 프론트에서 발급받은 Expo Push Token을 Firestore `user_push_tokens` collection에 저장합니다.
- `POST /notifications/send-test`: 저장된 token 또는 요청에 포함된 token으로 테스트 푸시를 전송합니다.

## Safety And Privacy

- 모델 점수는 공식 대피 판단을 대체하지 않는 보조 위험 정보입니다.
- 사용자에게 "절대 안전"처럼 확정적인 안전 표현을 하지 않습니다.
- `risk_score`만 단독으로 크게 보여주기보다 위험 단계, 주요 근거, 권장 행동을 함께 표시합니다.
- 반지하 거주, 이동약자, 시각장애 정보는 민감 정보로 취급하고 로그에 원문을 남기지 않습니다.
- 개인정보만으로 `긴급`까지 승격하지 않습니다.
- 네트워크 실패, 위치 권한 거부, 강수 데이터 없음, 모델 응답 오류는 별도 상태로 처리합니다.
