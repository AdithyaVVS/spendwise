from fastapi import FastAPI

app = FastAPI(title="SpendWise")


@app.get("/api/health")
def health():
    return {"status": "ok"}
