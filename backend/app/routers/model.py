"""POST /api/model/retrain — refit the classifier on stored transactions."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db import get_session
from app.ml.trainer import NotEnoughData
from app.schemas import RetrainResult
from app.services.model_service import retrain

router = APIRouter(prefix="/api", tags=["model"])


@router.post("/model/retrain", response_model=RetrainResult)
def retrain_model(session: Session = Depends(get_session)):
    """Train on every rule- and user-labelled row, then save the model.

    Retraining is manual on purpose. Training is the moment user corrections
    take effect, and doing it on a schedule would hide that cause and effect.
    """
    try:
        return retrain(session)
    except NotEnoughData as error:
        raise HTTPException(status_code=400, detail=str(error))
