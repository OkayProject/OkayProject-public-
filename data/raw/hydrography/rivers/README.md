# River Source Data

## NGII Continuous Topographic Map 실폭하천

- Raw Seoul file: `seoul/seoul_rivers.gpkg`
- Source meaning: 국토정보지리원 연속수치지형도 실폭하천 polygon layer
- CRS: EPSG:5186
- Coverage: Seoul study-grid clip only
- Original source coverage: national-scale South Korea coverage, not Seoul-only

The national source shapefile is intentionally not kept in this repository
because it is larger than the model needs. The committed raw file keeps only
the Seoul clip used for feature extraction.

Rebuild flood training features with:

```bash
cd ai
uv run python scripts/build_flood_events.py
```
