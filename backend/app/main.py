from fastapi import FastAPI

from app.routes import auth, budgets, categories, dashboard, importer, transactions

app = FastAPI(title="SpendWise")

app.include_router(auth.router)
app.include_router(categories.router)
app.include_router(transactions.router)
app.include_router(importer.router)
app.include_router(budgets.router)
app.include_router(dashboard.router)


@app.get("/api/health")
def health():
    return {"status": "ok"}
