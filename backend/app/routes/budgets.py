from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user
from app.models import Budget, Category, Transaction, User
from app.schemas import (
    MONTH_PATTERN,
    BudgetOut,
    BudgetSet,
    BudgetStatus,
    BudgetStatusReport,
)
from app.services.ownership import get_owned_category

router = APIRouter(prefix="/api/budgets", tags=["budgets"])

ZERO = Decimal("0.00")


def month_start(text: str) -> date:
    year, month = text.split("-")
    return date(int(year), int(month), 1)


def month_label(d: date) -> str:
    return d.strftime("%Y-%m")


def next_month(d: date) -> date:
    return date(d.year + (d.month == 12), d.month % 12 + 1, 1)


def resolve_month(month: str | None) -> date:
    return month_start(month) if month else date.today().replace(day=1)


def budget_rows(db: Session, user: User, start: date):
    """This user's budgets for one month, overall budget first."""
    return (
        db.query(Budget, Category.name)
        .outerjoin(Category, Budget.category_id == Category.id)
        .filter(Budget.user_id == user.id, Budget.month == start)
        .order_by(Budget.category_id.is_not(None), Category.name)
        .all()
    )


@router.put("", response_model=BudgetOut)
def set_budget(
    payload: BudgetSet,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    category_name = None
    if payload.category_id is not None:
        category_name = get_owned_category(db, user, payload.category_id).name
    start = month_start(payload.month)

    query = db.query(Budget).filter(Budget.user_id == user.id, Budget.month == start)
    if payload.category_id is None:
        query = query.filter(Budget.category_id.is_(None))
    else:
        query = query.filter(Budget.category_id == payload.category_id)
    budget = query.first()

    if budget:
        budget.amount = payload.amount  # already exists: replace the amount
    else:
        budget = Budget(
            user_id=user.id,
            category_id=payload.category_id,
            month=start,
            amount=payload.amount,
        )
        db.add(budget)
    try:
        db.commit()
    except IntegrityError:  # two requests set the same budget at the same moment
        db.rollback()
        raise HTTPException(status_code=409, detail="Budget changed at the same time, try again")
    db.refresh(budget)
    return BudgetOut(
        id=budget.id,
        category_id=budget.category_id,
        category_name=category_name,
        month=month_label(budget.month),
        amount=budget.amount,
    )


@router.get("", response_model=list[BudgetOut])
def list_budgets(
    month: str | None = Query(default=None, pattern=MONTH_PATTERN),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    start = resolve_month(month)
    return [
        BudgetOut(
            id=b.id,
            category_id=b.category_id,
            category_name=name,
            month=month_label(b.month),
            amount=b.amount,
        )
        for b, name in budget_rows(db, user, start)
    ]


@router.get("/status", response_model=BudgetStatusReport)
def budget_status(
    month: str | None = Query(default=None, pattern=MONTH_PATTERN),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    start = resolve_month(month)
    end = next_month(start)

    # One query: how much was spent in each category this month
    spent_rows = db.execute(
        select(Transaction.category_id, func.sum(Transaction.amount))
        .where(
            Transaction.user_id == user.id,
            Transaction.date >= start,
            Transaction.date < end,
        )
        .group_by(Transaction.category_id)
    ).all()
    spent_by_category = {cid: total for cid, total in spent_rows}
    total_spent = sum(spent_by_category.values(), ZERO)

    items = []
    for budget, name in budget_rows(db, user, start):
        if budget.category_id is None:
            spent = total_spent
        else:
            spent = spent_by_category.get(budget.category_id, ZERO)
        percent = (spent / budget.amount * 100).quantize(Decimal("0.1"))
        if spent > budget.amount:
            state = "over"
        elif percent >= 80:
            state = "warning"
        else:
            state = "ok"
        items.append(
            BudgetStatus(
                budget_id=budget.id,
                category_id=budget.category_id,
                category_name=name or "Overall",
                budget=budget.amount,
                spent=spent,
                remaining=budget.amount - spent,
                percent_used=percent,
                state=state,
            )
        )
    return BudgetStatusReport(month=month_label(start), items=items)


@router.delete("/{budget_id}", status_code=204)
def delete_budget(
    budget_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    budget = (
        db.query(Budget)
        .filter(Budget.id == budget_id, Budget.user_id == user.id)
        .first()
    )
    if budget is None:
        raise HTTPException(status_code=404, detail="Budget not found")
    db.delete(budget)
    db.commit()
    return Response(status_code=204)
