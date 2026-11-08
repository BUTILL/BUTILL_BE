# Supabase 연결 모듈

## 실행 준비

`pip install -r requirements.txt`로 실행 의존성을 설치한다.
프로젝트 루트의 `.env`에 `SUPABASE_URL`, `SUPABASE_KEY`를 설정한다.
실제 값은 Git에 올리거나 채팅, 로그에 출력하지 않는다. 기존 프로세스 환경변수가 `.env`보다 우선한다.
키 종류와 인증 방식은 TO_DECIDE.md의 팀 합의에 따른다. 이 구현은 secret/service_role 사용을 결정하지 않는다.

FastAPI 시작 시 `app/database/supabase.py`의 `get_supabase()`가 Client를 한 번 생성하여 `app.state.supabase`에 보관한다.
데이터 접근 계층에서는 같은 함수를 통해 Client를 재사용할 수 있다.
필수 설정이 없거나 URL이 잘못되면 서버 시작이 실패한다. `/health`는 서버 상태만 확인하며 DB 연결 성공을 의미하지 않는다.
환경변수 수정 후 서버를 재시작해야 한다.

공유 Client에는 사용자 로그인, `set_session`, 사용자 JWT 또는 헤더 변경을 적용하지 않는다.
사용자별 인증과 소유권 확인은 후속 인증 설계에서 구현해야 한다. 세션 저장과 자동 갱신은 비활성화했다.

## 검증

`pip install -r requirements-dev.txt`
`python -m unittest discover -s tests -v`

설정 누락, URL 검증, 초기화 오류의 비밀값 비노출, 환경변수 우선순위,
동시 호출 시 한 번 생성, 실제 SDK를 통한 모의 데이터 조회, FastAPI 시작과 기존 경로를 검증한다.
모의 조회는 실제 Supabase 서버 연결이나 RLS 정책 검증을 대신하지 않는다.

## 후속 범위

- #7: 실제 환경변수 저장, `.env.example` 항목 작성과 환경 관리
- #8: 실제 데이터베이스 조회·저장, 실패 응답과 접근 권한 검증

실제 프로젝트 URL 및 키는 이 문서에 포함하지 않는다.
