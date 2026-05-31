# v10 Stage1 Metrics Report

This report recreates Stage1 metrics for `flood_xgb_v10_stage3_operational` from the packaged model files.

## Threshold

- stage1_candidate: `0.3747505248`
- trusted events: `EVT_2014_FLOOD, EVT_2016_FLOOD, EVT_2017_FLOOD, EVT_2018_FLOOD, EVT_2019_FLOOD, EVT_2020_FLOOD, EVT_2022_FLOOD, EVT_2023_FLOOD, EVT_2024_FLOOD`
- suspect holdout: `EVT_2025_FLOOD`

## Recreated Fold-Holdout Metrics

The original `stage12_v4_oof_predictions.parquet` threshold-selection artifact is not packaged in the repository. These metrics are recreated from the saved `stage1_fold_N.ubj` files using the v10 LOEO training script order sorted by `event_year,event_id`.

- recall: `0.832266`
- precision: `0.011363`
- pass_rate: `0.577920`
- PR-AUC: `0.013309`
- ROC-AUC: `0.681800`
- TP/FP/FN/TN: `7,145` / `621,638` / `1,440` / `457,787`

## Final Ensemble Apparent Metrics

These are not validation metrics; they apply the saved 9-fold Stage1 ensemble back onto the trusted dataset.

- recall: `0.949796`
- precision: `0.013296`
- pass_rate: `0.563645`
- PR-AUC: `0.030328`

## EVT_2025 Suspect Holdout

- recall: `0.553227`
- precision: `0.009686`
- pass_rate: `0.563645`
- positive_count: `1,193`

## Outputs

- `stage1_metrics_report.json`
- `stage1_event_metrics.csv`
- `stage1_metrics_report.md`
