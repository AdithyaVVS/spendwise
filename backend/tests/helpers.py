from datetime import date
from decimal import Decimal

from app.models import Transaction

PASSWORD = "Passw0rd123"


def make_user(client, email, password=PASSWORD):
    resp = client.post("/api/auth/register", json={"email": email, "password": password})
    assert resp.status_code == 201, resp.text
    user_id = resp.json()["id"]
    resp = client.post("/api/auth/login", data={"username": email, "password": password})
    assert resp.status_code == 200, resp.text
    headers = {"Authorization": f"Bearer {resp.json()['access_token']}"}
    return user_id, headers


def make_category(client, headers, name="Food"):
    resp = client.post("/api/categories", json={"name": name}, headers=headers)
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def make_transaction(client, headers, category_id, amount="250.50",
                     description="Lunch", day="2026-10-31"):
    resp = client.post(
        "/api/transactions",
        json={"category_id": category_id, "amount": amount,
              "description": description, "date": day},
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def insert_transaction(db, user_id, category_id, amount, day, description=None):
    """Add a transaction straight to the database (faster than the API)."""
    db.add(Transaction(
        user_id=user_id,
        category_id=category_id,
        amount=Decimal(amount),
        description=description,
        date=date.fromisoformat(day),
    ))
    db.commit()


def upload(client, headers, content, name="statement.csv"):
    data = content.encode("utf-8") if isinstance(content, str) else content
    return client.post(
        "/api/transactions/import",
        files={"file": (name, data, "text/csv")},
        headers=headers,
    )
