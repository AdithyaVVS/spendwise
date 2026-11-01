from datetime import date, timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest

from tests.helpers import insert_transaction, make_category, make_transaction


@pytest.fixture
def seeded(client, db, alice):
    """25 transactions: 12 Food (even numbers) and 13 Transport (odd), Oct 2 to Oct 26."""
    food = make_category(client, alice.headers, "Food")
    transport = make_category(client, alice.headers, "Transport")
    for g in range(1, 26):
        insert_transaction(
            db, alice.id,
            food if g % 2 == 0 else transport,
            str(g * 10),
            (date(2026, 10, 1) + timedelta(days=g)).isoformat(),
            f"Seed item {g}",
        )
    return SimpleNamespace(food=food, transport=transport)


def fetch(client, headers, **params):
    resp = client.get("/api/transactions", params=params, headers=headers)
    assert resp.status_code == 200, resp.text
    return resp.json()


def test_default_page(client, alice, seeded):
    data = fetch(client, alice.headers)
    assert data["total"] == 25
    assert data["page"] == 1
    assert data["page_size"] == 20
    assert data["total_pages"] == 2
    assert len(data["items"]) == 20
    assert Decimal(data["total_amount"]) == Decimal("3250.00")


def test_second_page_has_the_rest(client, alice, seeded):
    data = fetch(client, alice.headers, page=2)
    assert data["page"] == 2
    assert len(data["items"]) == 5


def test_smaller_pages(client, alice, seeded):
    data = fetch(client, alice.headers, page_size=10)
    assert data["total_pages"] == 3
    assert len(data["items"]) == 10
    assert len(fetch(client, alice.headers, page_size=10, page=3)["items"]) == 5


def test_page_past_the_end_is_empty_not_an_error(client, alice, seeded):
    data = fetch(client, alice.headers, page=99)
    assert data["items"] == []
    assert data["total"] == 25


def test_pages_cover_every_row_exactly_once(client, alice, seeded):
    ids = []
    for page in (1, 2, 3):
        ids += [t["id"] for t in fetch(client, alice.headers, page_size=10, page=page)["items"]]
    assert len(ids) == 25
    assert len(set(ids)) == 25


def test_newest_transactions_come_first(client, alice, seeded):
    dates = [t["date"] for t in fetch(client, alice.headers, page_size=100)["items"]]
    assert dates == sorted(dates, reverse=True)


def test_filter_by_category(client, alice, seeded):
    food = fetch(client, alice.headers, category_id=seeded.food)
    assert food["total"] == 12
    assert Decimal(food["total_amount"]) == Decimal("1560.00")
    transport = fetch(client, alice.headers, category_id=seeded.transport)
    assert transport["total"] == 13
    assert Decimal(transport["total_amount"]) == Decimal("1690.00")


def test_date_range_includes_both_end_days(client, alice, seeded):
    data = fetch(client, alice.headers, date_from="2026-10-20", date_to="2026-10-26")
    assert data["total"] == 7
    assert Decimal(data["total_amount"]) == Decimal("1540.00")


def test_open_ended_date_ranges(client, alice, seeded):
    assert fetch(client, alice.headers, date_from="2026-10-26")["total"] == 1
    assert fetch(client, alice.headers, date_to="2026-10-02")["total"] == 1


def test_search_ignores_upper_and_lower_case(client, alice, seeded):
    assert fetch(client, alice.headers, search="SEED ITEM 2")["total"] == 7


def test_search_matches_part_of_a_description(client, alice, seeded):
    assert fetch(client, alice.headers, search="item 1")["total"] == 11


def test_filters_combine(client, alice, seeded):
    data = fetch(client, alice.headers, category_id=seeded.food, date_from="2026-10-20")
    assert data["total"] == 3
    assert Decimal(data["total_amount"]) == Decimal("660.00")


def test_no_matches(client, alice, seeded):
    data = fetch(client, alice.headers, search="zzzz")
    assert data["total"] == 0
    assert data["items"] == []
    assert data["total_pages"] == 1
    assert Decimal(data["total_amount"]) == 0


def test_blank_search_is_ignored(client, alice, seeded):
    assert fetch(client, alice.headers, search="   ")["total"] == 25


def test_percent_and_underscore_are_searched_literally(client, db, alice):
    cat = make_category(client, alice.headers)
    for text in ["100% done", "100 percent", "a_b", "axb"]:
        insert_transaction(db, alice.id, cat, "5", "2026-10-01", text)
    assert fetch(client, alice.headers, search="100%")["total"] == 1
    assert fetch(client, alice.headers, search="a_b")["total"] == 1


@pytest.mark.parametrize("params", [
    {"page": 0},
    {"page": -1},
    {"page": "abc"},
    {"page_size": 0},
    {"page_size": 101},
    {"date_from": "2026-10-31", "date_to": "2026-10-01"},
    {"date_from": "not-a-date"},
])
def test_invalid_parameters_are_422(client, alice, params):
    assert client.get("/api/transactions", params=params, headers=alice.headers).status_code == 422


def test_largest_allowed_page_size(client, alice, seeded):
    assert len(fetch(client, alice.headers, page_size=100)["items"]) == 25


def test_other_users_transactions_are_not_counted(client, alice, bob, seeded):
    cat = make_category(client, bob.headers, "Mine")
    make_transaction(client, bob.headers, cat, amount="777.00")
    data = fetch(client, alice.headers)
    assert data["total"] == 25
    assert Decimal(data["total_amount"]) == Decimal("3250.00")
