import pytest

from tests.helpers import make_category, make_transaction


def body(category_id, **changes):
    data = {"category_id": category_id, "amount": "250.50",
            "description": "Lunch", "date": "2026-10-31"}
    data.update(changes)
    return data


# ---------- categories ----------

def test_categories_are_listed_alphabetically(client, alice):
    make_category(client, alice.headers, "Zed")
    make_category(client, alice.headers, "Alpha")
    resp = client.get("/api/categories", headers=alice.headers)
    assert [c["name"] for c in resp.json()] == ["Alpha", "Zed"]


def test_category_name_is_trimmed(client, alice):
    resp = client.post("/api/categories", json={"name": "  Food  "}, headers=alice.headers)
    assert resp.status_code == 201
    assert resp.json()["name"] == "Food"


@pytest.mark.parametrize("name", ["", "   ", "x" * 51])
def test_bad_category_names_are_422(client, alice, name):
    resp = client.post("/api/categories", json={"name": name}, headers=alice.headers)
    assert resp.status_code == 422


def test_duplicate_category_is_409(client, alice):
    make_category(client, alice.headers, "Food")
    resp = client.post("/api/categories", json={"name": "Food"}, headers=alice.headers)
    assert resp.status_code == 409


def test_two_users_can_use_the_same_category_name(client, alice, bob):
    make_category(client, alice.headers, "Food")
    make_category(client, bob.headers, "Food")


def test_rename_category(client, alice):
    cat = make_category(client, alice.headers, "Food")
    resp = client.put(f"/api/categories/{cat}", json={"name": "Dining"}, headers=alice.headers)
    assert resp.status_code == 200
    assert resp.json()["name"] == "Dining"


def test_rename_to_an_existing_name_is_409(client, alice):
    make_category(client, alice.headers, "Food")
    other = make_category(client, alice.headers, "Transport")
    resp = client.put(f"/api/categories/{other}", json={"name": "Food"}, headers=alice.headers)
    assert resp.status_code == 409


def test_delete_empty_category(client, alice):
    cat = make_category(client, alice.headers)
    assert client.delete(f"/api/categories/{cat}", headers=alice.headers).status_code == 204
    assert client.get("/api/categories", headers=alice.headers).json() == []


def test_cannot_delete_category_that_has_transactions(client, alice):
    cat = make_category(client, alice.headers)
    make_transaction(client, alice.headers, cat)
    assert client.delete(f"/api/categories/{cat}", headers=alice.headers).status_code == 409
    assert len(client.get("/api/categories", headers=alice.headers).json()) == 1


def test_delete_unknown_category_is_404(client, alice):
    assert client.delete("/api/categories/999999", headers=alice.headers).status_code == 404


# ---------- creating transactions ----------

def test_create_transaction(client, alice):
    cat = make_category(client, alice.headers, "Food")
    resp = client.post("/api/transactions", json=body(cat), headers=alice.headers)
    assert resp.status_code == 201
    data = resp.json()
    assert data["amount"] == "250.50"
    assert data["category_name"] == "Food"
    assert data["description"] == "Lunch"
    assert data["date"] == "2026-10-31"


def test_description_is_optional(client, alice):
    cat = make_category(client, alice.headers)
    data = body(cat)
    del data["description"]
    resp = client.post("/api/transactions", json=data, headers=alice.headers)
    assert resp.status_code == 201
    assert resp.json()["description"] is None


@pytest.mark.parametrize("raw, saved", [("  Lunch  ", "Lunch"), ("   ", None)])
def test_description_is_trimmed(client, alice, raw, saved):
    cat = make_category(client, alice.headers)
    resp = client.post("/api/transactions", json=body(cat, description=raw), headers=alice.headers)
    assert resp.status_code == 201
    assert resp.json()["description"] == saved


@pytest.mark.parametrize("amount", ["-5", "0", "0.00", "10.999", "abc", "10000000000.00"])
def test_bad_amounts_are_422(client, alice, amount):
    cat = make_category(client, alice.headers)
    resp = client.post("/api/transactions", json=body(cat, amount=amount), headers=alice.headers)
    assert resp.status_code == 422


def test_largest_allowed_amount(client, alice):
    cat = make_category(client, alice.headers)
    resp = client.post("/api/transactions", json=body(cat, amount="9999999999.99"), headers=alice.headers)
    assert resp.status_code == 201
    assert resp.json()["amount"] == "9999999999.99"


@pytest.mark.parametrize("missing", ["category_id", "amount", "date"])
def test_missing_required_field_is_422(client, alice, missing):
    cat = make_category(client, alice.headers)
    data = body(cat)
    del data[missing]
    assert client.post("/api/transactions", json=data, headers=alice.headers).status_code == 422


def test_impossible_date_is_422(client, alice):
    cat = make_category(client, alice.headers)
    resp = client.post("/api/transactions", json=body(cat, date="2026-13-01"), headers=alice.headers)
    assert resp.status_code == 422


def test_category_that_belongs_to_someone_else_is_404(client, alice, bob):
    alices = make_category(client, alice.headers)
    resp = client.post("/api/transactions", json=body(alices), headers=bob.headers)
    assert resp.status_code == 404


def test_category_that_does_not_exist_is_404(client, alice):
    resp = client.post("/api/transactions", json=body(999999), headers=alice.headers)
    assert resp.status_code == 404


# ---------- reading, updating, deleting ----------

def test_get_one_transaction(client, alice):
    cat = make_category(client, alice.headers)
    tx = make_transaction(client, alice.headers, cat)
    resp = client.get(f"/api/transactions/{tx['id']}", headers=alice.headers)
    assert resp.status_code == 200
    assert resp.json()["id"] == tx["id"]


def test_get_unknown_transaction_is_404(client, alice):
    assert client.get("/api/transactions/999999", headers=alice.headers).status_code == 404


def test_non_numeric_transaction_id_is_422(client, alice):
    assert client.get("/api/transactions/abc", headers=alice.headers).status_code == 422


def test_update_changes_only_the_fields_you_send(client, alice):
    cat = make_category(client, alice.headers)
    tx = make_transaction(client, alice.headers, cat)
    resp = client.put(f"/api/transactions/{tx['id']}", json={"amount": "300.00"}, headers=alice.headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["amount"] == "300.00"
    assert data["description"] == "Lunch"
    assert data["date"] == "2026-10-31"
    assert data["category_id"] == cat


def test_update_cannot_move_to_someone_elses_category(client, alice, bob):
    alices = make_category(client, alice.headers)
    mine = make_category(client, bob.headers)
    tx = make_transaction(client, bob.headers, mine)
    resp = client.put(f"/api/transactions/{tx['id']}", json={"category_id": alices}, headers=bob.headers)
    assert resp.status_code == 404
    again = client.get(f"/api/transactions/{tx['id']}", headers=bob.headers).json()
    assert again["category_id"] == mine


@pytest.mark.parametrize("field", ["category_id", "amount", "date"])
def test_update_rejects_null_for_required_fields(client, alice, field):
    cat = make_category(client, alice.headers)
    tx = make_transaction(client, alice.headers, cat)
    resp = client.put(f"/api/transactions/{tx['id']}", json={field: None}, headers=alice.headers)
    assert resp.status_code == 422


def test_update_can_clear_the_description(client, alice):
    cat = make_category(client, alice.headers)
    tx = make_transaction(client, alice.headers, cat)
    resp = client.put(f"/api/transactions/{tx['id']}", json={"description": None}, headers=alice.headers)
    assert resp.status_code == 200
    assert resp.json()["description"] is None


def test_update_unknown_transaction_is_404(client, alice):
    resp = client.put("/api/transactions/999999", json={"amount": "5.00"}, headers=alice.headers)
    assert resp.status_code == 404


def test_delete_transaction(client, alice):
    cat = make_category(client, alice.headers)
    tx = make_transaction(client, alice.headers, cat)
    assert client.delete(f"/api/transactions/{tx['id']}", headers=alice.headers).status_code == 204
    assert client.get(f"/api/transactions/{tx['id']}", headers=alice.headers).status_code == 404
