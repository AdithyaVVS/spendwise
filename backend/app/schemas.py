import datetime as dt
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

Money = Annotated[Decimal, Field(gt=0, max_digits=12, decimal_places=2)]


# ---------- auth ----------

class UserCreate(BaseModel):
    email: EmailStr
    password: str

    @field_validator("email")
    @classmethod
    def lowercase_email(cls, value):
        return value.lower()

    @field_validator("password")
    @classmethod
    def password_rules(cls, value):
        if len(value) < 8:
            raise ValueError("Password must be at least 8 characters")
        if len(value.encode("utf-8")) > 72:  # bcrypt's limit
            raise ValueError("Password must be at most 72 bytes")
        return value


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    created_at: dt.datetime


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


# ---------- categories ----------

class CategoryCreate(BaseModel):
    name: str = Field(min_length=1, max_length=50)

    @field_validator("name")
    @classmethod
    def clean_name(cls, value):
        value = value.strip()
        if not value:
            raise ValueError("Name cannot be blank")
        return value


class CategoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str


# ---------- transactions ----------

def _clean_description(value):
    if value is None:
        return None
    value = value.strip()
    return value or None


class TransactionCreate(BaseModel):
    category_id: int
    amount: Money
    description: str | None = Field(default=None, max_length=255)
    date: dt.date

    _clean = field_validator("description")(_clean_description)


class TransactionUpdate(BaseModel):
    category_id: int | None = None
    amount: Money | None = None
    description: str | None = Field(default=None, max_length=255)
    date: dt.date | None = None

    _clean = field_validator("description")(_clean_description)


class TransactionOut(BaseModel):
    id: int
    category_id: int
    category_name: str
    amount: Decimal
    description: str | None
    date: dt.date
    created_at: dt.datetime


class TransactionPage(BaseModel):
    items: list[TransactionOut]
    total: int
    page: int
    page_size: int
    total_pages: int
    total_amount: Decimal


MONTH_PATTERN = r"^20\d{2}-(0[1-9]|1[0-2])$"


class BudgetSet(BaseModel):
    month: str = Field(pattern=MONTH_PATTERN, examples=["2026-10"])
    category_id: int | None = None  # leave out for the overall budget
    amount: Money


class BudgetOut(BaseModel):
    id: int
    category_id: int | None
    category_name: str | None
    month: str
    amount: Decimal


class BudgetStatus(BaseModel):
    budget_id: int
    category_id: int | None
    category_name: str
    budget: Decimal
    spent: Decimal
    remaining: Decimal
    percent_used: Decimal
    state: str


class BudgetStatusReport(BaseModel):
    month: str
    items: list[BudgetStatus]


class CategorySpend(BaseModel):
    category_id: int
    category_name: str
    spent: Decimal
    percent_of_total: Decimal
    previous_spent: Decimal
    change_percent: Decimal | None  # null when last month was zero


class DailySpend(BaseModel):
    date: dt.date
    spent: Decimal


class DashboardOut(BaseModel):
    month: str
    total_spent: Decimal
    transaction_count: int
    previous_month: str
    previous_total: Decimal
    change_amount: Decimal
    change_percent: Decimal | None  # null when last month was zero
    by_category: list[CategorySpend]
    daily: list[DailySpend]
