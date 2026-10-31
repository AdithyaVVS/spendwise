from fastapi import FastAPI

from app.routes import auth

app = FastAPI(title="SpendWise")

app.include_router(auth.router)


@app.get("/api/health")
def health():
    return {"status": "ok"}
