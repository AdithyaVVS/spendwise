import os
from types import SimpleNamespace

# Point the whole app at the TEST database before anything from `app` is imported.
TEST_DATABASE_URL = "postgresql+psycopg2://spendwise:spendwise@localhost:5433/spendwise_test"
os.environ["DATABASE_URL"] = TEST_DATABASE_URL
os.environ.setdefault("JWT_SECRET", "test-secret-only-used-by-the-test-suite")

import bcrypt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import models  # noqa: F401
from app.database import Base, get_db
from app.main import app
from tests.helpers import make_user

engine = create_engine(TEST_DATABASE_URL)
assert engine.url.database == "spendwise_test", "Tests must never run on the real database"
TestingSessionLocal = sessionmaker(bind=engine, autoflush=False)

_real_gensalt = bcrypt.gensalt


@pytest.fixture(autouse=True)
def clean_database():
    """Brand-new empty tables before every single test."""
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)


@pytest.fixture(autouse=True)
def fast_password_hashing(monkeypatch):
    """bcrypt is deliberately slow; use the cheapest setting in tests only."""
    monkeypatch.setattr(bcrypt, "gensalt", lambda: _real_gensalt(rounds=4))


@pytest.fixture
def db():
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def client():
    def override_get_db():
        session = TestingSessionLocal()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def alice(client):
    user_id, headers = make_user(client, "alice@gmail.com")
    return SimpleNamespace(id=user_id, headers=headers)


@pytest.fixture
def bob(client):
    user_id, headers = make_user(client, "bob@gmail.com")
    return SimpleNamespace(id=user_id, headers=headers)
