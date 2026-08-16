"""POST /api/model/retrain — refit the classifier on stored transactions."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.s03_db import get_session
from app.core.s04_models import User
from app.s16a_auth import current_user
from app.pipeline.s09_model import NotEnoughData
from app.s16_schemas import RetrainResult
from app.store.s13_model_service import retrain

router = APIRouter(prefix="/api", tags=["model"])


@router.post("/model/retrain", response_model=RetrainResult)
def retrain_model(
    session: Session = Depends(get_session),
    user: User = Depends(current_user),
):
    """Train on every rule- and user-labelled row, then save the model.

    Retraining is manual on purpose. Training is the moment user corrections
    take effect, and doing it on a schedule would hide that cause and effect.
    """
    try:
        return retrain(session)
    except NotEnoughData as error:
        raise HTTPException(status_code=400, detail=str(error))
