from datetime import datetime, timedelta, timezone

import jwt
import pytest

from app.config import settings
from app.models import User
from tests.helpers import PASSWORD


def register(client, email="alice@gmail.com", password=PASSWORD):
    return client.post("/api/auth/register", json={"email": email, "password": password})


def login(client, email="alice@gmail.com", password=PASSWORD):
    return client.post("/api/auth/login", data={"username": email, "password": password})


def bearer(token):
    return {"Authorization": f"Bearer {token}"}


def make_token(user_id, secret=None, expires_in=timedelta(minutes=5)):
    payload = {"sub": str(user_id), "exp": datetime.now(timezone.utc) + expires_in}
    return jwt.encode(payload, secret or settings.jwt_secret, algorithm="HS256")


# ---------- registration ----------

def test_register_returns_user_without_password(client):
    resp = register(client, "New.Person@Gmail.com")
    assert resp.status_code == 201
    body = resp.json()
    assert body["email"] == "new.person@gmail.com"  # saved in lowercase
    assert "password" not in body and "password_hash" not in body


def test_register_duplicate_email_is_409(client):
    assert register(client).status_code == 201
    assert register(client).status_code == 409


def test_register_duplicate_ignores_email_case(client):
    assert register(client, "alice@gmail.com").status_code == 201
    assert register(client, "ALICE@gmail.com").status_code == 409


@pytest.mark.parametrize("password", ["short", "a" * 73])
def test_register_rejects_bad_password(client, password):
    assert register(client, password=password).status_code == 422


@pytest.mark.parametrize("email", ["nope", "a@", "@gmail.com", ""])
def test_register_rejects_bad_email(client, email):
    assert register(client, email).status_code == 422


def test_password_is_stored_hashed_and_salted(client, db):
    register(client, "alice@gmail.com")
    register(client, "bob@gmail.com")
    users = db.query(User).order_by(User.id).all()
    assert users[0].password_hash.startswith("$2b$")
    assert PASSWORD not in users[0].password_hash
    assert users[0].password_hash != users[1].password_hash  # same password, different salt


# ---------- login ----------

def test_login_returns_token(client):
    register(client)
    resp = login(client)
    assert resp.status_code == 200
    assert resp.json()["token_type"] == "bearer"
    assert resp.json()["access_token"]


def test_login_ignores_email_case(client):
    register(client)
    assert login(client, "ALICE@GMAIL.COM").status_code == 200


def test_wrong_password_and_unknown_email_look_the_same(client):
    register(client)
    wrong = login(client, password="WrongPassw0rd")
    unknown = login(client, email="nobody@gmail.com")
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json() == unknown.json()


# ---------- tokens ----------

def test_me_without_token_is_401(client):
    assert client.get("/api/auth/me").status_code == 401


def test_me_with_token(client, alice):
    resp = client.get("/api/auth/me", headers=alice.headers)
    assert resp.status_code == 200
    assert resp.json()["email"] == "alice@gmail.com"
    assert resp.json()["id"] == alice.id


def test_hand_made_valid_token_works(client, alice):
    # Proves make_token builds real tokens, so the failure tests below mean something
    assert client.get("/api/auth/me", headers=bearer(make_token(alice.id))).status_code == 200


def test_expired_token_is_401(client, alice):
    token = make_token(alice.id, expires_in=timedelta(minutes=-1))
    assert client.get("/api/auth/me", headers=bearer(token)).status_code == 401


def test_token_signed_with_wrong_secret_is_401(client, alice):
    token = make_token(alice.id, secret="x" * 40)
    assert client.get("/api/auth/me", headers=bearer(token)).status_code == 401


def test_unsigned_token_is_401(client, alice):
    token = jwt.encode({"sub": str(alice.id)}, "", algorithm="none")
    assert client.get("/api/auth/me", headers=bearer(token)).status_code == 401


def test_token_for_deleted_user_is_401(client, db, alice):
    db.query(User).delete()
    db.commit()
    assert client.get("/api/auth/me", headers=alice.headers).status_code == 401


def test_garbage_token_is_401(client):
    assert client.get("/api/auth/me", headers=bearer("not-a-token")).status_code == 401
