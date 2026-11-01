from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user
from app.models import User
from app.schemas import ImportResult
from app.services.csv_import import MAX_BYTES, CsvFormatError, import_transactions

router = APIRouter(prefix="/api/transactions", tags=["import"])


@router.post("/import", response_model=ImportResult)
def import_csv(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    raw = file.file.read(MAX_BYTES + 1)  # never read more than the limit
    try:
        return import_transactions(db, user, raw)
    except CsvFormatError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
