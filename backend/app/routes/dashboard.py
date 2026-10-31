from datetime import date, timedelta
from decimal import Decimal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user
from app.models import Category, Transaction, User
from app.routes.budgets import month_label, next_month, resolve_month
from app.schemas import MONTH_PATTERN, CategorySpend, DailySpend, DashboardOut

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])

ZERO = Decimal("0.00")


def previous_month(d: date) -> date:
    return date(d.year - (d.month == 1), (d.month - 2) % 12 + 1, 1)


def spend_by_category(db: Session, user: User, start: date, end: date) -> dict:
    """{category_id: (name, total spent)} for one date range, in a single query."""
    rows = db.execute(
        select(Transaction.category_id, Category.name, func.sum(Transaction.amount))
        .join(Category, Category.id == Transaction.category_id)
        .where(
            Transaction.user_id == user.id,
            Transaction.date >= start,
            Transaction.date < end,
        )
        .group_by(Transaction.category_id, Category.name)
    ).all()
    return {cid: (name, total) for cid, name, total in rows}


def percent_of(part: Decimal, whole: Decimal) -> Decimal:
    if whole == 0:
        return Decimal("0.0")
    return (part / whole * 100).quantize(Decimal("0.1"))


def change_percent(current: Decimal, previous: Decimal) -> Decimal | None:
    if previous == 0:
        return None  # a percentage change from zero has no meaning
    return ((current - previous) / previous * 100).quantize(Decimal("0.1"))


@router.get("", response_model=DashboardOut)
def dashboard(
    month: str | None = Query(default=None, pattern=MONTH_PATTERN),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    start = resolve_month(month)
    end = next_month(start)
    prev_start = previous_month(start)

    current = spend_by_category(db, user, start, end)
    previous = spend_by_category(db, user, prev_start, start)

    total = sum((t for _, t in current.values()), ZERO)
    prev_total = sum((t for _, t in previous.values()), ZERO)

    count = db.execute(
        select(func.count(Transaction.id)).where(
            Transaction.user_id == user.id,
            Transaction.date >= start,
            Transaction.date < end,
        )
    ).scalar_one()

    # Include categories that had spending in either month
    categories = []
    for cid in set(current) | set(previous):
        name = (current.get(cid) or previous[cid])[0]
        spent = current[cid][1] if cid in current else ZERO
        prev_spent = previous[cid][1] if cid in previous else ZERO
        categories.append(
            CategorySpend(
                category_id=cid,
                category_name=name,
                spent=spent,
                percent_of_total=percent_of(spent, total),
                previous_spent=prev_spent,
                change_percent=change_percent(spent, prev_spent),
            )
        )
    categories.sort(key=lambda c: (-c.spent, c.category_name))

    # One total per day, with zeros for days that had no spending
    day_rows = db.execute(
        select(Transaction.date, func.sum(Transaction.amount))
        .where(
            Transaction.user_id == user.id,
            Transaction.date >= start,
            Transaction.date < end,
        )
        .group_by(Transaction.date)
    ).all()
    by_day = {d: s for d, s in day_rows}
    daily = []
    for i in range((end - start).days):
        day = start + timedelta(days=i)
        daily.append(DailySpend(date=day, spent=by_day.get(day, ZERO)))

    return DashboardOut(
        month=month_label(start),
        total_spent=total,
        transaction_count=count,
        previous_month=month_label(prev_start),
        previous_total=prev_total,
        change_amount=total - prev_total,
        change_percent=change_percent(total, prev_total),
        by_category=categories,
        daily=daily,
    )
