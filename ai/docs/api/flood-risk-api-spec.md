# Flood Risk API Specification

이 문서는 v10 운영 모델 `flood_xgb_v10_stage3_operational` 기준의 침수 위험 API 계약입니다.

## Endpoint

`POST /api/flood-risk/predict`

프론트엔드는 위치와 사용자 식별자/프로필을 보내고, 백엔드는 현재 강수 provider 또는 요청에 포함된 강수 feature를 사용해 v10 predictor를 호출합니다.

## Request

```json
{
  "user_id": 1,
  "latitude": 37.5446,
  "longitude": 126.9647
}
```

테스트나 provider fallback 용도로 강수 feature를 직접 넘길 수 있습니다.

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

호환용 nested 형식도 허용합니다.

```json
{
  "lat": 37.5446,
  "lon": 126.9647,
  "rainfall_features": {
    "rainfall_total": 72.5,
    "rainfall_1h": 35.0,
    "rainfall_3h": 52.0,
    "rainfall_6h": 80.0,
    "rainfall_24h": 120.0,
    "max_hourly_intensity": 35.0
  },
  "user_profile": {
    "lives_in_basement_or_semi_basement": false,
    "has_mobility_difficulty": false,
    "has_visual_impairment": false,
    "notification_preference": "push"
  }
}
```

## Response

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
    "caution": 0.0016348222270607948,
    "danger": 0.028214912861585617,
    "danger_candidate": 0.028214912861585617,
    "stage3_danger_filter": 0.012427846901118755,
    "emergency": 0.2207685261964798
  },
  "stage1_score": 0.42,
  "stage2_score": 0.1884,
  "stage3_danger_filter_score": 0.04,
  "model_version": "flood_xgb_v10_stage3_operational",
  "data_version": "flood_dataset_v1",
  "model_reasons": ["최근 누적 강수량이 높습니다."],
  "reasons": ["최근 누적 강수량이 높습니다."],
  "recommended_channels": ["push"],
  "personalization": {
    "applied": false,
    "included_in_model": false
  }
}
```

## Risk Level Policy

v10 base level은 아래 순서로 결정합니다.

1. `stage1_score < stage1_candidate`이면 `risk_score = 0`입니다.
2. `risk_score >= emergency`이면 `긴급`입니다.
3. `risk_score >= danger_candidate`이면 Stage3 danger filter를 실행합니다.
4. Stage3 통과 시 `위험`, 실패 시 `주의`입니다.
5. `risk_score >= caution`이면 `주의`, 그 미만은 `일반`입니다.

단계 의미:

| Level | Meaning |
|---|---|
| `일반` | 현재 입력 기준 높은 침수 위험 신호가 제한적입니다. |
| `주의` | recall-first 사전 알림 단계입니다. |
| `위험` | 회피/준비 행동을 안내하는 단계입니다. |
| `긴급` | precision-first 단계이며 강한 행동 안내가 필요합니다. |

## Safety Rules

- `risk_score`는 공식 대피 판단을 대체하는 절대 확률이 아니라 상대 위험 점수입니다.
- 프론트엔드는 위험 단계를 자체 계산하지 않고 `risk_level` 또는 `final_risk_level`을 그대로 사용합니다.
- 사용자 취약성 정보는 모델 feature가 아니라 추론 이후 보정 입력입니다.
- 개인정보만으로 `긴급`까지 승격하지 않습니다.
- 사용자 위치와 취약성 정보는 민감 정보로 취급하고 원문 로그를 남기지 않습니다.

## Backend Configuration

```bash
FLOOD_RISK_MODEL_VERSION=v10_stage3
FLOOD_RISK_MODEL_DIR=ai/models/flood_xgb_v10_stage3_operational
```
