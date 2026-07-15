"""Profiles API — פרופילי מדפסות מובנים ומותאמים אישית."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import PrinterProfile
from ..schemas import ProfileIn, ProfileOut

router = APIRouter(prefix="/api/v1/profiles", tags=["profiles"])


@router.get("", response_model=list[ProfileOut])
def list_profiles(db: Session = Depends(get_db)):
    return db.query(PrinterProfile).order_by(PrinterProfile.is_builtin.desc(),
                                             PrinterProfile.name).all()


@router.post("", response_model=ProfileOut, status_code=201)
def create_profile(profile: ProfileIn, db: Session = Depends(get_db)):
    if db.query(PrinterProfile).filter_by(name=profile.name).first():
        raise HTTPException(409, "פרופיל בשם זה כבר קיים")
    p = PrinterProfile(**profile.model_dump(), is_builtin=False)
    db.add(p)
    db.commit()
    return p


@router.delete("/{profile_id}", status_code=204)
def delete_profile(profile_id: str, db: Session = Depends(get_db)):
    p = db.get(PrinterProfile, profile_id)
    if p is None:
        raise HTTPException(404, "פרופיל לא נמצא")
    if p.is_builtin:
        raise HTTPException(403, "לא ניתן למחוק פרופיל מובנה")
    db.delete(p)
    db.commit()
