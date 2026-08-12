"""POST /api/upload — accept a bank statement CSV."""

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.db import get_session
from app.schemas import UploadResult
from app.services.importer import import_statement
from app.services.parser import UnparseableStatement

router = APIRouter(prefix="/api", tags=["uploads"])


@router.post("/upload", response_model=UploadResult)
async def upload_statement(
    file: UploadFile = File(...),
    session: Session = Depends(get_session),
):
    """Parse a CSV and store its new rows.

    Re-uploading the same file is safe: every row is recognised by its
    fingerprint and reported as a duplicate instead of being stored twice.
    """
    filename = file.filename or "upload.csv"
    if not filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only .csv files are supported.")

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="The uploaded file is empty.")

    try:
        return import_statement(session, filename, content)
    except UnparseableStatement as error:
        # The parser could not find a header row. Hand back the column names
        # it did see so the UI can tell the user what was wrong with the file.
        raise HTTPException(
            status_code=400,
            detail={
                "message": str(error),
                "detected_columns": error.detected_columns,
            },
        )
