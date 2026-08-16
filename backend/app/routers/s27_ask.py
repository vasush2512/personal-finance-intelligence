"""POST /api/ask — answering typed questions about the data.

Deliberately not called an AI endpoint anywhere, in the code or in the UI,
because there is no model behind it. It recognises a fixed set of question
shapes by keyword and maps them onto the same aggregations the dashboard uses.
Calling that "AI" would be a claim the implementation does not support.

A question it cannot parse comes back with understood=false and a list of
shapes it does handle — never a guess.
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.s03_db import get_session
from app.core.s04_models import User
from app.s16a_auth import current_user
from app.pipeline.s10g_assistant import EXAMPLES
from app.s16_schemas import Answer, AskRequest
from app.store.s12e_assistant import answer

router = APIRouter(prefix="/api", tags=["ask"])

# Long enough for any real question, short enough that the endpoint cannot be
# used to push a large body through the parser.
MAX_QUESTION_LENGTH = 300


@router.get("/ask/examples", response_model=list[str])
def get_examples():
    """Questions that are known to work, for the UI to offer as buttons."""
    return EXAMPLES


@router.post("/ask", response_model=Answer)
def ask(
    body: AskRequest,
    upload_id: int | None = Query(None),
    sheet: str | None = Query(None),
    account_id: int | None = Query(
        None, description="restrict to one bank account"
    ),
    entry_source: str | None = Query(
        None, description="'statement' or 'manual'; omit for both"
    ),
    session: Session = Depends(get_session),
    user: User = Depends(current_user),
):
    """Answer a question from the transactions, or say why it cannot.

    The response carries `explanation` — a sentence naming exactly what was
    counted — and `filters`, so the UI can offer to show the rows behind the
    number. Answering a different question well is the commonest failure of an
    interface like this, and both fields exist to make that visible.
    """
    question = (body.question or "")[:MAX_QUESTION_LENGTH]
    return answer(session, question, upload_id=upload_id, sheet=sheet, user_id=user.id,
        account_id=account_id,
        entry_source=entry_source)
