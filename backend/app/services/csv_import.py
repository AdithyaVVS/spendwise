import csv
import io
from collections import Counter
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import NamedTuple

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import Category, Transaction, User

MAX_BYTES = 1_000_000  # 1 MB
MAX_ROWS = 1000
MAX_DETAILS = 100  # how many error / duplicate rows to list in the report
DATE_FORMATS = ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y")
REQUIRED_COLUMNS = {"date", "amount", "category"}
TWO_PLACES = Decimal("0.01")
MAX_AMOUNT = Decimal("9999999999.99")


class CsvFormatError(Exception):
    """A problem with the whole file, so nothing is imported."""


class Row(NamedTuple):
    number: int
    when: date
    amount: Decimal
    description: str | None
    category: str


def parse_date(text: str) -> date:
    if not text:
        raise ValueError("date is required")
    for fmt in DATE_FORMATS:
        try:
            parsed = datetime.strptime(text, fmt).date()
        except ValueError:
            continue
        if not 2000 <= parsed.year <= 2100:
            raise ValueError("date is out of range")
        return parsed
    raise ValueError("date must look like 2026-11-05 or 05/11/2026")


def parse_amount(text: str) -> Decimal:
    cleaned = text.replace("\u20b9", "").replace(",", "").strip()
    if not cleaned:
        raise ValueError("amount is required")
    try:
        value = Decimal(cleaned)
    except InvalidOperation:
        raise ValueError("amount is not a number")
    if not value.is_finite():
        raise ValueError("amount is not a number")
    if value <= 0:
        raise ValueError("amount must be greater than 0")
    if value > MAX_AMOUNT:
        raise ValueError("amount is too large")
    if value != value.quantize(TWO_PLACES):
        raise ValueError("amount can have at most 2 decimal places")
    return value.quantize(TWO_PLACES)


def parse_category(text: str) -> str:
    if not text:
        raise ValueError("category is required")
    if len(text) > 50:
        raise ValueError("category name is longer than 50 characters")
    return text


def parse_description(text: str) -> str | None:
    if not text:
        return None
    if len(text) > 255:
        raise ValueError("description is longer than 255 characters")
    return text


def cell(row: dict, key: str) -> str:
    value = row.get(key)
    return value.strip() if isinstance(value, str) else ""


def read_rows(raw: bytes):
    """Parse and validate the file. Returns (valid rows, errors, total rows, rejected count)."""
    if len(raw) > MAX_BYTES:
        raise CsvFormatError("File is larger than 1 MB")
    try:
        text = raw.decode("utf-8-sig")  # also handles the BOM that Excel adds
    except UnicodeDecodeError:
        raise CsvFormatError("File must be a UTF-8 text CSV")
    if "\x00" in text:
        raise CsvFormatError("File must be a text CSV")

    valid: list[Row] = []
    errors: list[dict] = []
    total = rejected = 0
    try:
        reader = csv.DictReader(io.StringIO(text))
        if not reader.fieldnames:
            raise CsvFormatError("File is empty")
        reader.fieldnames = [(name or "").strip().lower() for name in reader.fieldnames]
        missing = REQUIRED_COLUMNS - set(reader.fieldnames)
        if missing:
            raise CsvFormatError(
                f"Missing column(s): {', '.join(sorted(missing))}. "
                "The file needs the columns date, amount, category (description is optional)."
            )

        for number, row in enumerate(reader, start=2):  # the header is row 1
            if not any(isinstance(v, str) and v.strip() for v in row.values()):
                continue  # completely blank row
            total += 1
            if total > MAX_ROWS:
                raise CsvFormatError(f"Too many rows (the maximum is {MAX_ROWS})")
            try:
                valid.append(
                    Row(
                        number=number,
                        when=parse_date(cell(row, "date")),
                        amount=parse_amount(cell(row, "amount")),
                        description=parse_description(cell(row, "description")),
                        category=parse_category(cell(row, "category")),
                    )
                )
            except ValueError as exc:
                rejected += 1
                if len(errors) < MAX_DETAILS:
                    errors.append({"row": number, "reason": str(exc)})
    except csv.Error as exc:
        raise CsvFormatError(f"Could not read the file as CSV: {exc}")
    return valid, errors, total, rejected


def import_transactions(db: Session, user: User, raw: bytes) -> dict:
    rows, errors, total, rejected = read_rows(raw)
    if total == 0:
        raise CsvFormatError("No data rows found in the file")

    imported = 0
    duplicate_count = 0
    duplicate_rows: list[int] = []
    categories_created: list[str] = []

    if rows:
        try:
            # 1. Find or create categories (names matched ignoring case)
            categories = {
                c.name.lower(): c
                for c in db.query(Category).filter(Category.user_id == user.id)
            }
            for row in rows:
                key = row.category.lower()
                if key not in categories:
                    category = Category(user_id=user.id, name=row.category)
                    db.add(category)
                    categories[key] = category
                    categories_created.append(row.category)
            db.flush()  # gives the new categories their ids

            # 2. Count what this user already has in the same date range
            first = min(r.when for r in rows)
            last = max(r.when for r in rows)
            existing = db.execute(
                select(
                    Transaction.date,
                    Transaction.amount,
                    Transaction.description,
                    Transaction.category_id,
                ).where(
                    Transaction.user_id == user.id,
                    Transaction.date >= first,
                    Transaction.date <= last,
                )
            ).all()
            seen = Counter(
                (d, amount, (desc or "").lower(), cid)
                for d, amount, desc, cid in existing
            )

            # 3. Add each row, unless an identical one already exists
            for row in rows:
                category_id = categories[row.category.lower()].id
                key = (row.when, row.amount, (row.description or "").lower(), category_id)
                if seen[key] > 0:
                    seen[key] -= 1  # use up one existing copy
                    duplicate_count += 1
                    if len(duplicate_rows) < MAX_DETAILS:
                        duplicate_rows.append(row.number)
                else:
                    db.add(
                        Transaction(
                            user_id=user.id,
                            category_id=category_id,
                            amount=row.amount,
                            description=row.description,
                            date=row.when,
                        )
                    )
                    imported += 1
            db.commit()
        except IntegrityError:
            db.rollback()
            raise CsvFormatError("The import clashed with another change. Please try again.")

    return {
        "total_rows": total,
        "imported": imported,
        "duplicates_skipped": duplicate_count,
        "rejected": rejected,
        "categories_created": categories_created,
        "errors": errors,
        "duplicate_rows": duplicate_rows,
    }
