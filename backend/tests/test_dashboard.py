import re
from decimal import Decimal
from types import SimpleNamespace

import pytest

from tests.helpers import insert_transaction, make_category


@pytest.fixture
def spending(client, db, alice):
    """October: Food 600 + Transport 400 (1000 in total). September: Food 300."""
    food = make_category(client, alice.headers, "Food")
    transport = make_category(client, alice.headers, "Transport")
    insert_transaction(db, alice.id, food, "600.00", "2026-10-05")
    insert_transaction(db, alice.id, transport, "400.00", "2026-10-05")
    insert_transaction(db, alice.id, food, "300.00", "2026-09-10")
    return SimpleNamespace(food=food, transport=transport)


def dashboard(client, headers, month):
    resp = client.get("/api/dashboard", params={"month": month}, headers=headers)
    assert resp.status_code == 200, resp.text
    return resp.json()


def test_october_totals_and_comparison(client, alice, spending):
    data = dashboard(client, alice.headers, "2026-10")
    assert data["month"] == "2026-10"
    assert Decimal(data["total_spent"]) == Decimal("1000.00")
    assert data["transaction_count"] == 2
    assert data["previous_month"] == "2026-09"
    assert Decimal(data["previous_total"]) == Decimal("300.00")
    assert Decimal(data["change_amount"]) == Decimal("700.00")
    assert Decimal(data["change_percent"]) == Decimal("233.3")

    food, transport = data["by_category"]  # biggest spender first
    assert food["category_name"] == "Food"
    assert Decimal(food["spent"]) == Decimal("600.00")
    assert Decimal(food["percent_of_total"]) == Decimal("60.0")
    assert Decimal(food["previous_spent"]) == Decimal("300.00")
    assert Decimal(food["change_percent"]) == Decimal("100.0")
    assert transport["category_name"] == "Transport"
    assert Decimal(transport["spent"]) == Decimal("400.00")
    assert Decimal(transport["percent_of_total"]) == Decimal("40.0")
    assert transport["change_percent"] is None  # nothing last month, so no percentage


def test_daily_series_fills_every_day(client, alice, spending):
    daily = dashboard(client, alice.headers, "2026-10")["daily"]
    assert len(daily) == 31
    assert daily[0]["date"] == "2026-10-01"
    assert Decimal(daily[0]["spent"]) == 0
    assert daily[4]["date"] == "2026-10-05"
    assert Decimal(daily[4]["spent"]) == Decimal("1000.00")
    assert daily[-1]["date"] == "2026-10-31"
    assert sum(Decimal(d["spent"]) for d in daily) == Decimal("1000.00")


def test_first_month_with_spending_has_no_percentage_change(client, alice, spending):
    data = dashboard(client, alice.headers, "2026-09")
    assert Decimal(data["total_spent"]) == Decimal("300.00")
    assert Decimal(data["previous_total"]) == 0
    assert Decimal(data["change_amount"]) == Decimal("300.00")
    assert data["change_percent"] is None
    assert [c["category_name"] for c in data["by_category"]] == ["Food"]


def test_empty_month_with_no_history(client, alice, spending):
    data = dashboard(client, alice.headers, "2026-08")
    assert Decimal(data["total_spent"]) == 0
    assert data["transaction_count"] == 0
    assert data["change_percent"] is None
    assert data["by_category"] == []
    assert len(data["daily"]) == 31
    assert all(Decimal(d["spent"]) == 0 for d in data["daily"])


def test_spending_that_drops_to_zero(client, alice, spending):
    data = dashboard(client, alice.headers, "2026-11")
    assert Decimal(data["total_spent"]) == 0
    assert Decimal(data["change_amount"]) == Decimal("-1000.00")
    assert Decimal(data["change_percent"]) == Decimal("-100.0")
    assert [c["category_name"] for c in data["by_category"]] == ["Food", "Transport"]
    for category in data["by_category"]:
        assert Decimal(category["spent"]) == 0
        assert Decimal(category["percent_of_total"]) == 0
        assert Decimal(category["change_percent"]) == Decimal("-100.0")


@pytest.mark.parametrize("month, days, previous", [
    ("2026-12", 31, "2026-11"),
    ("2027-01", 31, "2026-12"),   # crossing into a new year
    ("2026-04", 30, "2026-03"),
    ("2026-02", 28, "2026-01"),
    ("2028-02", 29, "2028-01"),   # leap year
])
def test_month_lengths_and_previous_month(client, alice, month, days, previous):
    data = dashboard(client, alice.headers, month)
    assert len(data["daily"]) == days
    assert data["previous_month"] == previous


def test_month_boundaries(client, db, alice, spending):
    insert_transaction(db, alice.id, spending.food, "10.00", "2026-10-31")  # last day of October
    insert_transaction(db, alice.id, spending.food, "20.00", "2026-11-01")  # first day of November
    assert Decimal(dashboard(client, alice.headers, "2026-10")["total_spent"]) == Decimal("1010.00")
    assert Decimal(dashboard(client, alice.headers, "2026-11")["total_spent"]) == Decimal("20.00")


@pytest.mark.parametrize("month", ["2026-13", "hello", "2026-1", "1999-01"])
def test_bad_month_is_422(client, alice, month):
    resp = client.get("/api/dashboard", params={"month": month}, headers=alice.headers)
    assert resp.status_code == 422


def test_other_users_spending_is_not_included(client, db, alice, bob, spending):
    bobs = make_category(client, bob.headers, "Mine")
    insert_transaction(db, bob.id, bobs, "5000.00", "2026-10-05")
    assert Decimal(dashboard(client, alice.headers, "2026-10")["total_spent"]) == Decimal("1000.00")


def test_without_a_month_it_uses_the_current_one(client, alice):
    resp = client.get("/api/dashboard", headers=alice.headers)
    assert resp.status_code == 200
    data = resp.json()
    assert re.fullmatch(r"\d{4}-\d{2}", data["month"])
    assert re.fullmatch(r"\d{4}-\d{2}", data["previous_month"])
