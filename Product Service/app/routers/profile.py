"""The shopper's own profile: age, food/shopping preferences and medical conditions.

Every route works on the logged-in shopper's row and takes no user id, so there is no way to name anyone else.
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy.sql import func

from .. import database, models, oauth2, schemas

router = APIRouter(prefix="/profile", tags=["profile"])


@router.get("", response_model=schemas.ProfileOut)
def get_profile(db: Session = Depends(database.get_db), current_user: models.User = Depends(oauth2.get_current_user)):
    """An empty profile (not a 404) until the shopper has saved something."""
    profile = db.get(models.UserProfile, current_user.id)
    if profile is None:
        return schemas.ProfileOut()
    return profile


@router.put("", response_model=schemas.ProfileOut)
def save_profile(
    body: schemas.ProfileIn,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    """Replace the whole profile with what was sent (send empty lists / null age to clear a field)."""
    profile = db.get(models.UserProfile, current_user.id)
    if profile is None:
        profile = models.UserProfile(user_id=current_user.id)
        db.add(profile)
    profile.age = body.age
    profile.preferences = body.preferences
    profile.medical_conditions = body.medical_conditions
    profile.updated_at = func.now()
    db.commit()
    db.refresh(profile)
    return profile
