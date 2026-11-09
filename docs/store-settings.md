# 매장 설정·원재료 단가·알림 API

모두 로그인 필요(`Authorization: Bearer <access_token>`). 다른 사용자의 매장이면 404.
마이그레이션: `supabase/migrations/20261109020000_store_settings.sql` (`store_settings`, `store_ingredient_costs`).
두 테이블은 매장을 지우면 함께 지워진다(`on delete cascade`). 회원탈퇴 RPC도 그대로 동작한다.

## 세금 설정

`GET /api/v1/stores/{store_id}/tax-settings`, `PUT` (본문 = `settings`)

```json
{"store_id": "…", "saved": true,
 "settings": {"business_entity": "individual", "tax_type": "general", "filing_method": "accountant",
              "reserve_method": "monthly", "employees": "yes", "installments": 1},
 "schedule": [{"code": "withholding", "title": "원천세 신고·납부와 4대보험 납부", "due_date": "2026-11-10",
               "days_left": 1, "note": "직원 급여를 지급한 다음 달 10일"}],
 "basis": "세법상 기본 신고·납부 기한 기준 참고 일정입니다. …"}
```

저장한 적이 없으면 `saved: false`와 기본값을 돌려준다. 세액은 계산하지 않는다.

| 화면 항목 | 필드 | 값 (화면 선택지) |
|---|---|---|
| 사업자 형태 | `business_entity` | `individual` 개인, `corporation` 법인, `unregistered` 등록 전, `unknown` 모름 |
| 과세 유형 | `tax_type` | `general` 일반과세자, `simple` 간이과세자, `unknown` 모름 |
| 세무 관리 방식 | `filing_method` | `self` 직접 신고, `accountant` 세무사 이용, `undecided` 미정/모름 |
| 세금 자금 준비 방식 | `reserve_method` | `monthly` 매월 세금 확보, `lump_sum` 납부월 일괄, `unknown` 모름 |
| 직원 고용 여부 | `employees` | `yes` 직원 있음, `no` 없음, `pending` 채용/신고 전 |
| 납부 방식 | `installments` | `1` 일시불, `2` 50%(2회), `3` 33.3%(3회), `4` 25%(4회) |

일정 규칙(다가오는 8건, 주말이면 다음 월요일)

- 개인 일반과세자: 부가세 1/25·7/25 확정, 4/25·10/25 예정고지, 종합소득세 5/31, 중간예납 11/30
- 간이과세자: 부가세 1/25, 예정부과 7/25, 종합소득세
- 법인: 부가세 1/25·4/25·7/25·10/25, 법인세 3/31, 중간예납 8/31
- 직원 있음: 원천세·4대보험 매월 10일
- `모름`은 일반과세자 기준으로 보여준다. 공휴일은 반영하지 않는다.

## 알림·화면 설정

`GET /api/v1/stores/{store_id}/preferences`, `PUT` (본문 = `preferences`)

```json
{"store_id": "…", "saved": false, "preferences": {"runway_alert": true, "ingredient_alert": true, "font_size": "normal"}}
```

`font_size`: `normal` | `large`. 알림은 앱 안 목록으로만 보여주며 발송(카카오 등)은 하지 않는다.

## 매장 원재료 단가

`PUT /api/v1/stores/{store_id}/ingredient-costs` (전체 교체, 최대 30개)

```json
{"items": [{"price_key": "pork_belly", "unit_price": 2900, "monthly_amount": 1200000}, {"price_key": "onion"}]}
```

- `price_key`: `/ingredient-prices` 품목 키. 목록에 없는 키는 422 `UNKNOWN_INGREDIENT`.
- `unit_price`: 매장 입고단가(원, 시세와 같은 단위). 선택.
- `monthly_amount`: 이 원재료에 매달 쓰는 금액(원). 선택. 지출 영향 계산에 쓴다.

`GET` 응답

```json
{"items": [{"price_key": "pork_belly", "name": "돼지고기 삼겹살", "unit": "100g", "market_price": 2866,
            "market_price_date": "2026-11-07", "market_status": "success", "week_change_bps": 487,
            "unit_price": 2900, "unit_price_gap_bps": 119, "monthly_amount": 1200000, "monthly_impact": 58440}],
 "total_monthly_amount": 1200000, "total_monthly_impact": 58440,
 "runway_impact": {"base_available_months": 8, "adjusted_available_months": 8,
                   "base_first_shortage_month": "2027-07-01", "adjusted_first_shortage_month": "2027-07-01",
                   "monthly_cost_increase": 58440},
 "prices_collected_at": "2026-11-08T14:15:23Z"}
```

- `monthly_impact` = `monthly_amount` × 1주 변동률. 시세나 사용금액이 없으면 `null`.
- `unit_price_gap_bps`: 매장 단가가 시세보다 몇 % 비싼지(1/10000 단위).
- `runway_impact`: 저장된 경영정보의 식재료비에 `total_monthly_impact`를 더해 다시 계산한 가용자금 기준 결과. 경영정보가 없으면 `null`. 원본 경영정보는 바꾸지 않는다.

## 알림 목록

`GET /api/v1/stores/{store_id}/notifications` (저장하지 않고 요청 때마다 만든다)

```json
{"generated_at": "…", "notifications": [
  {"type": "runway", "severity": "critical", "title": "가용 자금이 곧 부족해져요", "message": "…",
   "due_date": "2026-11-01", "days_left": null, "target": "home"}]}
```

| type | 조건 | target |
|---|---|---|
| `runway` | `runway_alert` 켜짐, 가용자금 부족 월이 6개월 안 (2개월 안이면 critical) | `home` |
| `ingredient` | `ingredient_alert` 켜짐, 저장한 원재료(없으면 공통 품목) 중 1주 전보다 5% 이상 오른 품목 | `raw_materials` |
| `expense` | 7일 안에 지급일인 고정 지출, 7일 안 미지급 추가 지출 | `calendar` |
| `tax` | 세금 설정을 저장했고 14일 안인 세무 일정 (3일 안이면 warning) | `tax` |

정렬: critical → warning → info, 같은 등급은 남은 날짜순.

## 원재료 주차 추이

`GET /api/v1/ingredient-prices` 품목마다 `weekly`가 추가되었다(월요일 시작 주, 일별 평균의 평균).

```json
"weekly": [{"week_start": "2026-10-12", "average_price": 2810, "days": 7}, …]
```
