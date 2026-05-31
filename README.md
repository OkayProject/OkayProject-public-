# OkayProject

OkayProject는 개인 맞춤형 재난 및 실종 안전 알림 Android 앱 프로젝트입니다. 앱 이름은 **내곁안전**이며, 사용자의 위치와 프로필을 바탕으로 침수 위험, 주변 대피소, 실종자 관련 알림을 한 화면 흐름 안에서 제공합니다.

이 저장소는 공개용 스냅샷입니다. 기존 private 개발 저장소의 Git 히스토리는 포함하지 않고, 최종 산출물 기준 파일만 정리해 공개했습니다.

## Project Goal

- 침수 위험 예측 결과를 `일반`, `주의`, `위험`, `긴급` 단계로 전달
- 사용자의 주거 형태, 이동 취약성, 시각장애 여부, 알림 선호를 반영한 안내 제공
- 현재 위치 또는 자주 가는 장소 주변의 실종자 알림 우선순위 계산
- 가까운 대피소와 카카오맵 길찾기 연결
- 재난/실종 알림 이력과 푸시 payload 구조 관리

모델 점수와 위험 단계는 공식 대피 판단을 대체하지 않는 보조 정보입니다. 실제 위급 상황에서는 경찰, 소방, 지자체, 재난안전문자 등 공식 안내를 우선해야 합니다.

## Team Scope

OkayProject는 팀 프로젝트로 진행되었습니다. 공개 저장소는 민감 정보가 포함될 수 있는 기존 private 개발 히스토리를 제외하고 최종 산출물을 새로 업로드한 스냅샷입니다. 따라서 GitHub contributors에는 대표 업로드 계정만 표시될 수 있지만, 실제 작업은 아래 영역을 나누어 협업했습니다.

| 영역 | 주요 작업 |
|---|---|
| AI/Data | 침수 위험 데이터셋 구축, v10 stage3 모델 패키징, 모델 리포트 작성 |
| Backend | FastAPI API, 침수 위험 추론 연동, 실종자/대피소/지도/알림 API |
| Frontend | Expo/React Native 앱 화면, 온보딩, 프로필, 위험/실종/대피소 화면 | 카카오 길찾기 연결 UI 구현
| Product/Design | 사용자 시나리오, 안전 문구 정책, 발표/시연 흐름 |

### Contributor Note

이 public repository의 commit history는 공개 안전성을 위해 최소화되어 있습니다. 기존 개발 저장소의 전체 commit author 기록을 가져오지 않았기 때문에 GitHub contributors 수가 실제 팀 구성과 다를 수 있습니다.

## Main Features

### 1. 침수 위험 알림

- 위치와 강수 feature를 기반으로 침수 위험 점수 산출
- `일반`, `주의`, `위험`, `긴급` 위험 단계 반환
- 위험 단계별 UI 화면 제공: `disaster-safe`, `disaster-caution`, `disaster-danger`, `disaster-emergency`
- 반지하/지하 거주자, 이동약자, 시각장애 사용자에 대한 추론 후 보정
- TTS, 진동, 플래시 등 알림 선호를 고려한 권장 채널 제공

### 2. 실종자 알림

- 경찰청 Safe182 실종경보정보 API 연동 구조
- API 실패 시 fallback JSON과 Firestore 캐시를 활용하는 구조
- 사용자 현재 위치와 자주 가는 장소를 기준으로 실종자 관련도 점수 계산
- 거리, 최종 목격 장소, 실종 시간, 특징 정보를 앱에 표시
- Gemini 기반 실종자 참고 이미지 생성/캐시 구조 포함
- 상세 이미지 화면과 112 신고 연결 제공

### 3. 위치와 대피소

- 위치 권한 요청 및 현재 위치 확인 flow
- 집 주소, 층수, 자주 가는 장소 저장
- 카카오 Local API 기반 주소/장소 검색, reverse geocoding
- 주변 대피소 조회, 거리/도보 시간 계산
- 카카오맵 길찾기 URL 연결 및 도착 확인 flow

### 4. 알림과 사용자 프로필

- Expo Push Token 저장 및 테스트 푸시 API
- 실제 푸시를 보내지 않고 payload를 확인하는 preview API
- 앱 내 알림 이력 저장
- 이름, 전화번호, 거주지, 이동 취약성, 알림 방식 입력
- 네트워크 실패, 위치 권한 거부, 강수 데이터 없음, 모델 응답 오류 상태 처리

## App Flow

```text
Splash
  -> Onboarding
  -> Permission consent
  -> Basic info
  -> Mobility status
  -> Address settings
  -> Home / risk screen
```

주요 화면:

- `frontend/app/index.tsx`: 앱 시작 화면
- `frontend/app/onboarding.tsx`: 서비스 소개
- `frontend/app/permission-consent.tsx`: 위치/알림 권한 안내
- `frontend/app/basic-info.tsx`: 기본 사용자 정보 입력
- `frontend/app/mobility-status.tsx`: 이동 취약성 및 알림 방식 입력
- `frontend/app/address-settings.tsx`: 주소와 자주 가는 장소 설정
- `frontend/app/disaster-*.tsx`: 침수 위험 단계별 화면
- `frontend/app/missing.tsx`: 실종자 알림 목록/요약
- `frontend/app/missing-detail.tsx`: 실종자 참고 이미지 상세
- `frontend/app/shelter-route.tsx`: 대피소와 길찾기 안내
- `frontend/app/alert-history.tsx`: 지난 알림 이력
- `frontend/app/profile-edit.tsx`: 프로필 수정

## Architecture

```text
Expo/React Native App
  -> FastAPI Backend
    -> Flood Risk Predictor
    -> Current Rainfall Provider
    -> Safe182 Missing Person API / fallback cache
    -> Kakao Local API / route URL
    -> Firestore cache and push token storage
    -> Gemini action guide and reference image generation
```

## Repository Structure

- `frontend/`: Expo/React Native Android 앱
- `frontend/app/`: expo-router 기반 화면
- `frontend/src/api/`: 백엔드 API client
- `frontend/src/components/`: 공통 UI, 위험 UI, 실종자 이미지 컴포넌트
- `frontend/src/storage/`: 사용자 프로필, 알림 선호, 알림 이력 저장
- `backend/`: FastAPI 백엔드
- `backend/main.py`: API endpoint, 실종/지도/대피소/알림 orchestration
- `backend/rainfall_provider.py`: 현재 강수 provider와 강수 feature 정규화
- `backend/tests/`: 백엔드 계약, 알림, 실종자 관련도, v10 smoke test
- `ai/`: 침수 위험 AI 파이프라인, 모델 산출물, 리포트
- `ai/src/flood_risk/`: 백엔드가 호출하는 침수 위험 추론 모듈
- `ai/models/flood_xgb_v10_stage3_operational/`: 운영 기준 v10 stage3 모델 패키지
- `ai/docs/`: 모델 구조, API 계약, AI 요약 문서
- `data/raw/`: 원본 공공데이터
- `data/processed/`: 학습/연동용 처리 데이터

## Backend API

주요 endpoint:

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/` | 서버 상태 확인 |
| `POST` | `/api/flood-risk/predict` | 침수 위험 예측 |
| `POST` | `/disaster/action-guide` | 위험 단계별 행동 안내 생성 |
| `GET` | `/alerts/banner` | 위치 확인/위험 알림 배너 |
| `POST` | `/location/confirm` | 감지 위치 확인 |
| `POST` | `/location/update` | 사용자 현재 위치 갱신 |
| `POST` | `/location/check-current` | 집/현재 위치 위험 기준 판단 |
| `GET` | `/rainfall/current/raw` | 현재 강수 provider 원본 확인 |
| `GET` | `/missing-persons/police` | 실종자 목록 조회 |
| `GET` | `/missing-persons/{id}/detail` | 실종자 상세 조회 |
| `POST` | `/missing-persons/{id}/reference-image` | 실종자 참고 이미지 생성/캐시 |
| `GET` | `/missing-persons/relevant` | 위치 기준 관련 실종자 조회 |
| `GET`/`POST` | `/missing-alert/classify` | 실종자 알림 대상 분류 |
| `GET` | `/map/search` | 카카오 장소 검색 |
| `GET` | `/map/geocode` | 주소/장소명 좌표 변환 |
| `GET` | `/map/reverse-geocode` | 좌표 주소 변환 |
| `GET` | `/shelters/nearby` | 주변 대피소 조회 |
| `GET` | `/shelters/{id}` | 대피소 상세 조회 |
| `POST` | `/notifications/payload-preview` | 알림 payload preview |
| `POST` | `/notifications/push-token` | Expo Push Token 저장 |
| `POST` | `/notifications/send-test` | 테스트 푸시 전송 |
| `POST` | `/users/profile` | 사용자 프로필 저장 |

## Flood Risk Model

현재 표준 운영 모델은 `flood_xgb_v10_stage3_operational`입니다.

- Runtime module: `ai/src/flood_risk/predict_v10_stage3.py`
- Model artifacts: `ai/models/flood_xgb_v10_stage3_operational/`
- Data version: `flood_dataset_v1`
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

## Flood Risk API Example

```text
POST /api/flood-risk/predict
```

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
  "base_risk_level": "위험",
  "final_risk_level": "위험",
  "risk_level": "위험",
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

프론트엔드는 위험 단계를 자체 계산하지 않고 `risk_level` 또는 `final_risk_level`을 그대로 사용합니다. LLM은 위험 단계나 대피 여부를 새로 판단하지 않고 이미 산출된 단계에 맞는 안내 문구만 생성합니다.

## Setup

### Backend

```bash
python3 -m venv backend/.venv
backend/.venv/bin/pip install -r backend/requirements.txt
FLOOD_RISK_MODEL_VERSION=v10_stage3 \
FLOOD_RISK_MODEL_DIR=ai/models/flood_xgb_v10_stage3_operational \
backend/.venv/bin/uvicorn backend.main:app --reload
```

### Frontend

```bash
cd frontend
npm install
npm run start
```

프론트 API base URL은 `frontend/.env.example`의 `EXPO_PUBLIC_API_BASE_URL` 형식을 따릅니다.

### AI

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

## Environment Variables

실제 API key와 서비스 계정 JSON은 저장소에 포함하지 않습니다. 필요한 이름은 `.env.example`을 기준으로 합니다.

주요 환경변수:

- `CURRENT_RAINFALL_API_URL`, `CURRENT_RAINFALL_API_KEY`
- `KMA_API_KEY`
- `POLICE_MISSING_API_KEY`, `POLICE_MISSING_API_URL`
- `KAKAO_REST_API_KEY`
- `GEMINI_API_KEY`, `GEMINI_MODEL`
- `FIREBASE_SERVICE_ACCOUNT_JSON`
- `FLOOD_RISK_MODEL_VERSION`
- `FLOOD_RISK_MODEL_DIR`
- `EXPO_PUBLIC_API_BASE_URL`

## Useful Commands

```bash
python -m pytest backend/tests
```

```bash
python -m pytest backend/tests/test_flood_v10_stage3_smoke.py
```

```bash
cd frontend
npm run lint
```

## Data Notes

학습/평가용 과거 강수량은 API 호출이 아니라 다운로드 원자료를 사용합니다. 서비스 추론용 현재 강수량은 백엔드의 current rainfall provider가 담당합니다.

주요 데이터/산출물:

- `data/raw/flood-traces/seoul/`: 연도별 서울 침수흔적도 원본
- `data/raw/rainfall/`: 과거 강수 원자료 안내와 아카이브
- `data/raw/dem/seoul_dem.tif`: 서울 DEM
- `data/raw/hydrography/rivers/`: 하천 데이터
- `data/processed/flood_dataset_v1/`: v10 운영 모델 데이터셋 산출물
- `ai/models/flood_xgb_v10_stage3_operational/grid_static_runtime.parquet`: 런타임 격자 static feature
- `backend/data/missing_persons.json`: Safe182 API fallback 실종자 샘플
- `backend/data/shelters.json`: 대피소 샘플 데이터

일부 원본/처리 데이터는 50MB 이상입니다. 공개 저장소에는 최종 시연 재현성을 위해 포함했지만, 운영 서비스에서는 별도 스토리지나 Git LFS 분리를 권장합니다.

## Safety And Privacy

- 모델 점수는 공식 대피 판단을 대체하지 않는 보조 위험 정보입니다.
- 사용자에게 "절대 안전"처럼 확정적인 안전 표현을 하지 않습니다.
- `risk_score`만 단독으로 크게 보여주기보다 위험 단계, 주요 근거, 권장 행동을 함께 표시합니다.
- 반지하 거주, 이동약자, 시각장애 정보는 민감 정보로 취급하고 로그에 원문을 남기지 않습니다.
- 개인정보만으로 `긴급`까지 승격하지 않습니다.
- 네트워크 실패, 위치 권한 거부, 강수 데이터 없음, 모델 응답 오류는 별도 상태로 처리합니다.
- 실종자 관련 이미지와 상세 정보는 발견/신고 지원 목적 외로 사용하지 않는다는 정책을 앱 약관에 포함했습니다.

## Public Release Notes

- 이 public repository는 히스토리 없는 공개용 스냅샷입니다.
- `.env`, `.env.test`, API key, 개인 토큰, 서비스 계정 JSON은 포함하지 않았습니다.
- GitHub contributors 표시는 public snapshot 업로드 이력 기준이며, 실제 팀 역할은 `Team Scope`를 기준으로 정리했습니다.
- 공개용 README는 전체 앱 기능을 설명하기 위해 frontend, backend, AI, data 흐름을 함께 정리했습니다.
