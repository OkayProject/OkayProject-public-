# v10 Stage3 Operational Packaging Summary

## Why v9 Stage3 Refined Was Promoted

`flood_xgb_v9_stage3_danger_filter_weighted_refine` reduced the overly broad danger alert volume while keeping recall for major flood events. The selected Stage3 filter keeps the original binary target and uses overlap-based sample weighting, so small/boundary positives are not discarded.

## v10 Performance Summary

- caution 이상 recall: `0.9500`
- danger 이상 recall: `0.7816`
- danger 이상 precision: `0.0190`
- danger 이상 alert rate: `0.3253`
- major event min danger recall: `0.6264`
- major event danger recall 0 이벤트: `0`
- emergency recall: `0.3002`
- emergency precision: `0.2060`
- emergency alert rate: `0.0115`
- emergency FP: `9933`

## Stage3 Danger Filter Inference Flow

1. Runtime input is converted into Stage1/Stage2/Stage3 feature vectors.
2. Stage1 score below `stage1_candidate` gates Stage2 score to 0.
3. Stage2 score is used as `risk_score`.
4. `risk_score >= emergency` returns `긴급`.
5. `risk_score >= danger_candidate` runs Stage3.
6. Stage3 score above `stage3_danger_filter` returns `위험`; otherwise the danger candidate is lowered to `주의`.
7. `risk_score >= caution` returns `주의`; otherwise `일반`.

## Improvement Over v9danger

- danger alert rate: `0.5019 -> 0.3253`
- danger recall: `0.8000 -> 0.7816`
- emergency precision/alert rate/FP preserved at v9danger level.

## EVT_2025 Suspect Holdout Limitation

EVT_2025_FLOOD remains excluded from train and threshold selection because prior diagnostics indicated rainfall/event mismatch risk. It is retained only as a suspect holdout report.

## Personalization Exclusion

No real user vulnerability dataset exists for model evaluation. v10 keeps personalization disabled by default. User vulnerability-based score adjustment is documented as an operating policy only and must be validated after profile/API data exists.


## Backend Grid Runtime Data

The v10 package includes `grid_static_runtime.parquet` for backend inference. It contains nearest-centroid lookup fields and runtime spatial features only; label/diagnostic fields such as `flood_overlap_ratio`, `flood_overlap_area`, and `distance_to_flood_trace_m` are excluded.

## Backend Connection

Set one of the following:

```bash
FLOOD_RISK_MODEL_VERSION=v10_stage3
# or
FLOOD_RISK_MODEL_DIR=ai/models/flood_xgb_v10_stage3_operational
```

The backend response should return `model_version=flood_xgb_v10_stage3_operational` and include `stage3_danger_filter_score` only for danger candidates.

## Gitignore And Tracking Notes

The repository should ignore experimental `ai/models/flood_xgb_v*/` and `ai/reports/flood_v*/` outputs while unignoring the v10 operational package. If older artifacts are already tracked, `.gitignore` alone will not untrack them. Do not run `git rm --cached` automatically; review and run it manually only if the team decides to remove tracked experiment artifacts from Git.
