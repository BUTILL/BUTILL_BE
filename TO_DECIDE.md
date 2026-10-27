# 같이 정해야 할 것들

`CONVENTION.md`에 넣기 전에 팀원과 합의해야 하는 항목이다.
항목마다 선택지와 권장안을 적어 두었다. 정해지면 **결정** 칸을 채우고 `CONVENTION.md`에 옮긴 뒤 여기서 체크한다.

PR #17(`feature/mvp-analysis`)의 구현으로 정해진 내용은 `CONVENTION.md`로 옮겼다. 아래에는 **남은 결정**만 남긴다.
옮긴 내용에 이견이 있으면 해당 항목을 다시 열고 이 문서에 적는다.

| # | 항목 | 우선순위 | 상태 |
|---|---|---|---|
| 1 | API 응답 / 에러 형식 | 높음 | [x] → CONVENTION 6장 |
| 2 | 인증 방식 | 높음 | [x] → CONVENTION 6장 |
| 3 | DB 스키마 변경 관리 | 높음 | [x] → CONVENTION 7장 |
| 4 | 환경 분리 (Supabase 프로젝트, 키 관리) | 높음 | [ ] 일부 결정 |
| 5 | 테스트 | 중간 | [ ] 일부 결정 |
| 6 | 코드 포맷 / 린트 | 중간 | [ ] |
| 7 | Python 버전 | 중간 | [ ] 일부 결정 |
| 8 | 이슈 / 작업 분담 흐름 | 중간 | [ ] 일부 결정 |
| 9 | PR 리뷰 / 머지 규칙 | 중간 | [ ] |
| 10 | 페이지네이션 / 날짜 형식 | 중간 | [ ] 일부 결정 |
| 11 | 도메인 모델 / 용어집 | 기획 후 | [x] → CONVENTION 4장 |
| 12 | 로깅 | 낮음 | [ ] |
| 13 | 경영정보 저장 구조 (JSONB / 정규화) | 높음 | [ ] |
| 14 | 로그인 없이 쓰는 API 공개 범위 | 중간 | [ ] |
| 15 | 스키마 이름 / 라우터 배치 규칙 | 중간 | [ ] |
| 16 | 지원사업 정보 기능 범위 | 높음 | [ ] |
| 17 | 외부 데이터 저장 방식 (캐시 / DB) | 중간 | [ ] |

우선순위 "높음"은 둘이 따로 개발을 시작하기 **전에** 정해야 하는 것이다.

---

## 4. 환경 분리 (Supabase 프로젝트, 키 관리)

**정해진 것 (CONVENTION 2장):** 사용자 데이터 API에는 publishable/anon 키만 쓴다. secret/service_role 키는 코드에서 거부한다. 환경변수 이름은 `SUPABASE_URL`, `SUPABASE_KEY`, `BUTILL_ANALYSIS_ONLY`, `BUTILL_CORS_ORIGINS`이다. 외부 API 키는 `DATA_GO_KR_SERVICE_KEY`, `BIZINFO_API_KEY`, `SEOUL_OPENAPI_KEY`로 서버 `.env`에만 둔다.

**남은 것**
- 개발용 Supabase 프로젝트: 공용 하나 / 각자 / 로컬(`supabase start`)
- 운영 프로젝트와 키는 누가 관리하나
- `.env` 값은 어떻게 공유하나 (메신저 금지, 비밀번호 관리자 등). 외부 API 키가 평문 파일(`api.json` 등)과 채팅으로 공유된 적이 있으니 재발급 여부도 정한다.
- KAMIS 가격 수집처럼 사용자 토큰 없이 돌아야 하는 서버 작업에 secret 키를 쓸지, 쓴다면 어디까지 쓸지
- 운영 CORS 허용 출처(`BUTILL_CORS_ORIGINS`) 값

**권장:** 개발용 공용 프로젝트 1개 + 운영 1개로 나눈다. 운영 키는 한 명이 관리한다. secret 키는 내부 수집 작업에서만 쓰고 사용자 API와 섞지 않는다.

**결정:**

---

## 5. 테스트

**정해진 것 (CONVENTION 2장):** 테스트는 `tests/`에 두고 FastAPI `TestClient`를 쓴다. 실행 명령은 `python -m unittest discover -s tests -v`와 `python -m pip check`이다.

**남은 것**
- 도구: 지금처럼 `unittest`를 쓸지, `pytest`로 바꿀지 (`pytest`는 기존 unittest 테스트도 그대로 실행한다)
- `tests/`가 `app/` 구조를 따르게 할지 (지금은 평면 구조)
- 범위: services 단위 테스트를 필수로 할지, router 테스트는 선택으로 할지
- PR 전에 테스트 통과를 필수로 할지, CI(GitHub Actions)로 강제할지

**권장:** 리스크 계산 같은 services 로직은 테스트를 필수로 하고, PR 전에 테스트를 통과시킨다.

**결정:**

---

## 6. 코드 포맷 / 린트

**왜:** 포맷이 다르면 diff에 의미 없는 변경이 섞인다.

**선택지**
- A. `ruff format` + `ruff check` (하나로 포맷과 린트를 함께 처리)
- B. `black` + `flake8` + `isort`

**권장:** A. `pyproject.toml`에 설정하고, 원하면 pre-commit 훅으로 강제한다.

**결정:**

---

## 7. Python 버전

**정해진 것 (CONVENTION 2장):** 3.11 이상. 코드가 `typing.Self`를 쓴다.

**남은 것:** 3.11 / 3.12 / 3.13 중 하나로 고정. 레포에 `.python-version`을 추가할지, Render 배포 버전을 어떻게 지정할지도 정한다.

**결정:**

---

## 8. 이슈 / 작업 분담 흐름

**정해진 것 (CONVENTION 1장):** PR 본문에 `Closes #n`으로 이슈를 연결한다.

**남은 것**
- 작업 전에 이슈를 먼저 만드나 (커밋 형식에 `#이슈번호`가 들어간다)
- 브랜치 이름에 이슈 번호를 넣을지 (`feature/<이슈번호>-<설명>`)
- 담당자 지정, 라벨(`feat`, `bug`, `docs` …)을 쓸지
- 이슈/PR 템플릿을 둘지 (`.github/ISSUE_TEMPLATE`, `pull_request_template.md`)
- 진행 상황은 어디서 보나 (GitHub Projects 보드, 프로그램목록 엑셀 등)

**권장:** 이슈를 먼저 만들고 → 브랜치 `feature/<이슈번호>-<설명>` → PR 본문에 `Closes #n`.

**결정:**

---

## 9. PR 리뷰 / 머지 규칙

**왜:** 2명이면 "상대 승인 필수"가 병목이 될 수 있다.

**정할 것**
- 승인 필수 여부, 급할 때 셀프 머지를 허용할지
- 머지 방식: Squash / Merge commit / Rebase
- `main`, `develop`에 브랜치 보호 규칙을 걸지

**권장:** 상대 승인 1명을 원칙으로 하되, 24시간 안에 리뷰가 없으면 셀프 머지를 허용한다. `develop`으로 들어가는 PR은 Squash로 머지한다.

**결정:**

---

## 10. 페이지네이션 / 날짜 형식

**정해진 것 (CONVENTION 6장):** 목록은 `limit`(1~100, 기본 50) + `offset`이고 `total`은 넣지 않는다. 날짜만 있는 값은 `2026-10-06`, 월 단위 값은 그 달 1일로 표기한다.

**남은 것**
- 시각(`created_at`, `updated_at`)을 DB 값 그대로(UTC) 내보낼지, KST(`+09:00`)로 바꿔 내보낼지
- 앱에서 전체 개수가 필요해지면 `total`을 추가할지

**권장:** 응답 시각은 KST(`2026-10-06T15:00:00+09:00`)로 통일한다.

**결정:**

---

## 12. 로깅

**현재 상태:** `Procfile`에서 access log를 끄고(`--no-access-log`), `*.log`는 gitignore 대상이다. 로거 설정은 아직 없다.

**정할 것**
- 표준 `logging`을 쓸지 다른 라이브러리를 쓸지
- 로그 레벨 기준 (INFO / WARNING / ERROR)
- 요청 ID를 남길지 (TRD SEC-07: 요청 ID·오류 코드·처리시간 중심)
- 마스킹 대상 (금액, 사업자번호, 토큰 등)과 보존 기간

**권장:** 표준 `logging`을 쓰고, 요청 ID·오류 코드·처리시간만 남긴다. 민감 값은 남기지 않는다.

**결정:**

---

## 13. 경영정보 저장 구조 (JSONB / 정규화)

**왜:** 설계 문서와 구현이 다르다. `BUTILL_ERD.md`와 TRD는 `fixed_expenses`, `irregular_expenses`, `monthly_sales` 같은 정규화 테이블을 두지만, PR #17은 경영정보 전체를 `startup_plans.input` JSONB 한 덩어리로 저장한다. API도 TRD의 `/startup-plan`, `/fixed-expenses` 등 대신 `PUT/GET /stores/{id}/finances` 하나다.

**정할 것**
- MVP 동안 JSONB 구조를 유지할지, 정규화 테이블로 바꿀지
- 바꾼다면 언제 바꿀지, `/finances` 요청 형식은 유지할지
- ERD, TRD, 프로그램목록(IF-006~021) 중 무엇을 기준 문서로 고칠지

**선택지**
- A. MVP는 JSONB 유지. 한 번에 원자적으로 저장되고 이미 동작한다. 항목별 조회·통계가 필요해지면 정규화한다.
- B. 지금 정규화. 문서와 맞지만 API와 테스트를 다시 만들어야 한다.

**권장:** A. 대신 ERD와 프로그램목록을 실제 구조에 맞게 고친다.

**결정:**

---

## 14. 로그인 없이 쓰는 API 공개 범위

**왜:** 아래 API는 인증 없이 누구나 호출할 수 있다. 사용자 데이터는 없지만 운영 서버에 그대로 열어 둘지 정해야 한다.
- 계산 미리보기: `POST /api/v1/analyses/preview`, `POST /api/v1/scenarios/compare`
- 외부 공개 자료: `GET /api/v1/ingredient-prices`, `GET /api/v1/support-programs` (외부 API 하루 호출 한도를 쓰므로 캐시로 보호 중)

**정할 것**
- 운영에서도 인증 없이 열어 둘지, 로그인 사용자만 쓰게 할지, 개발 환경에서만 열지
- 열어 둔다면 요청 횟수 제한을 둘지

**결정:**

---

## 15. 스키마 이름 / 라우터 배치 규칙

**왜:** CONVENTION 3장의 규칙과 PR #17 코드가 다르다.
- 스키마 이름: 규칙은 `XxxCreate` / `XxxUpdate` / `XxxResponse`인데, 코드는 `AnalysisInput`, `FinanceSave`, `ComparisonInput`, `ScenarioInput`도 쓴다.
- 라우터: 규칙은 "리소스 하나에 파일 하나"인데, 저장형 분석·시나리오 API가 `routers/stores.py` 안에 하위 경로로 있다. `routers/analyses.py`, `routers/scenarios.py`는 미리보기 전용이다.

**선택지**
- A. 규칙을 넓힌다: 계산 입력은 `XxxInput`을 허용하고, 매장 하위 자원은 `stores.py`에 둘 수 있게 한다.
- B. 코드를 규칙에 맞춘다: 이름을 바꾸고 하위 자원 라우터를 파일별로 나눈다.

**결정:**

---

## 16. 지원사업 정보 기능 범위

**왜:** 지원사업 공고 조회(#20)는 PRD·TRD·프로그램목록에 없는 기능이다. Charter는 "정부 지원사업 신청 대행"을 범위 밖으로 둔다.

**정할 것**
- MVP에 넣을지, 넣는다면 프로그램목록·화면(UI)에 어떻게 추가할지
- 범위: 공고 목록과 신청 링크 안내까지만 할지(현재 구현), 업종·업력별 맞춤 추천까지 할지
- 필터 기준: 지금은 "소상공인 대상 + 서울 해당" 공고만 남긴다(전체 1,451건 중 약 50건). 외식업 관련 공고로 더 좁힐지

**권장:** 공고 목록과 링크 안내까지만 MVP에 넣고, 맞춤 추천은 후속으로 둔다.

**결정:**

---

## 17. 외부 데이터 저장 방식 (캐시 / DB)

**왜:** 원재료 가격·지원사업 정보는 지금 서버 메모리에 3시간 캐시한다. TRD는 가격을 `ingredients`, `ingredient_prices`, `price_collection_runs` 테이블에 저장하도록 설계했다.

**정할 것**
- MVP를 캐시로 둘지, DB에 저장하고 정기 수집 작업(평일 저녁 1회 등)을 둘지
- DB에 저장한다면 사용자 토큰 없이 쓰는 서버 작업용 키(#4)를 어떻게 관리할지
- 서버를 여러 대 띄우거나 재시작하면 캐시가 비는 점을 받아들일지

**선택지**
- A. MVP는 캐시 유지. 구현이 끝났고 키 문제가 없다. 첫 호출이 약 10초 걸린다.
- B. DB 저장 + 정기 수집. 설계 문서와 맞고 응답이 빠르지만, 서버 작업용 키와 수집 실행 환경을 정해야 한다.

**권장:** 시연까지는 A, 운영을 고려하면 B로 옮긴다.

**결정:**

---

## 결정 기록

| # | 결정 | 근거 | 옮긴 곳 |
|---|---|---|---|
| 1 | A안. 성공은 그대로 반환, 에러는 `{code, message}`(422는 `fields` 추가), 상태 코드는 공통 핸들러 한곳에서 매핑 | PR #17 `app/main.py` | CONVENTION 6장 |
| 2 | A안. 앱이 Supabase Auth로 로그인, 백엔드는 Bearer 토큰을 요청마다 검증, `Depends(get_repository)`로 통일 | PR #17 `app/dependencies/auth.py` | CONVENTION 6장 |
| 3 | A안. `supabase/migrations/*.sql`을 커밋하고 PR로 리뷰 | PR #17 마이그레이션 | CONVENTION 7장 |
| 11 | 핵심 개체(매장·경영정보·분석·시나리오), 위험 코드 5종, 계산 기준 `mvp-1.0`, 용어집 | PR #17 `app/schemas/`, `docs/mvp-api.md` | CONVENTION 4장 |
