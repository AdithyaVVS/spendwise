from decimal import Decimal
from types import SimpleNamespace

import pytest

from tests.helpers import make_category, make_transaction, upload


@pytest.fixture
def alice_data(client, alice):
    """Alice owns a category, a transaction and a budget."""
    cat = make_category(client, alice.headers, "Secret")
    tx = make_transaction(client, alice.headers, cat, amount="99.00",
                          description="Private", day="2026-10-31")
    resp = client.put(
        "/api/budgets",
        json={"month": "2026-10", "category_id": cat, "amount": "500.00"},
        headers=alice.headers,
    )
    assert resp.status_code == 200
    return SimpleNamespace(category_id=cat, transaction_id=tx["id"], budget_id=resp.json()["id"])


# ---------- bob tries to touch alice's things ----------

def test_bob_cannot_read_alices_transaction(client, bob, alice_data):
    resp = client.get(f"/api/transactions/{alice_data.transaction_id}", headers=bob.headers)
    assert resp.status_code == 404


def test_bob_cannot_edit_alices_transaction(client, bob, alice_data):
    resp = client.put(f"/api/transactions/{alice_data.transaction_id}",
                      json={"amount": "1.00"}, headers=bob.headers)
    assert resp.status_code == 404


def test_bob_cannot_delete_alices_transaction(client, bob, alice_data):
    resp = client.delete(f"/api/transactions/{alice_data.transaction_id}", headers=bob.headers)
    assert resp.status_code == 404


def test_bob_cannot_file_spending_under_alices_category(client, bob, alice_data):
    resp = client.post(
        "/api/transactions",
        json={"category_id": alice_data.category_id, "amount": "10.00", "date": "2026-10-31"},
        headers=bob.headers,
    )
    assert resp.status_code == 404


def test_bob_cannot_move_his_transaction_into_alices_category(client, bob, alice_data):
    mine = make_category(client, bob.headers, "Mine")
    tx = make_transaction(client, bob.headers, mine)
    resp = client.put(f"/api/transactions/{tx['id']}",
                      json={"category_id": alice_data.category_id}, headers=bob.headers)
    assert resp.status_code == 404
    again = client.get(f"/api/transactions/{tx['id']}", headers=bob.headers).json()
    assert again["category_id"] == mine


def test_bob_cannot_rename_or_delete_alices_category(client, bob, alice_data):
    url = f"/api/categories/{alice_data.category_id}"
    assert client.put(url, json={"name": "Hacked"}, headers=bob.headers).status_code == 404
    assert client.delete(url, headers=bob.headers).status_code == 404


def test_bob_cannot_set_a_budget_on_alices_category(client, bob, alice_data):
    resp = client.put(
        "/api/budgets",
        json={"month": "2026-10", "category_id": alice_data.category_id, "amount": "100.00"},
        headers=bob.headers,
    )
    assert resp.status_code == 404


def test_bob_cannot_delete_alices_budget(client, bob, alice_data):
    resp = client.delete(f"/api/budgets/{alice_data.budget_id}", headers=bob.headers)
    assert resp.status_code == 404


def test_bob_sees_nothing_of_alices(client, bob, alice_data):
    h = bob.headers
    assert client.get("/api/categories", headers=h).json() == []
    page = client.get("/api/transactions", headers=h).json()
    assert page["total"] == 0 and page["items"] == []
    assert client.get("/api/budgets", params={"month": "2026-10"}, headers=h).json() == []
    assert client.get("/api/budgets/status", params={"month": "2026-10"}, headers=h).json()["items"] == []
    dash = client.get("/api/dashboard", params={"month": "2026-10"}, headers=h).json()
    assert Decimal(dash["total_spent"]) == 0
    assert dash["by_category"] == []


def test_alices_data_is_unchanged_after_bobs_attacks(client, alice, bob, alice_data):
    client.put(f"/api/transactions/{alice_data.transaction_id}", json={"amount": "1.00"}, headers=bob.headers)
    client.delete(f"/api/transactions/{alice_data.transaction_id}", headers=bob.headers)
    client.put(f"/api/categories/{alice_data.category_id}", json={"name": "Hacked"}, headers=bob.headers)
    client.delete(f"/api/budgets/{alice_data.budget_id}", headers=bob.headers)

    tx = client.get(f"/api/transactions/{alice_data.transaction_id}", headers=alice.headers).json()
    assert tx["amount"] == "99.00"
    assert tx["description"] == "Private"
    assert tx["category_name"] == "Secret"
    budgets = client.get("/api/budgets", params={"month": "2026-10"}, headers=alice.headers).json()
    assert len(budgets) == 1
    assert Decimal(budgets[0]["amount"]) == Decimal("500.00")


def test_bobs_import_does_not_see_alices_rows_as_duplicates(client, alice, bob, alice_data):
    csv_text = "date,amount,description,category\n2026-10-31,99.00,Private,Secret\n"
    data = upload(client, bob.headers, csv_text).json()
    assert data["imported"] == 1
    assert data["duplicates_skipped"] == 0
    assert data["categories_created"] == ["Secret"]  # bob gets his own category
    assert client.get("/api/transactions", headers=alice.headers).json()["total"] == 1
    assert len(client.get("/api/categories", headers=alice.headers).json()) == 1


# ---------- nothing works without a login ----------

PROTECTED = [
    ("GET", "/api/auth/me", {}),
    ("GET", "/api/categories", {}),
    ("POST", "/api/categories", {"json": {"name": "x"}}),
    ("PUT", "/api/categories/1", {"json": {"name": "x"}}),
    ("DELETE", "/api/categories/1", {}),
    ("GET", "/api/transactions", {}),
    ("POST", "/api/transactions", {"json": {"category_id": 1, "amount": "5", "date": "2026-10-31"}}),
    ("GET", "/api/transactions/1", {}),
    ("PUT", "/api/transactions/1", {"json": {"amount": "5"}}),
    ("DELETE", "/api/transactions/1", {}),
    ("POST", "/api/transactions/import",
     {"files": {"file": ("a.csv", b"date,amount,category\n", "text/csv")}}),
    ("GET", "/api/budgets", {}),
    ("PUT", "/api/budgets", {"json": {"month": "2026-10", "amount": "5"}}),
    ("GET", "/api/budgets/status", {}),
    ("DELETE", "/api/budgets/1", {}),
    ("GET", "/api/dashboard", {}),
]


@pytest.mark.parametrize(
    "method, path, kwargs", PROTECTED, ids=[f"{m} {p}" for m, p, _ in PROTECTED]
)
def test_endpoint_requires_login(client, method, path, kwargs):
    assert client.request(method, path, **kwargs).status_code == 401
