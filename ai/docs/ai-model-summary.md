# AI Model Summary

최종 운영 모델은 `flood_xgb_v10_stage3_operational`입니다. v10 이외의 실험 모델, 리포트, 학습 스크립트, 회의/기획 문서는 `ai/_archive_non_v10/` 아래에 로컬 보관하고 Git에서는 무시합니다.

## Current Operational Model

- 모델 버전: `flood_xgb_v10_stage3_operational`
- 추론 코드: `ai/src/flood_risk/predict_v10_stage3.py`
- 모델 패키지: `ai/models/flood_xgb_v10_stage3_operational/`
- 운영 리포트: `ai/reports/flood_v10_stage3_operational/`
- smoke test: `backend/tests/test_flood_v10_stage3_smoke.py`

## Runtime Structure

v10은 단일 멀티클래스 모델이 아니라 staged XGBoost pipeline입니다.

1. Stage1 terrain gate: 지형 기반 후보 통과 여부를 판단합니다.
2. Stage2 risk scorer: 지형 + 강수 feature로 `risk_score`를 계산합니다.
3. Stage3 danger filter: `위험` 후보의 오탐을 줄입니다.
4. Threshold policy: `일반`, `주의`, `위험`, `긴급` 단계를 결정합니다.

## Thresholds

```json
{
  "stage1_candidate": 0.3747505247592926,
  "caution": 0.0016348222270607948,
  "danger_candidate": 0.028214912861585617,
  "stage3_danger_filter": 0.012427846901118755,
  "emergency": 0.2207685261964798
}
```

## Metrics

EVT_2025_FLOOD는 데이터 품질 의심 이벤트로 학습과 threshold 선택에서 제외하고 suspect holdout으로만 평가했습니다.

| Metric | Value |
|---|---:|
| 주의 이상 recall | 0.9500 |
| 위험 이상 recall | 0.7816 |
| 위험 이상 precision | 0.0190 |
| 위험 이상 alert rate | 0.3253 |
| major event min 위험 recall | 0.6264 |
| major event 위험 recall 0 이벤트 수 | 0 |
| 긴급 recall | 0.3002 |
| 긴급 precision | 0.2060 |
| 긴급 alert rate | 0.0115 |
| 긴급 FP | 9,933 |

## Backend Selection

Render 또는 로컬 백엔드에서 v10을 명시하려면 아래 중 하나를 사용합니다.

```bash
FLOOD_RISK_MODEL_VERSION=v10_stage3
FLOOD_RISK_MODEL_DIR=ai/models/flood_xgb_v10_stage3_operational
```

백엔드 로더는 `v10`, `v10_stage3`, `flood_xgb_v10_stage3_operational` 값을 v10 predictor로 연결합니다.

## Personalization Policy

- 사용자 취약성 정보는 모델 feature가 아니라 추론 이후 post-processing 입력으로만 취급합니다.
- 백엔드에서 v10 predictor로 넘기는 대표 필드는 `is_basement`, `is_mobility_limited`, `has_visual_impairment`, `has_disability`, `notification_preference`입니다.
- `is_basement`는 백엔드에서 `risk_location_type`이 `home`, `residence`, 또는 `null`일 때만 집 기준 정보로 반영합니다.
- 개인화 보정은 운영 단계의 보수적 점수 보정입니다.
- 개인화 보정 후 점수가 단계 threshold를 넘으면 `위험`, `긴급`을 포함해 해당 단계로 승격될 수 있습니다.
- `has_visual_impairment`는 위험 점수보다 TTS 권장 채널에 우선 반영합니다.

## Notes

- `risk_score`는 공식 대피 판단을 대체하는 절대 확률이 아니라 앱 안내용 상대 위험 점수입니다.
- `flood_overlap_ratio`, `flood_overlap_area`, `distance_to_flood_trace_m`, label, split, event_id는 런타임 feature로 사용하지 않습니다.
