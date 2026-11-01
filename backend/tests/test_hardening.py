import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.config import Settings, settings
from app.database import get_db
from app.limiter import limiter
from app.main import app

FRONTEND = Path(__file__).resolve().parents[2] / "frontend"
DB_URL = "postgresql+psycopg2://user:pass@localhost:5432/db"


# ---------- rate limits ----------

def test_login_is_rate_limited(client):
    limiter.enabled = True
    limiter.reset()
    try:
        responses = [
            client.post("/api/auth/login", data={"username": "nobody@gmail.com", "password": "Wrong1234"})
            for _ in range(12)
        ]
    finally:
        limiter.enabled = False
        limiter.reset()
    codes = [r.status_code for r in responses]
    assert codes[:10] == [401] * 10
    assert codes[10:] == [429, 429]
    assert "wait" in responses[-1].json()["detail"].lower()
    assert responses[-1].headers["retry-after"] == "60"


def test_register_is_rate_limited(client):
    limiter.enabled = True
    limiter.reset()
    try:
        codes = [
            client.post(
                "/api/auth/register",
                json={"email": f"user{i}@gmail.com", "password": "Passw0rd123"},
            ).status_code
            for i in range(7)
        ]
    finally:
        limiter.enabled = False
        limiter.reset()
    assert codes[:5] == [201] * 5
    assert codes[5:] == [429, 429]


# ---------- security headers ----------

def test_api_responses_have_security_headers_and_are_not_cached(client):
    resp = client.get("/api/health")
    assert resp.headers["x-content-type-options"] == "nosniff"
    assert resp.headers["x-frame-options"] == "DENY"
    assert resp.headers["referrer-policy"] == "same-origin"
    assert resp.headers["cache-control"] == "no-store"


def test_website_pages_have_a_content_security_policy(client):
    resp = client.get("/app/login.html")
    assert resp.status_code == 200
    policy = resp.headers["content-security-policy"]
    assert "script-src 'self' https://cdn.jsdelivr.net" in policy
    assert "frame-ancestors 'none'" in policy
    assert "'unsafe-eval'" not in policy


def test_api_docs_page_is_not_restricted_by_the_policy(client):
    resp = client.get("/docs")
    assert resp.status_code == 200
    assert "content-security-policy" not in resp.headers


def test_hsts_is_sent_only_in_production(client, monkeypatch):
    assert "strict-transport-security" not in client.get("/api/health").headers
    monkeypatch.setattr(settings, "production", True)
    assert "max-age" in client.get("/api/health").headers["strict-transport-security"]


def test_frontend_pages_have_no_inline_scripts_or_event_attributes():
    pages = list(FRONTEND.glob("*.html"))
    assert len(pages) >= 7
    for page in pages:
        text = page.read_text(encoding="utf-8")
        for attributes in re.findall(r"<script([^>]*)>", text, flags=re.I):
            assert "src=" in attributes, f"inline script in {page.name}"
        assert not re.search(r"\son[a-z]+\s*=", text, flags=re.I), f"event attribute in {page.name}"


# ---------- errors and configuration ----------

def test_unexpected_errors_return_a_generic_500():
    def broken_db():
        raise RuntimeError("secret internal detail")
        yield

    app.dependency_overrides[get_db] = broken_db
    try:
        with TestClient(app, raise_server_exceptions=False) as test_client:
            resp = test_client.post(
                "/api/auth/register",
                json={"email": "a@gmail.com", "password": "Passw0rd123"},
            )
    finally:
        app.dependency_overrides.clear()
    assert resp.status_code == 500
    assert resp.json() == {"detail": "Internal server error"}
    assert "secret" not in resp.text


def test_production_requires_a_long_jwt_secret():
    with pytest.raises(ValidationError):
        Settings(database_url=DB_URL, jwt_secret="short", production=True, _env_file=None)
    assert Settings(database_url=DB_URL, jwt_secret="x" * 32, production=True, _env_file=None).production
    assert Settings(database_url=DB_URL, jwt_secret="short", production=False, _env_file=None).jwt_secret == "short"
