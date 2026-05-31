# Seoul Rainfall Raw Data

이 폴더는 침수 위험 데이터셋 생성에 쓰는 서울시 강우량 다운로드 원자료를 보관합니다. API 호출로 새로 받은 파일은 사용하지 않습니다.

## Directory Layout

| Path | Role | Files | Size | Notes |
| --- | --- | ---: | ---: | --- |
| `seoul_city_2011_2020/` | Primary | 466 | 591M | 2011-2020 서울시 강우량 관측소별 CSV 묶음. 현재 2014, 2016-2020 이벤트에 사용합니다. |
| `seoul_city_2021_2024/` | Primary | 192 | 251M | 2021-2024 서울시 강우량 관측소별 CSV 묶음. 현재 2022-2024 이벤트에 사용합니다. |
| `seoul_city_2020_monthly/` | Reference fallback | 12 | 85M | 월별 2020 다운로드 원자료. 기본 파이프라인은 `seoul_city_2011_2020/`을 우선 사용합니다. |
| `seoul_city_2025_monthly/` | Primary | 12 | 96M | 월별 2025 다운로드 원자료. 현재 2025-08-13~14, 2025-08-21~24 침수 이벤트에 사용합니다. |
| `archives/` | Download archives | 3 | 72M | 위 CSV 묶음을 만들 때 사용한 원본 zip 보관용입니다. |

## Pipeline Priority

`ai/scripts/build_flood_events.py`는 연도별로 아래 순서의 다운로드 원자료를 우선 사용합니다.

1. 2011-2020년: `data/raw/rainfall/seoul_city_2011_2020/`
2. 2021-2024년: `data/raw/rainfall/seoul_city_2021_2024/`
3. 2025년 월별 후보 원자료: `data/raw/rainfall/seoul_city_2025_monthly/`
4. 2020년 fallback: `data/raw/rainfall/seoul_city_2020_monthly/`

CSV 컬럼은 `강우량계명`, `시간`, `10분우량`을 표준으로 봅니다. 일부 과거 파일의 `10분강우량` 컬럼은 빌드 단계에서 `10분우량`으로 정규화합니다.
2025 월별 파일의 `자료수집 시각` 컬럼은 가공 단계에서 `시간`으로 정규화합니다.

## Commit Policy

이 원자료 묶음과 다운로드 zip은 대용량 파일이므로 `.gitignore`에서 제외합니다. 원자료를 다시 배치해야 할 때는 위 폴더명을 유지해야 재생성 스크립트가 그대로 동작합니다.
