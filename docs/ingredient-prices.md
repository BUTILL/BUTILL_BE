# 원재료 가격 (aT KAMIS 일별 도·소매 가격)

## 제공 API

`GET /api/v1/ingredient-prices`

| 조건 | 설명 |
|---|---|
| `group` | `common`, `dakgalbi`, `pasta` |
| `item` | 품목 키. 예: `pork_belly` |
| `kind_code`, `unit` | 품종 코드, 단위. 예: `unit=100g` |
| `region_code` | 지역 코드. 지금은 서울(`1101`)만 수집한다 |
| `start_date`, `end_date` | 조회 기간, 최대 1년. 생략하면 `end_date`는 오늘, 시작은 그 28일 전 |

품목별로 서울 소매 시장의 **최근 조사일 평균가**, **1주 전 대비 변동**, 일별 평균을 돌려준다.
이 API는 DB만 읽고 외부 API를 호출하지 않는다. 가격은 아래 내부 수집 작업이 넣는다.
외부 가격은 참고 정보이며 매장 식재료비에 자동 반영하지 않는다(TRD Out-of-Scope).
인증 없이 호출할 수 있다(공개 시세, 사용자 데이터 없음). 공개 범위는 TO_DECIDE #14에서 함께 정한다.

```json
{"collected_at": "2026-11-02T04:15:07Z", "last_success_at": "2026-11-02T04:15:07Z",
 "status": "success", "error_code": null, "stale": false,
 "items": [{"key": "chicken", "name": "닭(육계)", "status": "success", "stale": false, "unit": "1kg",
            "latest": {"price_date": "2026-10-26", "average_price": 4754, "market_count": 1},
            "week_change": {"base_date": "2026-10-19", "base_price": 4424, "change_amount": 330, "change_bps": 746},
            "missing_count": 0, "duplicate_count": 0, "invalid_count": 0}]}
```

- `change_bps`: 1/10000 단위. 746은 +7.46%이다.
- 품목 `status`: 마지막 수집 결과이다. `success`, `no_data`(자료 없음, 결측만 있는 경우 포함), `failed`(수집 실패).
- 전체 `status`: `success`, `partial`, `failed`, `no_data`(수집 이력 없음).
- `missing_count`, `duplicate_count`, `invalid_count`: 마지막 수집에서 결측·중복·형식 오류로 제외한 건수.

## 장애 대응

| 상황 | 응답 |
|---|---|
| 일부 품목 수집 실패 | 해당 품목은 `failed`, `stale: true`, `error_code`와 함께 마지막 정상 가격과 기준일(`latest.price_date`)을 그대로 보여준다 |
| 전체 수집 실패 | 위와 같고 전체 `status`가 `failed`이다. `last_success_at`으로 마지막 성공 시각을 알 수 있다 |
| DB 조회 실패 | 서버 메모리의 마지막 정상 응답을 `stale: true`와 함께 돌려준다. 없으면 품목별 `failed`, 가격은 `null`이다 |

실패 자료는 저장하지 않으므로 0원으로 표시되지 않는다. 사용자가 직접 입력한 비용으로 하는 분석은 가격 수집과 무관하게 동작한다.
정상 응답은 서버 메모리에 10분 캐시한다.

## 내부 수집 작업

```bash
python -m app.jobs.collect_prices
```

- 최근 35일을 다시 받아 저장한다. 같은 품목·날짜·품종·등급·시장은 덮어쓰므로 여러 번 실행해도 중복되지 않는다.
- 전체 실패나 설정 누락이면 종료 코드 1이다. 일부 실패는 수집 이력에 남기고 종료 코드 0이다.
- HTTP 경로가 없다. 서버 환경에서 하루 1회 실행하도록 스케줄러에 등록한다(등록 위치는 배포 환경 확정 후 결정).

| 환경변수 | 쓰는 곳 |
|---|---|
| `SUPABASE_SERVICE_KEY` | 이 수집 작업에서만 쓴다. `sb_secret_` 또는 `service_role` 키만 허용한다. 웹 서버에는 넣지 않는다 |
| `SUPABASE_URL`, `DATA_GO_KR_SERVICE_KEY` | 수집 작업 |
| `SUPABASE_URL`, `SUPABASE_KEY` | 조회 API (publishable 또는 anon 키) |

## 저장 구조

마이그레이션: `supabase/migrations/20261102040000_ingredient_prices.sql`. 먼저 적용되어 있는 `mvp_store_persistence` 마이그레이션의 트리거 함수를 사용한다.

| 테이블 | 내용 |
|---|---|
| `ingredients` | 품목 키, 이름, 출처별 코드, 지역, 유통 구분. 수집 때 `PRICE_ITEMS`로 갱신한다 |
| `ingredient_prices` | 품목별 가격 이력. 가격은 0보다 커야 한다 |
| `price_collection_runs` | 수집 시각, 상태, 건수, 오류 코드, 품목별 결과. 키와 원본 응답은 저장하지 않는다 |

공통 시세라서 `anon`, `authenticated`는 읽기만 할 수 있고 쓰기는 `service_role`만 가능하다. 삭제 권한은 아무에게도 없다.

## 출처

| 항목 | 값 |
|---|---|
| API | 공공데이터포털 `한국농수산식품유통공사_일별 도,소매 가격정보 조회`(15156057) |
| 주소 | `GET https://apis.data.go.kr/B552845/perDay/price` |
| 키 | `.env`의 `DATA_GO_KR_SERVICE_KEY` (공공데이터포털 계정 키, 승인 완료) |
| 필수 조건 | `cond[exmn_ymd::GTE]`, `cond[exmn_ymd::LTE]`(YYYYMMDD), `cond[ctgry_cd::EQ]`, `cond[item_cd::EQ]` |
| 사용 조건 | `cond[se_cd::EQ]=01`(소매), `cond[sgg_cd::EQ]=1101`(서울), 품종·등급 코드 |
| 한도 | 개발 계정 하루 10,000건, 한 번에 최대 1,000건(페이지 나누기 처리) |
| 갱신 | 평일 조사. 토·일·공휴일은 조사하지 않는다(축산물은 주말에도 값이 있다) |

명세서: `일별 도,소매 가격정보 API 명세.xlsx`, 코드표: `(참고)일별 도,소매 가격정보_코드.xlsx` (공공데이터포털 첨부).

## 계산 기준

- 서울 시장별 가격을 날짜별로 평균한다(원 단위 반올림). 축산물(계란·닭)은 시장코드 없이 서울 전체 값 하나가 온다.
- 품종·등급·단위가 다른 가격은 섞지 않는다. 품종을 지정하지 않은 품목(배추·무·방울토마토)은 최근 조사일에 가장 많은 시장에서 조사된 품종을 기준으로 삼는다(계절별 품종 변경 대응).
- 1주 변동은 최근 조사일에서 7일 이전 중 가장 가까운 조사일과 비교한다. 비교할 날이 없으면 `null`이다.
- `-`, 빈 값, 0 이하는 결측이며 0원으로 저장하지 않는다. kg 환산가는 단위가 g·kg일 때만 표시한다.

## 수집 품목 (`app/services/price_items.py`)

2026-10~11 서울 소매 실데이터로 코드와 품종을 확인했다.

| 묶음 | 품목 |
|---|---|
| 공통 | 쌀(20kg), 양파, 대파, 깐마늘(국산), 배추, 계란(특란 30구), 돼지고기 삼겹살(100g) |
| 닭갈비 | 닭(육계), 고구마, 양배추, 깻잎, 부추, 미나리, 고춧가루(국산), 무 |
| 파스타(간소화) | 토마토, 방울토마토, 레몬, 새우(흰다리), 물오징어(원양 냉동), 바지락 |

- aT에 없는 재료: 쑥갓, 바질, 셀러리. 모시조개는 바지락으로 대신한다.
- 식용유(대두유)는 aT 코드표에 없다.
- 가공식품은 대상이 아니다: 식초, 간장, 포도씨유, 치킨스탁, 올리브오일, 버터, 생크림, 베이컨, 엔초비, 파스타면, 토마토홀.
- 닭(육계 kg)은 aT 원자료의 kg 환산가가 조사가와 다르게 온다(4,754원 / 3,032원). 화면에는 조사가(`average_price`)를 쓴다.

## 검증

```bash
python -m unittest tests.test_price_collection tests.test_price_storage -v
```
