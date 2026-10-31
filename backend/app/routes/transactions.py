import math
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.database import get_db
from app.dependencies import get_current_user
from app.models import Transaction, User
from app.schemas import (
    TransactionCreate,
    TransactionOut,
    TransactionPage,
    TransactionUpdate,
)
from app.services.ownership import get_owned_category, get_owned_transaction

router = APIRouter(prefix="/api/transactions", tags=["transactions"])


def to_out(t: Transaction) -> TransactionOut:
    return TransactionOut(
        id=t.id,
        category_id=t.category_id,
        category_name=t.category.name,
        amount=t.amount,
        description=t.description,
        date=t.date,
        created_at=t.created_at,
    )


@router.post("", response_model=TransactionOut, status_code=201)
def create_transaction(
    payload: TransactionCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    get_owned_category(db, user, payload.category_id)  # must be YOUR category
    transaction = Transaction(
        user_id=user.id,
        category_id=payload.category_id,
        amount=payload.amount,
        description=payload.description,
        date=payload.date,
    )
    db.add(transaction)
    db.commit()
    db.refresh(transaction)
    return to_out(transaction)


@router.get("", response_model=TransactionPage)
def list_transactions(
    date_from: date | None = None,
    date_to: date | None = None,
    category_id: int | None = None,
    search: str | None = Query(default=None, max_length=100),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if date_from and date_to and date_from > date_to:
        raise HTTPException(status_code=422, detail="date_from must not be after date_to")

    # Every filter list starts with the owner check, so isolation always applies.
    filters = [Transaction.user_id == user.id]
    if date_from:
        filters.append(Transaction.date >= date_from)
    if date_to:
        filters.append(Transaction.date <= date_to)
    if category_id is not None:
        filters.append(Transaction.category_id == category_id)
    if search and search.strip():
        term = search.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        filters.append(Transaction.description.ilike(f"%{term}%", escape="\\"))

    # One query for the count and the money total of ALL matching rows
    total, total_amount = db.execute(
        select(func.count(Transaction.id), func.coalesce(func.sum(Transaction.amount), 0)).where(*filters)
    ).one()

    rows = (
        db.query(Transaction)
        .options(joinedload(Transaction.category))
        .filter(*filters)
        .order_by(Transaction.date.desc(), Transaction.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    return TransactionPage(
        items=[to_out(t) for t in rows],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=max(1, math.ceil(total / page_size)),
        total_amount=total_amount,
    )


@router.get("/{transaction_id}", response_model=TransactionOut)
def get_transaction(
    transaction_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return to_out(get_owned_transaction(db, user, transaction_id))


@router.put("/{transaction_id}", response_model=TransactionOut)
def update_transaction(
    transaction_id: int,
    payload: TransactionUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    transaction = get_owned_transaction(db, user, transaction_id)
    data = payload.model_dump(exclude_unset=True)

    for field in ("category_id", "amount", "date"):
        if field in data and data[field] is None:
            raise HTTPException(status_code=422, detail=f"{field} cannot be null")
    if "category_id" in data:
        get_owned_category(db, user, data["category_id"])

    for field, value in data.items():
        setattr(transaction, field, value)
    db.commit()
    db.refresh(transaction)
    return to_out(transaction)


@router.delete("/{transaction_id}", status_code=204)
def delete_transaction(
    transaction_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    transaction = get_owned_transaction(db, user, transaction_id)
    db.delete(transaction)
    db.commit()
    return Response(status_code=204)
