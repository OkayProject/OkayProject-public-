# Personalized Score Adjustment Policy

This is a policy note only. It is not included in Stage3 model evaluation.

- User vulnerability fields are not model training features.
- They should be used only after a real user profile API/DB exists.
- Prefer score adjustment over hard level promotion.
- Do not create synthetic personalization scenarios and present them as model performance.

## Example Score Adjustment

- vulnerability_score:
  - lives_in_basement_or_semi_basement: +2
  - has_mobility_difficulty: +2
  - uses_wheelchair_or_walking_aid: +2
  - needs_guardian_support: +1
  - frequently_uses_underground_space: +1
  - is_with_child_or_elderly: +1
- vulnerability_bonus:
  - vulnerability_score == 0: 0
  - vulnerability_score == 1: 0.25 * (danger_threshold - caution_threshold)
  - vulnerability_score == 2: 0.50 * (danger_threshold - caution_threshold)
  - vulnerability_score >= 3: 0.75 * (danger_threshold - caution_threshold)
- final_score = base_score + vulnerability_bonus
- final_level is computed by comparing final_score with thresholds.

## Emergency Guard

If final_score >= emergency_threshold but no strong emergency signal exists,
cap the final level at `위험`.

Strong emergency signal:

- base_score >= emergency_threshold * 0.9
- OR rainfall_6h >= p95 AND relative_elev <= p30
- OR rainfall_24h >= p95 AND distance_to_stream <= 300
- OR cumulative_rainfall_mm >= p95 AND relative_elev <= p30
