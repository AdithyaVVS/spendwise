from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session, joinedload

from app.database import get_db
from app.dependencies import get_current_user
from app.models import Transaction, User
from app.schemas import TransactionCreate, TransactionOut, TransactionUpdate
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


@router.get("", response_model=list[TransactionOut])
def list_transactions(
    db: Session = Depends(get_db), user: User = Depends(get_current_user)
):
    rows = (
        db.query(Transaction)
        .options(joinedload(Transaction.category))
        .filter(Transaction.user_id == user.id)
        .order_by(Transaction.date.desc(), Transaction.id.desc())
        .all()
    )
    return [to_out(t) for t in rows]


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
