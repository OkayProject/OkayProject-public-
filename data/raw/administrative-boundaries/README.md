# Seoul Administrative District Data

This folder stores raw Seoul district-level administrative data.

## Current Files

- `seoul_district_admin_area_2025.csv`
  - Source table: 서울특별시 기본통계, 행정구역(구별), 2025
  - Contents: district area, area share, administrative/legal dong counts, tong/ban counts
  - Status: usable as tabular district context data
- `seoul_district_admin_area_2025.xlsx`
  - Same source table kept as the original Excel download

## Important Limitation

These files are not district boundary geometry. They do not contain polygons,
coordinates, or CRS information. To populate `district` for every grid cell in
`data/processed/flood_events.parquet`, add a Seoul district boundary layer such
as SHP, GeoJSON, or GPKG with 25 district polygons.

Normalized outputs can be regenerated with:

```bash
cd ai
.venv/bin/python scripts/prepare_district_context_data.py
```
