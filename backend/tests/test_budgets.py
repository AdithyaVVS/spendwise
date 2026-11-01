from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest
from sqlalchemy.exc import IntegrityError

from app.models import Budget
from tests.helpers import insert_transaction, make_category


@pytest.fixture
def spending(client, db, alice):
    """October 2026: Food 1560.00, Transport 1690.00, everything 3250.00."""
    food = make_category(client, alice.headers, "Food")
    transport = make_category(client, alice.headers, "Transport")
    insert_transaction(db, alice.id, food, "1000.00", "2026-10-05", "a")
    insert_transaction(db, alice.id, food, "560.00", "2026-10-20", "b")
    insert_transaction(db, alice.id, transport, "1690.00", "2026-10-10", "c")
    return SimpleNamespace(food=food, transport=transport)


def set_budget(client, headers, month, amount, category_id=None):
    body = {"month": month, "amount": amount}
    if category_id is not None:
        body["category_id"] = category_id
    return client.put("/api/budgets", json=body, headers=headers)


def status(client, headers, month):
    resp = client.get("/api/budgets/status", params={"month": month}, headers=headers)
    assert resp.status_code == 200, resp.text
    return resp.json()


def food_item(client, headers, month="2026-10"):
    return status(client, headers, month)["items"][0]


# ---------- the maths ----------

def test_status_numbers_and_states(client, alice, spending):
    set_budget(client, alice.headers, "2026-10", "3500.00")
    set_budget(client, alice.headers, "2026-10", "1500.00", spending.food)
    set_budget(client, alice.headers, "2026-10", "5000.00", spending.transport)

    report = status(client, alice.headers, "2026-10")
    assert report["month"] == "2026-10"
    assert report["items"][0]["category_name"] == "Overall"  # overall budget is listed first
    items = {i["category_name"]: i for i in report["items"]}
    expected = {
        "Overall":   ("3500.00", "3250.00", "250.00", "92.9", "warning"),
        "Food":      ("1500.00", "1560.00", "-60.00", "104.0", "over"),
        "Transport": ("5000.00", "1690.00", "3310.00", "33.8", "ok"),
    }
    for name, (budget, spent, remaining, percent, state) in expected.items():
        item = items[name]
        assert Decimal(item["budget"]) == Decimal(budget)
        assert Decimal(item["spent"]) == Decimal(spent)
        assert Decimal(item["remaining"]) == Decimal(remaining)
        assert Decimal(item["percent_used"]) == Decimal(percent)
        assert item["state"] == state


def test_spending_exactly_the_budget_is_warning_not_over(client, alice, spending):
    set_budget(client, alice.headers, "2026-10", "1560.00", spending.food)
    item = food_item(client, alice.headers)
    assert item["state"] == "warning"
    assert Decimal(item["remaining"]) == 0
    assert Decimal(item["percent_used"]) == Decimal("100.0")


def test_exactly_80_percent_is_warning(client, alice, spending):
    set_budget(client, alice.headers, "2026-10", "1950.00", spending.food)
    assert food_item(client, alice.headers)["state"] == "warning"


def test_just_under_80_percent_is_ok_even_though_it_rounds_to_80(client, alice, spending):
    set_budget(client, alice.headers, "2026-10", "1951.00", spending.food)  # 79.96% used
    assert food_item(client, alice.headers)["state"] == "ok"


def test_one_rupee_over_is_over(client, alice, spending):
    set_budget(client, alice.headers, "2026-10", "1559.00", spending.food)
    item = food_item(client, alice.headers)
    assert item["state"] == "over"
    assert Decimal(item["remaining"]) == Decimal("-1.00")


def test_category_with_no_spending(client, alice, spending):
    empty = make_category(client, alice.headers, "Empty")
    set_budget(client, alice.headers, "2026-10", "1000.00", empty)
    item = food_item(client, alice.headers)
    assert Decimal(item["spent"]) == 0
    assert Decimal(item["remaining"]) == Decimal("1000.00")
    assert Decimal(item["percent_used"]) == 0
    assert item["state"] == "ok"


# ---------- setting and listing ----------

def test_setting_a_budget_twice_replaces_it(client, alice, spending):
    set_budget(client, alice.headers, "2026-10", "3000.00")
    set_budget(client, alice.headers, "2026-10", "4000.00")
    budgets = client.get("/api/budgets", params={"month": "2026-10"}, headers=alice.headers).json()
    assert len(budgets) == 1
    assert Decimal(budgets[0]["amount"]) == Decimal("4000.00")


def test_budgets_belong_to_one_month(client, alice, spending):
    set_budget(client, alice.headers, "2026-10", "1500.00", spending.food)
    set_budget(client, alice.headers, "2026-11", "900.00", spending.food)
    october = client.get("/api/budgets", params={"month": "2026-10"}, headers=alice.headers).json()
    november = client.get("/api/budgets", params={"month": "2026-11"}, headers=alice.headers).json()
    assert [Decimal(b["amount"]) for b in october] == [Decimal("1500.00")]
    assert [Decimal(b["amount"]) for b in november] == [Decimal("900.00")]
    assert Decimal(food_item(client, alice.headers, "2026-11")["spent"]) == 0


def test_a_month_with_no_budgets_has_no_items(client, alice, spending):
    assert status(client, alice.headers, "2026-09")["items"] == []


def test_budget_for_a_missing_category_is_404(client, alice):
    assert set_budget(client, alice.headers, "2026-10", "100.00", 999999).status_code == 404


@pytest.mark.parametrize("body", [
    {"month": "2026-13", "amount": "100"},
    {"month": "26-10", "amount": "100"},
    {"month": "2026-10", "amount": "-5"},
    {"month": "2026-10", "amount": "0"},
    {"month": "2026-10", "amount": "abc"},
    {"amount": "100"},
])
def test_bad_budget_bodies_are_422(client, alice, body):
    assert client.put("/api/budgets", json=body, headers=alice.headers).status_code == 422


@pytest.mark.parametrize("path", ["/api/budgets", "/api/budgets/status"])
def test_bad_month_in_the_query_is_422(client, alice, path):
    resp = client.get(path, params={"month": "2026-13"}, headers=alice.headers)
    assert resp.status_code == 422


def test_delete_budget(client, alice, spending):
    budget_id = set_budget(client, alice.headers, "2026-10", "1500.00", spending.food).json()["id"]
    assert client.delete(f"/api/budgets/{budget_id}", headers=alice.headers).status_code == 204
    assert client.delete(f"/api/budgets/{budget_id}", headers=alice.headers).status_code == 404


# ---------- month boundaries ----------

def test_only_the_chosen_month_is_counted(client, db, alice, spending):
    set_budget(client, alice.headers, "2026-10", "10000.00")
    insert_transaction(db, alice.id, spending.food, "5000.00", "2026-09-30")  # last day before
    insert_transaction(db, alice.id, spending.food, "7000.00", "2026-11-01")  # first day after
    insert_transaction(db, alice.id, spending.food, "1.00", "2026-10-01")     # first day, counted
    insert_transaction(db, alice.id, spending.food, "2.00", "2026-10-31")     # last day, counted
    assert Decimal(food_item(client, alice.headers)["spent"]) == Decimal("3253.00")


def test_december_and_january_do_not_mix(client, db, alice, spending):
    set_budget(client, alice.headers, "2026-12", "1000.00", spending.food)
    set_budget(client, alice.headers, "2027-01", "1000.00", spending.food)
    insert_transaction(db, alice.id, spending.food, "100.00", "2026-12-31")
    insert_transaction(db, alice.id, spending.food, "50.00", "2027-01-01")
    assert Decimal(food_item(client, alice.headers, "2026-12")["spent"]) == Decimal("100.00")
    assert Decimal(food_item(client, alice.headers, "2027-01")["spent"]) == Decimal("50.00")


# ---------- the database itself refuses bad budgets ----------

def add_budget(db, user_id, category_id, month, amount):
    db.add(Budget(user_id=user_id, category_id=category_id, month=month, amount=Decimal(amount)))
    db.commit()


def test_database_rejects_a_second_overall_budget(db, alice):
    add_budget(db, alice.id, None, date(2026, 10, 1), "100")
    with pytest.raises(IntegrityError):
        add_budget(db, alice.id, None, date(2026, 10, 1), "200")


def test_database_rejects_a_second_budget_for_the_same_category(db, alice, spending):
    add_budget(db, alice.id, spending.food, date(2026, 10, 1), "100")
    with pytest.raises(IntegrityError):
        add_budget(db, alice.id, spending.food, date(2026, 10, 1), "200")


def test_database_rejects_a_month_that_is_not_the_first_day(db, alice):
    with pytest.raises(IntegrityError):
        add_budget(db, alice.id, None, date(2026, 10, 15), "100")


def test_database_rejects_a_budget_that_is_not_positive(db, alice):
    with pytest.raises(IntegrityError):
        add_budget(db, alice.id, None, date(2026, 10, 1), "-1")
