# BUTILL_BE 개발 규칙 (공유본)

BUTILL_BE(소상공인 경영 리스크 관리 시스템 백엔드)에서 일하는 **팀원 모두와 각자 쓰는 AI 도구(ChatGPT, Claude 등)가 똑같이 따르는 규칙**이다.
레포: https://github.com/BUTILL/BUTILL_BE

- 규칙끼리 부딪치거나 바꿀 필요가 생기면 이 문서를 먼저 고치고 팀원과 합의한다.

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
| 언어 | Python 3.x | 가상환경은 `venv/`에 두며 gitignore 대상 |
| 웹 프레임워크 | FastAPI 0.142.2 | |
| 서버 | uvicorn[standard] 0.54.0 | |
| DB / 인증 | Supabase | 클라이언트는 `app/database/supabase.py`에서 한 번만 만든다 |
| 설정 | python-dotenv 1.2.4 | `.env`에서 읽는다. 코드에 하드코딩하지 않는다 |

### 로컬 실행

```bash
python -m venv venv
venv\Scripts\activate            # Windows (macOS/Linux: source venv/bin/activate)
pip install -r requirements.txt
cp .env.example .env             # 값 채우기
uvicorn app.main:app --reload
```

- 헬스체크: `GET /health` → `{"status": "ok"}`
- API 문서: http://localhost:8000/docs

### 의존성 관리

- `requirements.txt`에는 **직접 쓰는 패키지만** 버전을 고정해서 적는다. `pip freeze` 전체 덤프는 쓰지 않는다.
- **파일 인코딩은 UTF-8이어야 한다.** PowerShell에서 `pip freeze > requirements.txt`를 하면 UTF-16으로 저장되므로 하지 않는다.
- 현재 알려진 문제: `requirements.txt`가 UTF-16으로 커밋되어 있고, supabase 패키지가 빠져 있다.

---

## 3. 코드 구조 / 아키텍처

의존 방향은 **routers → services → database** 한쪽으로만 흐른다. 거꾸로 import하지 않는다.

```
app/
├── main.py          # FastAPI 앱 생성, 라우터 등록, 미들웨어
├── routers/         # HTTP 계층: 엔드포인트, 요청/응답 매핑만
├── schemas/         # Pydantic 모델: 요청/응답 DTO, 검증
├── services/        # 비즈니스 로직: 리스크 계산, 도메인 처리
└── database/        # Supabase 클라이언트, 데이터 접근
```

### 계층 규칙

- **routers**에는 비즈니스 로직을 넣지 않는다. 입력을 검증하고, 서비스를 부르고, 응답을 돌려주는 일만 한다.
- **services**는 FastAPI(`Request`, `HTTPException` 등)에 의존하지 않는다. 오류는 도메인 예외로 던지고 router에서 HTTP 응답으로 바꾼다.
- **schemas**는 요청과 응답 모델을 나눈다(`XxxCreate`, `XxxUpdate`, `XxxResponse`). DB에서 받은 dict를 그대로 응답하지 않는다.
- **database**만 Supabase 클라이언트를 직접 다룬다.

### 컨벤션

| 대상 | 규칙 | 예 |
|---|---|---|
| 파일, 함수, 변수 | `snake_case` | `calc_risk_score` |
| 클래스 | `PascalCase` | `StoreResponse` |
| 상수 | `UPPER_SNAKE_CASE` | `RISK_THRESHOLD` |
| 라우터 파일 | 리소스 하나에 파일 하나 | `routers/stores.py` |
| URL | 복수형 명사, kebab-case, `/api/v1` 접두어 | `/api/v1/stores` |

- 라우터는 `main.py`에서 `app.include_router(..., prefix="/api/v1/...", tags=[...])`로 등록한다.
- 공개 함수에는 타입 힌트를 반드시 단다.

---

## 4. 도메인 원칙 (소상공인 경영 리스크 관리)

아래는 지금 기준의 기본 원칙이다. 서비스 기획이 확정되면 더 구체적으로 채운다.

1. **사용자는 소상공인이다.** 응답 메시지와 리스크 설명은 전문 용어 대신 사장님이 이해할 수 있는 말로 쓴다.
2. **리스크 판단에는 근거가 따라야 한다.** 점수나 등급을 돌려줄 때는 어떤 지표가 어떤 기준을 넘었는지 함께 돌려준다.
3. **리스크 계산 로직은 `services/`에만 둔다.** 임계치 같은 기준값은 상수나 설정으로 빼서, 기획이 바뀌면 한곳만 고치면 되게 한다.
4. **경영 데이터는 민감 정보다.** 매출, 비용, 사업자 정보는 본인 데이터만 볼 수 있게 한다(Supabase RLS + 서버에서 소유권 확인). 로그에 원본 값을 남기지 않는다.
5. **금액은 원 단위 정수로 다룬다.** 금액을 부동소수점으로 계산하지 않는다.
6. **날짜와 시간은 KST 기준으로 해석하고, 저장은 타임존 정보를 포함해서 한다.**

### 용어집

| 용어 | 의미 | 코드에서 쓰는 이름 |
|---|---|---|
| _(추가 예정)_ | | |

---

## 5. AI 도구로 작업할 때

ChatGPT든 Claude든 AI가 만든 코드도 이 문서의 규칙을 똑같이 따른다. 최종 책임은 커밋한 사람에게 있다.

- AI가 만든 코드는 직접 읽고, 로컬에서 실행해 본 뒤에 커밋한다.
- `.env` 값, Supabase 키, 토큰, 실제 사장님 데이터는 AI 채팅창에 넣지 않는다.
- ChatGPT는 레포를 직접 보지 못하므로, 고칠 파일과 관련 파일(예: 해당 router, schema, service)을 함께 붙여넣는다.
- 새 파일은 3장의 계층 규칙에 맞는 위치에 만든다.
