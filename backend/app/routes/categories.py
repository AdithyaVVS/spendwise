from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user
from app.models import Category, Transaction, User
from app.schemas import CategoryCreate, CategoryOut
from app.services.ownership import get_owned_category

router = APIRouter(prefix="/api/categories", tags=["categories"])

DUPLICATE = "You already have a category with this name"


@router.post("", response_model=CategoryOut, status_code=201)
def create_category(
    payload: CategoryCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    category = Category(user_id=user.id, name=payload.name)
    db.add(category)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail=DUPLICATE)
    db.refresh(category)
    return category


@router.get("", response_model=list[CategoryOut])
def list_categories(
    db: Session = Depends(get_db), user: User = Depends(get_current_user)
):
    return (
        db.query(Category)
        .filter(Category.user_id == user.id)
        .order_by(Category.name)
        .all()
    )


@router.put("/{category_id}", response_model=CategoryOut)
def rename_category(
    category_id: int,
    payload: CategoryCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    category = get_owned_category(db, user, category_id)
    category.name = payload.name
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail=DUPLICATE)
    db.refresh(category)
    return category


@router.delete("/{category_id}", status_code=204)
def delete_category(
    category_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    category = get_owned_category(db, user, category_id)
    in_use = db.query(Transaction.id).filter(Transaction.category_id == category.id).first()
    if in_use:
        raise HTTPException(
            status_code=409,
            detail="This category has transactions. Move or delete them first.",
        )
    db.delete(category)
    try:
        db.commit()
    except IntegrityError:  # a transaction was added at the same moment
        db.rollback()
        raise HTTPException(status_code=409, detail="This category has transactions.")
    return Response(status_code=204)
