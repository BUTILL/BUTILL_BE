# BUTILL_BE 개발 규칙 (공유본)

BUTILL_BE(소상공인 경영 리스크 관리 시스템 백엔드)에서 일하는 **팀원 모두와 각자 쓰는 AI 도구(ChatGPT, Claude 등)가 똑같이 따르는 규칙**이다.
레포: https://github.com/BUTILL/BUTILL_BE

- 규칙끼리 부딪치거나 바꿀 필요가 생기면 이 문서를 먼저 고치고 팀원과 합의한다.
- 아직 정하지 못한 항목은 `TO_DECIDE.md`에 있다. 정해지면 이 문서로 옮긴다.
- 2장 일부와 6·7장은 PR #17(`feature/mvp-analysis`)의 구현 기준으로 정한 내용이다.

---

## 0. 절대 규칙

1. **비밀값은 커밋하지 않는다.** `.env`는 gitignore 대상이다. 새 환경변수는 키 이름만 `.env.example`에 적는다. Supabase 키나 토큰을 AI 채팅창에 붙여넣지 않는다.
2. **`main`에 직접 푸시하지 않는다.** 모든 변경은 PR로 올린다.

---

## 1. Git 브랜치 / 커밋 / PR

작업은 `develop`에서 따온 `feature/*` 브랜치에서 하고, PR로 `develop`에 합친다. `main`에는 릴리스할 때만 `develop`에서 들어간다.

| 브랜치 | 어디서 따내나 | 어디로 합치나 | 용도 |
|---|---|---|---|
| `main` | — | — | 배포용. 릴리스 PR로만 병합 |
| `develop` | `main` | `main` | 통합 브랜치, 기본 작업 기준 |
| `feature/<설명>` | `develop` | `develop` | 기능 개발 |
| `fix/<설명>` | `develop` | `develop` | 버그 수정 |
| `hotfix/<설명>` | `main` | `main` + `develop` | 운영 긴급 수정 |

브랜치 이름은 영문 소문자 kebab-case로 짓는다. 예: `feature/risk-score-api`

### 커밋 메시지

```
<type>: <요약> #<이슈번호>
```

예: `feat: initialize FastAPI backend #1`

| type | 쓰는 경우 |
|---|---|
| `feat` | 기능 추가 |
| `fix` | 버그 수정 |
| `refactor` | 동작 변화 없는 구조 개선 |
| `docs` | 문서 |
| `test` | 테스트 |
| `chore` | 빌드, 설정, 의존성 |
| `style` | 포맷만 변경 |

- 요약은 한글이든 영어든 괜찮다. 한 줄로, 마침표 없이 쓴다.
- 커밋 하나에는 논리적 변경 하나만 담는다.

### PR

- 제목은 커밋 메시지 형식을 따른다.
- 본문에는 변경 내용, 이유, 테스트 방법, 관련 이슈(`Closes #n`)를 적는다.
- 다른 팀원의 리뷰 승인을 받은 뒤 병합하고, 병합한 브랜치는 삭제한다.

---

## 2. 기술 스택 / 환경

| 항목 | 사용 | 비고 |
|---|---|---|
| 언어 | Python **3.11 이상** | `typing.Self`를 쓰므로 3.11 미만은 안 된다. 가상환경은 `venv/`에 두며 gitignore 대상 |
| 웹 프레임워크 | FastAPI 0.142.2 | |
| 서버 | uvicorn[standard] 0.54.0 | |
| 검증 | pydantic 2.13.5 | |
| DB / 인증 | Supabase (supabase 2.32.0) | 클라이언트 규칙은 3장 참고 |
| HTTP | httpx 0.28.1 | 사용자별 Supabase 요청, 테스트 |
| 설정 | python-dotenv 1.2.4 | `.env`에서 읽는다. 이미 설정된 프로세스 환경변수가 `.env`보다 우선한다 |
| 배포 | Render | `Procfile` 사용 |

### 환경변수

| 키 | 설명 |
|---|---|
| `SUPABASE_URL` | Supabase 프로젝트 주소. 사용자 데이터 API는 `https://`만 허용한다 |
| `SUPABASE_KEY` | **publishable(`sb_publishable_`) 또는 anon 키만** 쓴다. secret/service_role 키는 코드에서 거부한다 |
| `BUTILL_ANALYSIS_ONLY` | `1`이면 DB 설정 없이 계산 미리보기 API만 띄운다. 기본값 `0` |
| `BUTILL_CORS_ORIGINS` | 허용 출처, 쉼표로 구분. 기본값 `https://localhost` |

환경변수를 바꾸면 서버를 재시작한다.

### 로컬 실행

```bash
python -m venv venv
venv\Scripts\activate            # Windows (macOS/Linux: source venv/bin/activate)
pip install -r requirements-dev.txt
cp .env.example .env             # 값 채우기
uvicorn app.main:app --reload
```

- DB 없이 계산만 확인할 때: `BUTILL_ANALYSIS_ONLY=1`로 실행한다(PowerShell: `$env:BUTILL_ANALYSIS_ONLY = "1"`).
- 헬스체크: `GET /health` → `{"status": "ok"}`. 서버 상태만 확인하며 DB 연결 성공을 뜻하지 않는다.
- API 문서: http://localhost:8000/docs
- 요청 예시는 `examples/*.json`에 있다.

### 테스트

```bash
python -m unittest discover -s tests -v
python -m pip check
```

- 테스트는 `tests/`에 두고 FastAPI `TestClient`로 실제 라우트까지 확인한다.
- 계산 로직(services)을 바꾸면 테스트를 함께 고치고 위 명령을 통과시킨다.

### 의존성 관리

- `requirements.txt`에는 **직접 쓰는 패키지만** 버전을 고정해서 적는다. `pip freeze` 전체 덤프는 쓰지 않는다.
- 개발/테스트에만 쓰는 패키지는 `requirements-dev.txt`에 적는다(`-r requirements.txt` 포함).
- **파일 인코딩은 UTF-8이어야 한다.** PowerShell에서 `pip freeze > requirements.txt`를 하면 UTF-16으로 저장되므로 하지 않는다.

---

## 3. 코드 구조 / 아키텍처

의존 방향은 **routers → (dependencies) → services → database** 한쪽으로만 흐른다. 거꾸로 import하지 않는다.

```
app/
├── main.py          # FastAPI 앱 생성, 라우터 등록, CORS, 공통 예외 핸들러
├── errors.py        # DomainError(code, message): 도메인 예외
├── dependencies/    # FastAPI Depends: 인증, 사용자별 저장소 주입
├── routers/         # HTTP 계층: 엔드포인트, 요청/응답 매핑만
├── schemas/         # Pydantic 모델: 요청/응답 DTO, 검증
├── services/        # 비즈니스 로직: 현금흐름·Runway·위험·시나리오 계산
└── database/        # Supabase 클라이언트, 데이터 접근
supabase/migrations/ # DB 스키마·RLS 변경 SQL (7장)
tests/               # 테스트
docs/                # API·계산 기준 문서
examples/            # Swagger 요청 예시
```

### 계층 규칙

- **routers**에는 비즈니스 로직을 넣지 않는다. 입력을 검증하고, 서비스를 부르고, 응답을 돌려주는 일만 한다.
- **services**는 FastAPI(`Request`, `HTTPException` 등)에 의존하지 않는다. 오류는 `app.errors.DomainError`로 던지고, `main.py`의 공통 핸들러가 HTTP 응답으로 바꾼다.
- **schemas**는 요청과 응답 모델을 나눈다. DB에서 받은 dict를 그대로 응답하지 않고 응답 모델로 검증한다.
- **database**만 Supabase에 직접 접근한다.

### Supabase 클라이언트

- 공용 Client는 `app/database/supabase.py`의 `get_supabase()`로 앱 시작 시 한 번만 만든다. 공용 Client에는 사용자 로그인, `set_session`, 사용자 JWT를 **절대 적용하지 않는다.**
- 사용자 데이터 접근은 요청마다 사용자 토큰을 넣은 별도 HTTP Client(`app/database/persistence.py`의 `SupabaseRepository`)로 한다. 이 Client는 `app/dependencies/auth.py`의 `get_repository`가 만들어 주입한다.
- 서버의 소유권 필터와 DB RLS를 함께 적용한다. 한쪽에만 의존하지 않는다.

### 컨벤션

| 대상 | 규칙 | 예 |
|---|---|---|
| 파일, 함수, 변수 | `snake_case` | `calc_risk_score` |
| 클래스 | `PascalCase` | `StoreResponse` |
| 상수 | `UPPER_SNAKE_CASE` | `CALCULATION_VERSION` |
| 라우터 파일 | 리소스 하나에 파일 하나 | `routers/stores.py` |
| URL | 복수형 명사, kebab-case, `/api/v1` 접두어 | `/api/v1/stores` |

- 라우터는 `main.py`에서 `app.include_router(..., prefix="/api/v1/...", tags=[...])`로 등록한다.
- 공개 함수에는 타입 힌트를 반드시 단다.

---

## 4. 도메인 원칙 (소상공인 경영 리스크 관리)

1. **사용자는 소상공인이다.** 응답 메시지와 리스크 설명은 전문 용어 대신 사장님이 이해할 수 있는 말로 쓴다.
2. **리스크 판단에는 근거가 따라야 한다.** 위험마다 코드, 발생 월, 금액, 설명을 함께 돌려준다. 근거 없는 위험 점수나 폐업 확률은 만들지 않는다.
3. **리스크 계산 로직은 `services/`에만 둔다.** 기준값은 상수나 설정으로 빼서, 기획이 바뀌면 한곳만 고치면 되게 한다.
4. **경영 데이터는 민감 정보다.** 매출, 비용, 사업자 정보는 본인 데이터만 볼 수 있게 한다(Supabase RLS + 서버에서 소유권 확인). 로그에 원본 값을 남기지 않는다.
5. **금액은 원 단위 정수로 다룬다.** 금액을 부동소수점으로 계산하지 않는다. 비율은 bps(1/10000) 정수로 다룬다.
6. **날짜와 시간은 KST 기준으로 해석하고, 저장은 타임존 정보를 포함해서 한다.**

### 계산 기준 (`mvp-1.0`)

자세한 내용은 `docs/mvp-api.md`의 "계산 기준 초안"을 따른다.

- 분석 시작은 해당 월 1일이고, 분석기간은 1~12개월이다. 보유자금은 시작 월 1일 기준이다.
- 미지급 초기 투자비만 시작 시점에 한 번 뺀다. 이미 낸 투자비와 지급 완료된 비정기 지출은 다시 빼지 않는다.
- 예비자금은 지출이 아니다. `현금잔액 - 예비자금 = 가용잔액`으로 따로 보여 준다.
- 수입과 지출은 월말에 정산한다. 월중 부족과 세금 자동 추정은 계산하지 않는다.
- 월별 `fixed_cost` 변경은 기본 고정비 합계를 **대체**한다(추가 합산이 아니다).
- 잔액 0원은 `depleted`, 음수는 `shortage`이다. 한 번 부족하면 이후 회복해도 최초 부족을 보존한다.
- 시나리오 변동률은 bps 단위(-10000~50000)이고, 금액은 항목별로 원 단위 반올림한다. 시나리오의 추가 지출에는 변동률을 적용하지 않는다.
- 계산 방식이 바뀌면 `app/services/cashflow.py`의 `CALCULATION_VERSION`을 올린다. 버전이 다른 저장 분석으로는 시나리오를 만들 수 없다.

### 위험 코드

| 코드 | 뜻 |
|---|---|
| `INITIAL_CASH_SHORTAGE` | 미지급 초기 투자비를 빼면 시작부터 현금 부족 |
| `OPERATING_DEFICIT` | 월 매출 < 식재료비 + 고정비 |
| `IRREGULAR_OUTFLOW` | 해당 월에 비정기 지출 발생 |
| `RESERVE_NEEDED` | 현금은 있지만 예비자금을 빼면 부족 |
| `CASH_SHORTAGE` | 예상 현금잔액이 음수 |

### 용어집

| 용어 | 의미 | 코드에서 쓰는 이름 |
|---|---|---|
| 매장 | 사용자가 등록한 음식점·카페 | `store` |
| 업종 | 음식점 / 카페 | `business_type`: `restaurant` / `cafe` |
| 매장 상태 | 창업 준비 / 운영 중 | `status`: `planning` / `operating` |
| 경영정보 | 자금·매출·비용 입력 묶음 | `finances` (DB: `startup_plans.input`) |
| 경영정보 버전 | 덮어쓰기 방지용 버전 값 | `revision` |
| 보유자금 | 분석 시작 월 1일의 현금 | `current_cash` |
| 예비자금 | 쓰지 않고 남겨 둘 돈 | `reserve_cash` |
| 미지급 초기 투자비 | 아직 내지 않은 창업 비용 | `unpaid_initial_investment` |
| 월 매출 | 기본 월 매출 | `monthly_sales` |
| 식재료비 | 월 원재료 비용 | `monthly_ingredient_cost`, 품목별 `ingredient_items` |
| 고정비 | 임대료·인건비 등 매달 나가는 돈 | `fixed_expenses` |
| 비정기 지출 | 특정 날짜에 한 번 나가는 돈 | `irregular_expenses` |
| 월별 변경 | 특정 월만 다른 매출·비용 | `monthly_overrides` |
| 현금잔액 / 가용잔액 | 예비자금 포함 / 제외 잔액 | `cash_balance` / `available_balance` |
| Cash Runway | 자금이 버티는 기간과 최초 부족 시점 | `cash_runway`, `available_runway` |
| 분석 | 저장된 경영정보로 한 계산 결과 | `analysis` (DB: `analysis_runs`) |
| 시나리오 | 기본 분석에 매출·비용 변경을 적용한 비교 | `scenario` (DB: `scenarios`) |

---

## 5. AI 도구로 작업할 때

ChatGPT든 Claude든 AI가 만든 코드도 이 문서의 규칙을 똑같이 따른다. 최종 책임은 커밋한 사람에게 있다.

- AI가 만든 코드는 직접 읽고, 로컬에서 실행해 본 뒤에 커밋한다.
- `.env` 값, Supabase 키, 토큰, 실제 사장님 데이터는 AI 채팅창에 넣지 않는다.
- ChatGPT는 레포를 직접 보지 못하므로, 고칠 파일과 관련 파일(예: 해당 router, schema, service)을 함께 붙여넣는다.
- 새 파일은 3장의 계층 규칙에 맞는 위치에 만든다.

---

## 6. API 규칙

### 응답 / 에러 형식

- 성공 응답은 감싸지 않고 응답 모델을 그대로 돌려준다.
- 에러 본문은 항상 `{"code": "...", "message": "..."}`이다. `message`는 사장님이 읽을 수 있는 한국어로 쓴다.
- 입력 검증 오류(422)에만 `fields`가 붙는다. 입력 원본 값은 돌려주지 않는다.
  ```json
  { "code": "INVALID_INPUT", "message": "입력값의 누락·형식·범위와 분석기간을 확인하세요.",
    "fields": [{ "field": "body.current_cash", "type": "missing" }] }
  ```
- 오류 코드와 상태 코드는 `app/main.py`의 공통 핸들러 한곳에서 매핑한다. 새 코드를 추가하면 여기에 등록한다.

| 상태 | 코드 | 쓰는 경우 |
|---|---|---|
| 401 | `UNAUTHORIZED` | 토큰이 없거나 만료되었거나 유효하지 않음 |
| 403 | `FORBIDDEN` | 명시적 권한 거부 |
| 404 | `NOT_FOUND` | 없는 자원 **또는 남의 자원**(존재 여부를 노출하지 않는다) |
| 409 | `CONFLICT`, `SAVED_INPUT_INVALID`, `CALCULATION_VERSION_MISMATCH` | 저장 버전 충돌, 저장된 입력 손상, 계산 버전 불일치 |
| 422 | `INVALID_INPUT`, `INVALID_SCENARIO` | 입력값 오류 |
| 503 | `DB_UNAVAILABLE`, `AUTH_UNAVAILABLE`, `CONFIG_REQUIRED` 등 그 외 | 연결 장애, 설정 누락 |

### 인증

- 앱이 Supabase Auth로 직접 로그인하고, 요청에 `Authorization: Bearer <access_token>`을 보낸다. 백엔드는 로그인·회원가입 API를 제공하지 않는다.
- 서버는 요청마다 Supabase Auth(`/auth/v1/user`)로 토큰을 검증해 사용자 ID를 얻는다. **요청 본문에서 `user_id`를 받지 않는다.**
- 보호 라우트는 `Depends(get_repository)`(`app/dependencies/auth.py`)를 쓴다. 이 의존성이 인증된 사용자의 저장소를 넘겨준다.
- Swagger에서는 Authorize에 사용자 access token만 넣는다. publishable 키는 사용자 토큰이 아니다.

### 동시 수정

- 경영정보 수정은 마지막 조회의 `revision`을 함께 보낸다. 오래된 `revision`이면 409로 막는다.
- 저장된 분석과 시나리오는 입력 사본을 함께 저장하며, 원본 경영정보가 바뀌어도 자동으로 바뀌지 않는다.

### 목록 / 날짜

- 목록 API는 `limit` + `offset`을 쓴다. `limit`은 1~100, 기본 50이다. 응답은 배열이며 `total`은 넣지 않는다.
- 기본 정렬은 최신순(`created_at desc, id desc`)이다.
- 날짜만 있는 값은 `2026-10-06` 형식이고, 월 단위 값은 그 달 1일로 표기한다(`2026-10-01`).
- 시각은 ISO 8601 + 타임존 형식으로 응답한다.

---

## 7. DB 스키마 변경

- 테이블, 컬럼, RLS 정책, 권한 변경은 **모두 `supabase/migrations/*.sql`로 커밋하고 PR로 리뷰한다.** 대시보드에서 직접 바꾸지 않는다.
- 마이그레이션 파일명은 원격 Supabase 이력 버전(`YYYYMMDDHHMMSS_<설명>.sql`)에 맞춘다.
- 사용자 소유 테이블에는 RLS를 켜고, `authenticated` 역할에 필요한 최소 권한만 준다. `anon` 역할에는 사용자 테이블 권한을 주지 않는다.
- 분석·시나리오 이력은 사용자에게 UPDATE/DELETE 권한을 주지 않는다.
