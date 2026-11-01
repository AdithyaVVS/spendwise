from decimal import Decimal

import pytest

from tests.helpers import make_category, make_transaction, upload

HEADER = "date,amount,description,category\n"
DATE_HINT = "date must look like 2026-11-05 or 05/11/2026"

MIXED_FILE = """date,amount,description,category
2026-11-01,250.50,Lunch,Food
2026-11-02,"1,250.00",Metro,Transport
03/11/2026,80,Auto,transport
2026-11-04,-20,Refund,Food
2026-11-05,abc,Bad amount,Food
2026-13-45,100,Bad date,Food
2026-11-06,100,No category,
2026-11-07,10.999,Too many decimals,Food
,,,
2026-11-08,500,,Transport
"""


def list_all(client, headers, **params):
    params.setdefault("page_size", 100)
    resp = client.get("/api/transactions", params=params, headers=headers)
    assert resp.status_code == 200, resp.text
    return resp.json()


# ---------- a realistic file ----------

def test_mixed_file_imports_good_rows_and_reports_bad_ones(client, alice):
    resp = upload(client, alice.headers, MIXED_FILE)
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_rows"] == 9  # the all-blank row is ignored
    assert data["imported"] == 4
    assert data["duplicates_skipped"] == 0
    assert data["rejected"] == 5
    assert data["categories_created"] == ["Food", "Transport"]  # "transport" matched Transport
    assert data["duplicate_rows"] == []
    assert data["errors"] == [
        {"row": 5, "reason": "amount must be greater than 0"},
        {"row": 6, "reason": "amount is not a number"},
        {"row": 7, "reason": DATE_HINT},
        {"row": 8, "reason": "category is required"},
        {"row": 9, "reason": "amount can have at most 2 decimal places"},
    ]


def test_mixed_file_saves_the_right_data(client, alice):
    upload(client, alice.headers, MIXED_FILE)
    page = list_all(client, alice.headers)
    assert page["total"] == 4
    assert Decimal(page["total_amount"]) == Decimal("2080.50")
    dates = {t["date"] for t in page["items"]}
    assert "2026-11-03" in dates  # 03/11/2026 is read day-first
    assert None in {t["description"] for t in page["items"]}  # the row with no description
    names = [c["name"] for c in client.get("/api/categories", headers=alice.headers).json()]
    assert names == ["Food", "Transport"]


def test_importing_the_same_file_twice_adds_nothing(client, alice):
    upload(client, alice.headers, MIXED_FILE)
    data = upload(client, alice.headers, MIXED_FILE).json()
    assert data["imported"] == 0
    assert data["duplicates_skipped"] == 4
    assert data["duplicate_rows"] == [2, 3, 4, 11]
    assert data["rejected"] == 5
    assert data["categories_created"] == []
    assert list_all(client, alice.headers)["total"] == 4


# ---------- duplicates ----------

def test_identical_rows_in_one_file_are_kept_but_not_added_again(client, alice):
    two_teas = HEADER + "2026-11-05,60,Tea,Food\n" * 2
    three_teas = HEADER + "2026-11-05,60,Tea,Food\n" * 3
    assert upload(client, alice.headers, two_teas).json()["imported"] == 2
    data = upload(client, alice.headers, three_teas).json()
    assert data["imported"] == 1
    assert data["duplicates_skipped"] == 2
    assert data["duplicate_rows"] == [2, 3]
    assert list_all(client, alice.headers)["total"] == 3


def test_transactions_made_by_hand_count_as_duplicates(client, alice):
    cat = make_category(client, alice.headers, "Food")
    make_transaction(client, alice.headers, cat, "250.50", "Lunch", "2026-11-01")
    data = upload(client, alice.headers, HEADER + "2026-11-01,250.50,LUNCH,food\n").json()
    assert data["imported"] == 0
    assert data["duplicates_skipped"] == 1
    assert data["categories_created"] == []
    assert len(client.get("/api/categories", headers=alice.headers).json()) == 1


def test_existing_category_is_reused_ignoring_case(client, alice):
    cat = make_category(client, alice.headers, "Food")
    data = upload(client, alice.headers, HEADER + "2026-11-02,10,Snack,food\n").json()
    assert data["imported"] == 1
    assert data["categories_created"] == []
    assert list_all(client, alice.headers)["items"][0]["category_id"] == cat


# ---------- file formats that should work ----------

ACCEPTED = [
    ("date,amount,category\n2026-11-01,5,Food\n", "5.00"),
    ("  Date , AMOUNT ,Category\n2026-11-01,5,Food\n", "5.00"),
    ("category,amount,date\nFood,5,2026-11-01\n", "5.00"),
    ("\ufeffdate,amount,category\n2026-11-01,5,Food\n", "5.00"),
    ("date,amount,category\r\n2026-11-01,5,Food\r\n", "5.00"),
    ("date,amount,category\n2026-11-01,\u20b9500,Food\n", "500.00"),
    ('date,amount,category\n2026-11-01,"1,234.50",Food\n', "1234.50"),
    ("date,amount,category\n01-11-2026,5,Food\n", "5.00"),
    ("date,amount,category\n01/11/2026,5,Food\n", "5.00"),
]
ACCEPTED_IDS = ["plain", "messy-header", "column-order", "excel-bom", "windows-lines",
                "rupee-sign", "thousands-comma", "dd-mm-yyyy-dashes", "dd-mm-yyyy-slashes"]


@pytest.mark.parametrize("content, amount", ACCEPTED, ids=ACCEPTED_IDS)
def test_accepted_file_variations(client, alice, content, amount):
    data = upload(client, alice.headers, content).json()
    assert data["imported"] == 1
    assert data["rejected"] == 0
    item = list_all(client, alice.headers)["items"][0]
    assert item["amount"] == amount
    assert item["date"] == "2026-11-01"


# ---------- single bad rows ----------

BAD_ROWS = [
    ("2026-11-01,0,Food", "amount must be greater than 0"),
    ("2026-11-01,-5,Food", "amount must be greater than 0"),
    ("2026-11-01,abc,Food", "amount is not a number"),
    ("2026-11-01,NaN,Food", "amount is not a number"),
    ("2026-11-01,Infinity,Food", "amount is not a number"),
    ("2026-11-01,,Food", "amount is required"),
    ("2026-11-01,5.005,Food", "amount can have at most 2 decimal places"),
    ("2026-11-01,99999999999,Food", "amount is too large"),
    (",5,Food", "date is required"),
    ("1999-01-01,5,Food", "date is out of range"),
    ("2101-01-01,5,Food", "date is out of range"),
    ("2026-02-30,5,Food", DATE_HINT),
    ("11/13/2026,5,Food", DATE_HINT),
    ("2026-11-01,5,", "category is required"),
    ("2026-11-01,5", "category is required"),
    (f"2026-11-01,5,{'x' * 51}", "category name is longer than 50 characters"),
    (f"2026-11-01,5,Food,{'d' * 256}", "description is longer than 255 characters"),
]
BAD_ROW_HEADER = "date,amount,category,description\n"


@pytest.mark.parametrize("row, reason", BAD_ROWS)
def test_bad_row_is_rejected_with_a_reason(client, alice, row, reason):
    data = upload(client, alice.headers, BAD_ROW_HEADER + row + "\n").json()
    assert data["imported"] == 0
    assert data["rejected"] == 1
    assert data["errors"] == [{"row": 2, "reason": reason}]
    assert list_all(client, alice.headers)["total"] == 0


# ---------- whole files that get refused ----------

REFUSED = [
    (b"\n", "File is empty"),
    ("hello,world\n1,2\n", "Missing column(s): amount, category, date"),
    ("date,amount,category\n", "No data rows found"),
    ("date,amount,category\n,,\n\n", "No data rows found"),
    (bytes([0xFF, 0xFE, 0xFD]), "UTF-8 text CSV"),
    (b"date,amount,category\n2026-11-01,5,Food\x00", "File must be a text CSV"),
    (b"x" * 1_000_001, "larger than 1 MB"),
    ("date,amount,category\n" + "2026-11-01,1,Food\n" * 1001, "Too many rows"),
]
REFUSED_IDS = ["empty", "wrong-columns", "header-only", "only-blank-rows",
               "not-utf8", "binary-nul", "over-1mb", "over-1000-rows"]


@pytest.mark.parametrize("content, message", REFUSED, ids=REFUSED_IDS)
def test_unusable_file_is_refused(client, alice, content, message):
    resp = upload(client, alice.headers, content)
    assert resp.status_code == 422
    assert message in resp.json()["detail"]


def test_a_refused_file_saves_nothing(client, alice):
    too_many = "date,amount,category\n" + "2026-11-01,1,Food\n" * 1001
    assert upload(client, alice.headers, too_many).status_code == 422
    assert list_all(client, alice.headers)["total"] == 0
    assert client.get("/api/categories", headers=alice.headers).json() == []


def test_exactly_1000_rows_is_allowed(client, alice):
    content = "date,amount,category\n" + "2026-11-01,1,Food\n" * 1000
    data = upload(client, alice.headers, content).json()
    assert data["imported"] == 1000


def test_request_without_a_file_is_422(client, alice):
    assert client.post("/api/transactions/import", headers=alice.headers).status_code == 422
