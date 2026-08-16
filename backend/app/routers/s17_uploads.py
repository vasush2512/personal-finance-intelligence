"""POST /api/upload — accept a bank statement CSV."""

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from sqlalchemy.orm import Session

from app.core.s03_db import get_session
from app.s16a_auth import current_user
from app.core.s04_models import Account, Upload, User
from app.s16_schemas import UploadDeleted, UploadResult
from app.store.s11_importer import import_statement
from app.pipeline.s07_parser import UnparseableStatement

router = APIRouter(prefix="/api", tags=["uploads"])

# Formats services/readers.py can turn into rows.
SUPPORTED_EXTENSIONS = (".csv", ".txt", ".tsv", ".json", ".xlsx", ".xlsm")

# A ceiling on one upload. A hundred thousand rows of CSV is roughly 12 MB, so
# this is generous for a real statement and still far below what would exhaust
# memory. The whole file has to be held at once — the parsers need random
# access, and an .xlsx is a zip that cannot be streamed — which is exactly why
# there has to be a limit at all.
MAX_UPLOAD_BYTES = 25 * 1024 * 1024

# Read size for the loop below. Large enough not to spend the whole upload in
# syscalls, small enough that the cap is enforced before much is in memory.
_CHUNK = 1024 * 1024


def read_within_limit(upload_file, limit=MAX_UPLOAD_BYTES) -> bytes:
    """Read an upload, refusing anything over the limit.

    Read in chunks and stopped at the ceiling, rather than read whole and
    measured afterwards: checking the size after `.read()` means a two-gigabyte
    file is already in memory by the time it is rejected, which is the attack
    the limit is supposed to prevent.
    """
    chunks = []
    total = 0

    while True:
        chunk = upload_file.read(_CHUNK)
        if not chunk:
            break

        total += len(chunk)
        if total > limit:
            raise HTTPException(
                status_code=413,
                detail=(
                    f"That file is larger than the "
                    f"{limit // (1024 * 1024)} MB upload limit. Split the "
                    f"statement into smaller periods and upload them "
                    f"separately."
                ),
            )
        chunks.append(chunk)

    return b"".join(chunks)


@router.post("/upload", response_model=UploadResult)
def upload_statement(
    file: UploadFile = File(...),
    account_id: int | None = Query(
        None, description="which bank account this statement is from"
    ),
    session: Session = Depends(get_session),
    user: User = Depends(current_user),
):
    """Parse a statement file and store its new rows.

    Deliberately a plain `def`, not `async def`. Everything this does —
    reading the file, parsing it, running the model, writing to SQLite — is
    blocking work. In an `async def` handler that work runs *on* the event
    loop, so a single large upload freezes every other request until it
    finishes; a 20k-row file made /health time out for 30 seconds. Declared
    as `def`, FastAPI runs it in a worker thread and the server stays
    responsive.

    CSV, JSON and Excel are all accepted; the format is worked out from the
    file itself, not trusted from its name.

    Re-uploading the same file is safe: every row is recognised by its
    fingerprint and reported as a duplicate instead of being stored twice.
    That holds across formats too — the same statement as CSV and as JSON
    fingerprints identically, because the fingerprint is built from the
    parsed values, not the file's text.
    """
    filename = file.filename or "upload.csv"
    if not filename.lower().endswith(SUPPORTED_EXTENSIONS):
        raise HTTPException(
            status_code=400,
            detail=(
                "Unsupported file type. Upload one of: "
                f"{', '.join(SUPPORTED_EXTENSIONS)}."
            ),
        )

    content = read_within_limit(file.file)
    if not content:
        raise HTTPException(status_code=400, detail="The uploaded file is empty.")

    try:
        # An account that is not this user's is ignored rather than refused:
        # the statement is still theirs and still worth importing.
        owned_account = None
        if account_id is not None:
            account = session.get(Account, account_id)
            if account is not None and account.user_id == user.id:
                owned_account = account_id

        return import_statement(
            session, filename, content, user_id=user.id, account_id=owned_account
        )
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


@router.delete("/uploads/{upload_id}", response_model=UploadDeleted)
def delete_upload(
    upload_id: int,
    session: Session = Depends(get_session),
    user: User = Depends(current_user),
):
    """Remove an upload and every transaction that came from it.

    Undoing a bad import has to take the rows with it, otherwise the totals
    stay wrong with no way to find the offending rows. Deleting also frees
    those fingerprints, so the file can be uploaded again cleanly.
    """
    upload = session.get(Upload, upload_id)
    # Another user's file is reported missing rather than forbidden.
    if upload is not None and upload.user_id != user.id:
        upload = None
    if upload is None:
        raise HTTPException(status_code=404, detail=f"No upload with id {upload_id}.")

    deleted = len(upload.transactions)
    filename = upload.filename

    session.delete(upload)
    session.commit()

    return UploadDeleted(
        upload_id=upload_id, filename=filename, transactions_deleted=deleted
    )
