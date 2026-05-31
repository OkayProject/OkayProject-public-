# Seoul Urban Infrastructure Data

This folder stores raw district-level urban infrastructure data for future flood
risk features.

## Current Files

- `seoul_sewer_facilities_2023.csv`
  - Source table: 하수도 및 부대시설 현황, 2023
  - Contents: sewer lengths by type, crossing sewer length, manhole count,
    storm drain inlet count, sewer coverage rate
  - Status: usable as district-level proxy features once grid cells have
    district labels

Normalized outputs can be regenerated with:

```bash
cd ai
.venv/bin/python scripts/prepare_district_context_data.py
```
