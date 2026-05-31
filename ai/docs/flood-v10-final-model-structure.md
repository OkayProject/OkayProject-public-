# flood_xgb_v10_stage3_operational Final Model Structure

작성일: 2026-05-26

이 문서는 현재 운영 기준 침수 위험 모델 `flood_xgb_v10_stage3_operational`의 실제 모델 구조를 설명합니다. v10은 단일 회귀 모델이나 멀티클래스 분류 모델이 아니라, **3개의 binary XGBoost classifier와 threshold/rule 기반 severity 변환**으로 구성된 staged pipeline입니다.

## 결론

- Stage1은 회귀가 아니라 **binary classification**입니다.
- Stage2도 회귀가 아니라 **binary classification**입니다. 출력값을 `risk_score`로 사용하지만, 학습 objective는 `binary:logistic`입니다.
- Stage3도 **binary classification**입니다. `긴급` 판단용 모델이 아니라, `위험` 후보의 false positive를 줄이기 위한 danger filter입니다.
- 최종 `주의`/`위험`/`긴급` 단계는 별도 multiclass 모델이 아니라 score threshold와 Stage3 filter로 결정합니다.
- Stage3는 `danger_candidate <= risk_score < emergency` 구간에서만 실행됩니다. `risk_score >= emergency`이면 Stage3를 거치지 않고 바로 `긴급`입니다.

## 운영 산출물 위치

```text
ai/models/flood_xgb_v10_stage3_operational/
  stage1_fold_0.ubj ... stage1_fold_8.ubj
  stage2_fold_0.ubj ... stage2_fold_8.ubj
  stage3_fold_0.ubj ... stage3_fold_8.ubj
  thresholds.json
  feature_schema.json
  metrics.json
  model_card.md
  grid_static_runtime.parquet
```

런타임에서는 각 stage의 9개 fold 모델 예측을 평균하여 score를 만듭니다.

## 입력 feature

### Stage1 Feature

Stage1은 지형/공간 feature만 사용합니다.

```text
elevation
slope
mean_elevation
relative_low
relative_high
relative_elev
aspect
curvature
distance_to_stream
```

### Stage2 Feature

Stage2는 지형/공간 feature에 강우 feature와 interaction feature를 추가로 사용합니다.

```text
elevation
slope
mean_elevation
relative_low
relative_high
relative_elev
aspect
curvature
distance_to_stream
idw_rainfall_mm
rainfall_1h
rainfall_3h
rainfall_6h
rainfall_24h
cumulative_rainfall_mm
max_hourly_intensity
rainfall_missing_flag
rainfall_ratio_1h_24h
elevation_x_rainfall
relative_low_x_rainfall
```

### Stage3 Feature

Stage3는 Stage2에서 나온 `risk_score`와 강우/지형 feature를 함께 사용합니다.

```text
risk_score
rainfall_1h
rainfall_3h
rainfall_6h
rainfall_24h
cumulative_rainfall_mm
max_hourly_intensity
idw_rainfall_mm
rainfall_ratio_1h_24h
elevation
relative_elev
relative_low
relative_high
slope
curvature
aspect
distance_to_stream
elevation_x_rainfall
relative_low_x_rainfall
mean_elevation
```

## 학습 Target

공통 binary label은 `flooded`입니다.

```text
flooded = flood_overlap_ratio > 0
```

`flood_overlap_ratio`, `flood_overlap_area`, `distance_to_flood_trace_m`는 label 생성, sample weight, 진단에만 사용합니다. 운영 추론 feature로는 사용하지 않습니다.

## Stage별 실제 역할

### Stage1: Candidate Classifier

```text
model type: XGBoost binary classifier
objective: binary:logistic
target: flooded
output: stage1_score
threshold: stage1_candidate = 0.3747505248
```

Stage1은 지형적으로 침수 후보인지 넓게 거르는 gate입니다. Stage1 score가 threshold 미만이면 Stage2 score가 있어도 최종 `risk_score`는 0으로 처리됩니다.

```text
if stage1_score >= stage1_candidate:
    risk_score = stage2_score
else:
    risk_score = 0
```

### Stage2: Risk Score Classifier

```text
model type: XGBoost binary classifier
objective: binary:logistic
target: flooded
output: stage2_score
runtime score name: risk_score
```

Stage2는 강우와 지형을 함께 보고 침수 양성 확률에 가까운 score를 냅니다. 이름은 `risk_score`지만 회귀값이 아니라 binary logistic classifier의 출력입니다.

### Stage3: Danger Filter Classifier

```text
model type: XGBoost binary classifier
objective: binary:logistic
target: flooded
input population: danger candidate rows
threshold: stage3_danger_filter = 0.0124278469
```

Stage3는 `위험` 후보 중 false positive를 줄이기 위한 필터입니다. Stage3는 전체 row를 새로 분류하는 모델이 아니라, `risk_score >= danger_candidate`인 후보를 대상으로 `위험` 유지 여부를 판단합니다.

운영 코드에서는 `risk_score >= emergency`를 먼저 검사합니다. 따라서 Stage3의 실제 실행 구간은 아래와 같습니다.

```text
danger_candidate <= risk_score < emergency
```

즉 Stage3는 `긴급` 여부를 판단하지 않습니다. `긴급`은 별도 Stage3 통과 여부 없이 `risk_score >= emergency` threshold만으로 결정됩니다.

## 최종 Severity 결정

v10 threshold:

```text
caution = 0.005
danger_candidate = 0.0282149129
emergency = 0.2207685262
stage1_candidate = 0.3747505248
stage3_danger_filter = 0.0124278469
```

최종 결정 흐름:

```text
1. Stage1 score 계산
2. Stage2 score 계산
3. stage1_score < stage1_candidate 이면 risk_score = 0
4. stage1_score >= stage1_candidate 이면 risk_score = stage2_score

5. risk_score >= emergency
   -> 긴급
   -> Stage3 실행 안 함

6. danger_candidate <= risk_score < emergency
   -> Stage3 실행
   -> stage3_score >= stage3_danger_filter 이면 위험
   -> stage3_score < stage3_danger_filter 이면 주의

7. risk_score >= caution
   -> 주의

8. 그 외
   -> 일반
```

주의할 점:

- `긴급`은 v10에서 별도 emergency model을 통과하지 않습니다.
- `긴급`은 `risk_score >= emergency` threshold로 결정되며, Stage3를 실행하지 않습니다.
- `위험`은 `danger_candidate <= risk_score < emergency` 구간에서 Stage3 danger filter를 통과해야 합니다.
- `주의`는 recall-first 성격이 강하고, Stage3에서 탈락한 danger 후보도 `주의`로 내려올 수 있습니다.

## v10 모델 구조 다이어그램

```text
위치/격자 feature + 강우 feature
        |
        v
Stage1 XGBoost binary classifier
지형 기반 침수 후보 score
        |
        | stage1_score >= 0.3747505248
        v
Stage2 XGBoost binary classifier
강우+지형 기반 stage2_score
        |
        v
risk_score = stage2_score or 0
        |
        +-- risk_score >= 0.2207685262
        |       -> 긴급
        |       -> Stage3 실행 안 함
        |
        +-- 0.0282149129 <= risk_score < 0.2207685262
        |       |
        |       v
        |   Stage3 XGBoost binary classifier
        |       +-- stage3_score >= 0.0124278469 -> 위험
        |       +-- stage3_score < 0.0124278469  -> 주의
        |
        +-- risk_score >= 0.005
                -> 주의

else -> 일반
```

## 성능 요약

EVT_2025 suspect holdout 제외 LOEO 기준:

| Metric | Value |
|---|---:|
| caution_or_above_recall | 0.9500 |
| danger_or_above_recall | 0.7816 |
| danger_or_above_precision | 0.0190 |
| danger_or_above_alert_rate | 0.3253 |
| major_event_min_danger_recall | 0.6264 |
| major_event_zero_danger_recall_count | 0 |
| emergency_recall | 0.3002 |
| emergency_precision | 0.2060 |
| emergency_alert_rate | 0.0115 |
| emergency_FP | 9,933 |

## 개인화 보정과의 관계

v10 모델 자체에는 개인 특성이 들어가지 않습니다.

```text
personalization_included = false
```

반지하 거주, 이동약자, 시각장애 등은 모델 학습 feature가 아니라 추론 이후 rule-based post-processing에서 반영합니다.

## 금지 Feature

아래 컬럼은 운영 추론 feature로 사용하면 안 됩니다.

```text
flood_overlap_ratio
flood_overlap_area
distance_to_flood_trace_m
is_flooded
y
split
event_id
```

이 값들은 label 또는 진단용이며, 런타임 입력에 포함하면 label leakage가 됩니다.
