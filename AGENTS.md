# AGENTS.md

이 문서는 OkayProject 저장소에서 AI, 프론트엔드, 백엔드 작업자가 공통으로 참고하는 작업 가이드입니다. 저장소 루트 기준으로 적용합니다.

## 프로젝트 개요

OkayProject는 개인 맞춤형 재난 및 실종 안전 알림 Android 앱입니다. 현재 우선순위는 침수 위험 예측 MVP를 안정화하고, 이후 앱/백엔드에서 소비할 수 있는 위험 점수와 위험 단계, 알림 메시지 입력값을 제공하는 것입니다.

주요 디렉토리:

- `ai/`: AI 데이터 파이프라인, 모델 학습, 리포트, 스펙
- `ai/scripts/`: 데이터 생성/전처리/모델 학습 스크립트
- `ai/models/`: 학습된 모델 산출물
- `ai/reports/`: 데이터 및 모델 리포트
- `data/raw/`: 원본 공공데이터
- `data/interim/`: 중간 처리 산출물
- `data/processed/`: 학습/연동용 처리 데이터
- `docs/`: 회의록, 기획서, UI/UX 자료

## 공통 규칙

- `.env`, `.env.test`, API key, 개인 토큰, 개인정보성 원본 데이터는 커밋하지 않습니다.
- `ai/.venv`, `.uv-cache`, `__pycache__`, 대용량 임시 파일은 저장소 산출물로 취급하지 않습니다.
- 기존 팀원이 만든 변경사항을 임의로 되돌리지 않습니다. 작업 전 `git status --short`로 현재 상태를 확인합니다.
- 큰 데이터 파일을 추가할 때는 README나 리포트에 왜 필요한지, 어떻게 재생성하는지 남깁니다.
- 최종 사용자에게 "절대 안전"처럼 확정적인 안전 표현을 하지 않습니다. 위험도는 보조 판단 정보이며 공식 대피 판단을 대체하지 않습니다.
- 영역 간 계약은 문서화된 JSON 스키마를 우선합니다. 필드 이름을 바꿀 때는 AI, 백엔드, 프론트가 함께 영향 범위를 확인합니다.

## AI 작업 가이드

현재 AI MVP의 중심은 침수 위험 예측입니다. 모델 학습에 개인 특성은 직접 넣지 않고, 추론 단계에서 규칙 기반 보정으로 반영합니다.

환경 설정:

```bash
cd ai
uv sync
```

기존 `ai/.venv`를 직접 사용할 때:

```bash
cd ai
env UV_CACHE_DIR=../.uv-cache python3 -m uv pip install --python .venv -r requirements.txt
.venv/bin/python -c "import pandas, geopandas, rasterio, sklearn"
pdftotext -v
```

데이터 파이프라인:

```bash
cd ai
uv run python scripts/build_flood_events.py
```

주요 산출물:

- `data/processed/flood_events.parquet`: 표준 침수 이벤트 데이터셋
- `data/processed/dataset.csv`: 기존 학습 스크립트 호환용 CSV
- `data/processed/flood_events_schema.json`: 데이터셋 스키마
- `ai/reports/flood_events_profile.json`: 행 수, 클래스 수, 결측치 리포트
- `ai/reports/flood_events_data_report.md`: 데이터 출처와 사건 기간 문서

현재 표준 데이터셋은 `195,014`행이며 클래스 수는 `y=0: 193,930`, `y=1: 1,084`입니다. 2025년 침수흔적도는 있으나 대응 강수량이 없어 현재 supervised dataset에서는 제외합니다.

모델 학습:

```bash
cd ai
uv run python scripts/train_model.py
```

AI 작업 시 지킬 점:

- `ai/spec.md`의 세션별 목표를 우선 확인합니다.
- 데이터셋에는 `event_year`, `event_id`를 유지해서 연도/사건 누수를 추적할 수 있게 합니다.
- accuracy를 주요 지표로 삼지 않습니다. PR-AUC, recall, precision, F2, Brier score를 우선 검토합니다.
- 임계값은 검증 데이터 기준으로 선택하고 JSON/리포트에 이유를 남깁니다.
- 모델 산출물은 가능하면 `ai/models/<model_name>/` 아래에 `model.pkl`, `thresholds.json`, `metrics.json`, `model_card.md` 형태로 정리합니다.
- `district`는 현재 침수 폴리곤 내부 일부에만 채워질 수 있습니다. 전체 자치구 정보가 필요하면 서울 자치구 경계 데이터가 추가로 필요합니다.

## 프론트엔드 작업 가이드

프론트엔드는 사용자에게 위험 정보를 빠르고 차분하게 전달하는 것이 목표입니다. 공포감을 키우는 표현보다 현재 위험 단계, 근거, 다음 행동을 명확히 보여줍니다.

위험 단계 기본 표시:

- `주의`: 상황 확인, 이동 경로 점검, 추가 강수 확인
- `위험`: 저지대/반지하/침수 취약 위치 회피, 안전한 장소 이동 준비
- `긴급`: 즉시 이동 또는 도움 요청처럼 짧고 직접적인 행동 유도

AI/백엔드에서 받을 수 있는 예측 응답 형태:

```json
{
  "risk_score": 0.0,
  "risk_level": "주의",
  "base_probability": 0.0,
  "personalized_probability": 0.0,
  "thresholds": {
    "caution": 0.0,
    "danger": 0.0,
    "emergency": 0.0
  },
  "reasons": ["고도가 낮음", "최근 강수량이 많음"],
  "recommended_channels": ["push", "tts"],
  "model_version": "flood-v0"
}
```

프론트 작업 시 지킬 점:

- LLM이나 화면 문구가 위험 단계를 자체 결정하지 않습니다. 위험 단계는 AI/백엔드 응답을 그대로 사용합니다.
- `risk_score`만 단독으로 크게 보여주기보다 `risk_level`, 주요 근거, 권장 행동을 함께 보여줍니다.
- 접근성을 고려해 TTS, 큰 글씨, 고대비 상태를 염두에 둡니다.
- 반지하 거주자, 이동약자, 시각장애 사용자에게 필요한 행동/채널 차이를 UI에서 구분할 수 있게 설계합니다.
- 네트워크 실패, 위치 권한 거부, 강수 데이터 없음, 모델 응답 오류 상태를 별도 화면/상태로 처리합니다.
- 디자인 자료는 `docs/design/`을 먼저 확인합니다.

## 백엔드 작업 가이드

백엔드는 앱, AI 모델, 공공데이터 사이의 안정적인 계약 계층입니다. AI 모델의 원시 출력이 앱으로 그대로 새지 않도록 API 응답 스키마를 관리합니다.

권장 추론 입력:

```json
{
  "lat": 37.0,
  "lon": 127.0,
  "rainfall_features": {
    "rainfall_total": 0.0
  },
  "user_profile": {
    "is_basement": false,
    "is_mobility_limited": false,
    "has_visual_impairment": false,
    "notification_preference": "push"
  }
}
```

권장 추론 출력은 프론트엔드 섹션의 예측 응답 형태를 따릅니다.

백엔드 작업 시 지킬 점:

- API key와 외부 서비스 토큰은 환경변수로만 주입합니다.
- 사용자 위치와 개인 취약성 정보는 민감 정보로 취급하고 로그에 원문을 남기지 않습니다.
- AI 모델이 입력 누락이나 잘못된 값을 받으면 구조화된 오류를 반환하게 합니다.
- 모델 파일, threshold, feature schema, model version을 함께 로드하고 응답에 `model_version`을 포함합니다.
- 모델 호출 실패 시 규칙 기반 fallback이나 "현재 위험도 산출 불가" 응답을 명확히 분리합니다.
- LLM은 메시지 표현을 만드는 역할만 맡깁니다. LLM이 위험 단계나 대피 여부를 새로 판단하게 하지 않습니다.
- 실종자 랭킹 데이터와 침수 모델 데이터는 저장소, DB 테이블, API 경로에서 명확히 분리합니다.

## 협업 체크리스트

PR이나 작업 공유 전에 다음을 확인합니다.

- 재생성 명령이나 실행 방법을 README, 리포트, 코드 주석 중 적절한 곳에 남겼는가
- 새 환경변수가 필요하면 `.env.example`에 이름만 추가했는가
- AI 응답/백엔드 API/프론트 타입 중 하나의 필드명이 바뀌었다면 다른 영역도 같이 업데이트했는가
- 테스트 또는 최소 실행 검증 결과를 작업 메모에 남겼는가
- 대용량 산출물이나 원본 데이터 추가 이유가 분명한가
