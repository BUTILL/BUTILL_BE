# 매장 저장과 저장형 분석 API

## 인증

앱은 Supabase Auth에서 발급받은 사용자 access token을 요청의 `Authorization: Bearer <access_token>`으로 보낸다.
Swagger에서는 우측 Authorize에 사용자 access token만 입력한다. publishable API 키는 사용자 토큰이 아니다.
서버는 매 요청마다 Supabase Auth에서 토큰을 검증하고 사용자 ID를 얻는다. 요청 본문에서 user_id를 받지 않는다.
현재 로그인·회원가입 화면이나 로그인 대행 API는 제공하지 않는다. 인증 화면의 최종 팀 합의와는 별개의 백엔드 초안이다.
운영에서는 HTTPS를 사용한다. 토큰·비밀번호·키를 채팅이나 코드·로그에 남기지 않는다.

## 실행과 흐름

프로젝트 루트의 `.env`에 SUPABASE_URL과 SUPABASE_KEY가 필요하다.
SUPABASE_KEY는 publishable 또는 호환 가능한 anon 키만 허용한다. secret/service_role 키는 이 경로에서 사용하지 않는다.
`BUTILL_ANALYSIS_ONLY=1`에서도 저장 API는 실제 연결 설정과 사용자 토큰을 요구한다.
설정 없이 사용할 수 있는 경로는 이전의 preview/compare 계산 경로뿐이다.

1. POST `/api/v1/stores`로 매장을 생성한다.
2. PUT `/api/v1/stores/{store_id}/finances`에 `{"input": 분석입력}`을 보내 자금·매출·식재료비·고정비·비정기 지출을 한 번에 저장한다.
3. GET `/api/v1/stores/{store_id}/finances`로 저장한 input과 revision을 조회한다.
4. 수정 시 PUT 본문에 마지막 조회의 revision과 전체 input을 보낸다. 오래된 revision이면 409로 덮어쓰기를 차단한다.
5. POST `/api/v1/stores/{store_id}/analyses`를 본문 없이 호출하면 저장된 입력값으로 계산하고 결과를 저장한다.
6. GET `/api/v1/stores/{store_id}/analyses/{analysis_id}`로 결과·입력 사본·source_revision을 확인한다.
7. POST `/api/v1/stores/{store_id}/scenarios`에 base_analysis_id와 scenario를 보내 저장된 분석 기준의 비교 결과를 저장한다.
8. GET `/api/v1/stores/{store_id}/scenarios/{scenario_id}/comparison`으로 저장된 비교를 조회한다.

매장 목록은 GET `/api/v1/stores?limit=50&offset=0`이며 limit은 1~100이다. 매장 수정은 PATCH `/api/v1/stores/{store_id}`이다.
원본 경영정보나 기준 분석을 변경해도 저장된 분석·시나리오 입력 사본은 자동 변경하지 않는다.
네트워크 오류로 POST 성공 여부를 모를 때는 새 요청으로 별도 이력이 생성될 수 있다. 쓰기 재시도용 멱등성 키는 후속 작업이다.

## 응답 예시의 의미

저장형 응답의 persisted는 true, 계산 미리보기 응답의 persisted는 false이다.
분석 결과의 source_revision은 어떤 경영정보 버전으로 계산했는지 나타낸다.
경영정보 수정과 동시에 분석하더라도 조회한 입력 사본과 버전을 기록한다. 최신 저장 버전을 무조건 분석했다고 보장하지는 않는다.
존재하지 않거나 타인 소유의 매장·분석·시나리오는 404로 처리해 자원 존재 여부를 구분해서 노출하지 않는다.
입력 오류는 422, 토큰 오류는 401, 명시적 권한 거부는 403, 저장 버전 충돌은 409, 연결 장애는 503이다.

## 저장 구조

첫 동작 버전은 public의 stores, startup_plans, analysis_runs, scenarios 네 테이블을 사용한다.
startup_plans.input은 검증된 AnalysisInput 전체를 JSONB로 저장하는 집계 구조이다.
앞서 TRD에서 제안한 개별 월별 매출·비용 테이블과 같은 정규화 구조는 아직 구현하지 않았다.
이 구조는 전체 입력을 한 번의 DB 쓰기로 원자적으로 저장하는 MVP 구현 선택이며 팀 규칙 확정으로 간주하지 않는다.
앱은 경영정보 묶음 API를 사용하므로 후속 정규화 시 가능한 한 같은 요청 형식을 유지한다.
analysis_runs는 입력 사본과 결과, scenarios는 기준 분석과 조건·비교 결과를 각각 한 행에 저장한다.
시나리오의 기준 분석과 매장은 복합 외래키로 일치시킨다.

## 접근 제어와 검증

사용자 API는 요청마다 별도 HTTP Client와 사용자 토큰으로 DB에 접근한다. 공용 SDK Client의 세션을 변경하지 않는다.
서버의 소유권 필터와 DB RLS를 함께 적용한다. 익명 역할에는 네 테이블의 접근 권한을 부여하지 않는다.
경영정보는 본인 매장에 대해서만 조회·추가·수정할 수 있다.
분석·시나리오 이력에는 사용자 UPDATE/DELETE 권한을 부여하지 않는다.
마이그레이션 파일명은 원격 Supabase 이력 버전에 맞췄다.
원격 RLS 검증은 트랜잭션 안에서 임시 사용자 A/B로 수행하고 rollback하여 테스트 레코드를 남기지 않는다.
실제 앱 로그인 세션을 사용한 전체 HTTP 흐름은 별도의 사용자 토큰으로 확인해야 한다.
