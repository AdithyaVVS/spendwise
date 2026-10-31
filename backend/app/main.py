from fastapi import FastAPI

from app.routes import auth, categories, transactions

app = FastAPI(title="SpendWise")

app.include_router(auth.router)
app.include_router(categories.router)
app.include_router(transactions.router)


@app.get("/api/health")
def health():
    return {"status": "ok"}
