# v9 Stage3 Weighted Danger Filter Refinement

- Generated at: 2026-05-25T16:13:51.724081+09:00
- Selected mode: `best`
- Selected policy: `xgboost_medium_overlap_area_weighted_alpha2_max_precision_with_recall_guard`
- Full sweep: `True`
- Model types: `xgboost_shallow,xgboost_medium`
- Weight schemes: `positive_boost_3,positive_boost_5,positive_boost_7,positive_boost_10,overlap_area_weighted_alpha2,overlap_area_weighted_alpha5,overlap_ratio_weighted_alpha2,overlap_ratio_weighted_alpha5,event_balanced_positive,event_balanced_overlap_weighted`

## Policy
- Stage3 trains only on `risk_score >= d20` danger candidates.
- Stage3 target remains the original `is_flooded` binary label.
- `flood_overlap_ratio` and `flood_overlap_area` are used only for sample weights and diagnostics.
- Stage3 failures are lowered to `주의`; emergency remains `e70` and no-rescue.
- Synthetic personalization/high-vulnerability simulation is not included.

## Selected Metrics
- caution_or_above_recall: `0.9500`
- danger_or_above_recall: `0.7816`
- danger_or_above_precision: `0.0190`
- danger_or_above_alert_rate: `0.3253`
- danger_TP / FP / FN: `6710` / `347258` / `1875`
- major_event_min_danger_recall: `0.6264`
- major_event_zero_danger_recall_count: `0`
- emergency_recall: `0.3002`
- emergency_precision: `0.2060`
- emergency_alert_rate: `0.0115`
- emergency_FP / FN: `9933` / `6008`

## Compared With Previous Policies
- v9danger danger alert rate: `0.5019` -> refine `0.3253`
- v9danger danger recall: `0.8000` -> refine `0.7816`
- quick Stage3 danger alert rate: `0.4112` -> refine `0.3253`
- quick Stage3 danger recall: `0.7904` -> refine `0.7816`
- quick Stage3 caution recall: `0.9499` -> refine `0.9500`

## Constraint Status
- caution recall >= 0.95: `True`
- danger recall >= 0.78 preferred: `True`
- danger alert rate <= 0.42: `True`
- major event collapse count == 0: `True`
- major event min danger recall >= 0.50: `True`
- emergency policy preserved: `True`

## Large Positive Recall
- `ratio_top20` danger recall: `0.7880`, emergency recall: `0.3879`
- `ratio_top30` danger recall: `0.8276`, emergency recall: `0.3979`
- `area_top20` danger recall: `0.7880`, emergency recall: `0.3879`
- `area_top30` danger recall: `0.8276`, emergency recall: `0.3979`

## Diagnostics
- Stage3 removed danger FP rows: `191901`
- Stage3 missed positive rows: `158`
- Stage3 retained positive rows: `6710`
- Removed FP / missed positive / retained positive feature profiles are saved as CSV.

## Suspect EVT_2025 Holdout
- caution_or_above_recall: `0.5532`
- danger_or_above_recall: `0.2213`
- emergency_recall: `0.0000`
- EVT_2025 remains a suspect holdout and is not used for train/threshold selection.

## Recommendation
- Recommended as the refined Stage3 operating candidate.
- No personalization performance is reported because real user vulnerability data is not available.
