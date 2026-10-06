from fastapi import FastAPI

app = FastAPI(
    title="BUTILL API",
    description="소상공인 경영 리스크 관리 시스템 API",
    version="0.1.0"
)


@app.get("/")
def root():
    return {"message": "BUTILL API Server"}


@app.get("/health")
def health():
    return {"status": "ok"}