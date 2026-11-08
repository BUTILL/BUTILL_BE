import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from app.database.supabase import get_supabase
from app.errors import DomainError
from app.routers.stores import router as stores_router
from app.routers.analyses import router as analyses_router
from app.routers.scenarios import router as scenarios_router


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    load_dotenv(Path(__file__).resolve().parents[1] / ".env", override=False)
    mode = os.getenv("BUTILL_ANALYSIS_ONLY", "0")
    if mode not in ("0", "1"):
        raise RuntimeError("BUTILL_ANALYSIS_ONLY는 0 또는 1이어야 합니다.")
    app.state.analysis_only = mode == "1"
    app.state.supabase = None if app.state.analysis_only else get_supabase()
    yield


app = FastAPI(
    title="BUTILL API",
    description="요식업 매장의 현금흐름·Runway·시나리오 분석 API. preview/compare는 데이터를 저장하지 않습니다.",
    version="0.2.0",
    lifespan=lifespan,
)

load_dotenv(Path(__file__).resolve().parents[1] / ".env", override=False)
origins = [value.strip() for value in os.getenv("BUTILL_CORS_ORIGINS", "https://localhost").split(",") if value.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "PATCH", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)

app.include_router(stores_router, prefix="/api/v1/stores", tags=["매장·경영정보 저장"])
app.include_router(analyses_router, prefix="/api/v1/analyses", tags=["분석 미리보기"])
app.include_router(scenarios_router, prefix="/api/v1/scenarios", tags=["시나리오 비교"])


@app.exception_handler(RequestValidationError)
async def invalid_request(request: Request, exc: RequestValidationError) -> JSONResponse:
    fields = [{"field": ".".join(str(p) for p in e["loc"]), "type": e["type"]} for e in exc.errors()]
    return JSONResponse(status_code=422, content={
        "code": "INVALID_INPUT", "message": "입력값의 누락·형식·범위와 분석기간을 확인하세요.", "fields": fields,
    })


@app.get("/")
def root() -> dict[str, str]:
    return {"message": "BUTILL API Server"}


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.exception_handler(DomainError)
async def domain_error(request: Request, exc: DomainError) -> JSONResponse:
    statuses = {"UNAUTHORIZED": 401, "FORBIDDEN": 403, "NOT_FOUND": 404, "CONFLICT": 409,
                "SAVED_INPUT_INVALID": 409, "CALCULATION_VERSION_MISMATCH": 409, "INVALID_SCENARIO": 422}
    status = statuses.get(exc.code, 503)
    return JSONResponse(status_code=status, content={"code": exc.code, "message": exc.message},
                        headers={"WWW-Authenticate": "Bearer"} if status == 401 else None)
