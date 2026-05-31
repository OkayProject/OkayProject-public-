# Flood Data Quality Diagnostics

- Generated at: 2026-05-24T23:20:20.760355+09:00
- v7 best non-baseline candidate used for score diagnostic: `D_stage2_reweighted/fn2x2_evt2025x3`

## 1. 공간 feature 오류 여부
- 전체 기준 비정상 플래그:
  - `flow_accumulation`: all_missing
- `flow_accumulation`은 원본 `grid_static`에서 전부 결측인 상태입니다. 모델 feature로 쓰면 정보량이 없습니다.
- `distance_to_stream`은 평균 약 509.2m, 최대 약 3188.6m로 정상 범위입니다.

## 2. EVT_2025_FLOOD 실패 원인
- v6 기준 EVT_2025 recall: 0.0000
- streamfix v7 best 후보 기준 EVT_2025 recall: 0.0000
- EVT_2025 내부 v6 final_score ROC-AUC: 0.5221, PR-AUC: 0.0106
- EVT_2025 내부 streamfix v7 final_score ROC-AUC: 0.4885, PR-AUC: 0.0096
- EVT_2025 positive rainfall_total 평균은 57.5mm로, EVT_2022 positive 500.3mm 및 v6 TP 534.7mm보다 매우 낮습니다.
- EVT_2025 negative rainfall_total 평균은 60.2mm로, 2025 내부에서는 positive가 negative보다 오히려 낮습니다.
- EVT_2025 positive 평균 고도는 113.0m로 v6 TP 평균 26.2m보다 높고, 평균 하천거리는 699.2m로 v6 TP 평균 810.1m와 같은 방향의 저위험 feature는 아닙니다.
- v6 final_score 평균은 2025 positive 0.0333, negative 0.0344입니다.
- streamfix v7 final_score 평균은 2025 positive 0.0744, negative 0.0768입니다.
- 따라서 EVT_2025는 threshold만 낮추면 해결되는 모양이 아니라, event 내부 ranking도 거의 무작위 또는 역전된 상태입니다.

## 3. 데이터/모델/threshold 판단
- CRS 관점에서는 하천 거리 문제는 수정됐고, grid 좌표와 DEM/하천/침수흔적도는 같은 서울 TM 계열 projected 좌표로 처리된 것으로 보입니다.
- 가장 가능성 높은 실패 원인은 2025 이벤트의 강수 기간/강수 원천 매칭 문제입니다. 2025 침수 positive가 학습된 침수 패턴에 비해 강수량이 너무 낮게 들어가 있습니다.
- 두 번째 원인은 2025 침수흔적도 라벨의 공간 분포 차이입니다. 2025 positive는 평균 고도가 높고 하천거리도 TP와 크게 다르지 않아, 기존 feature 조합으로는 positive/negative ranking이 되지 않습니다.
- 결론적으로 현재 증상은 단순 threshold 문제가 아니라 데이터 품질과 event generalization 문제가 섞여 있습니다.

## 4. Split 방식
- 진단 결과: v6 and v7 train/evaluate with one event_id held out at a time (manual Leave-One-Event-Out).
- random row-level split은 확인되지 않았고, event generalization 평가 방식은 적절합니다.

## 5. 다음 단계
- 다음 모델 실험으로 바로 넘어가기보다 EVT_2025의 rain_start/end, 원시 강수 파일 시간 범위, 침수흔적도 발생일, 2025 라벨 좌표/면적 분포를 먼저 수정/검증하는 쪽을 권장합니다.
