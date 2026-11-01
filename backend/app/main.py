from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

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


@app.get("/", include_in_schema=False)
def home():
    return RedirectResponse("/app/index.html")


# The website lives at /app/..., the API stays at /api/...
FRONTEND_DIR = Path(__file__).resolve().parent.parent.parent / "frontend"
app.mount("/app", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
