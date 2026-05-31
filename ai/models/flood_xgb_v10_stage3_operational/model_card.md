# flood_xgb_v10_stage3_operational

Operational package promoted from `flood_xgb_v9_stage3_danger_filter_weighted_refine`.

## Selected Config

- `xgboost_medium_overlap_area_weighted_alpha2_max_precision_with_recall_guard`
- Personalization in model/evaluation: `false`
- EVT_2025_FLOOD: suspect holdout only

## Severity Flow

1. Stage1 estimates candidate/pass probability.
2. Stage2 estimates `risk_score`.
3. `risk_score >= emergency` -> `긴급`.
4. `risk_score >= danger_candidate` -> run Stage3 danger filter.
5. Stage3 pass -> `위험`; Stage3 fail -> `주의`.
6. `risk_score >= caution` -> `주의`; otherwise `일반`.

## Metrics

- caution_or_above_recall: `0.9500`
- danger_or_above_recall: `0.7816`
- danger_or_above_precision: `0.0190`
- danger_or_above_alert_rate: `0.3253`
- major_event_min_danger_recall: `0.6264`
- emergency_recall: `0.3002`
- emergency_precision: `0.2060`
- emergency_alert_rate: `0.0115`
- emergency_FP: `9933`

## Runtime Feature Restrictions

`flood_overlap_ratio`, `flood_overlap_area`, `distance_to_flood_trace_m`, labels, split fields, and `event_id` are not runtime model features.
