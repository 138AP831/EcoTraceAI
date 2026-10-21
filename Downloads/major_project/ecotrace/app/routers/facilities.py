"""Facility endpoints."""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Facility
from app.schemas import FacilityCreate, FacilityOut

router = APIRouter(prefix="/facilities", tags=["facilities"])


@router.post("", response_model=FacilityOut, status_code=status.HTTP_201_CREATED)
def create_facility(payload: FacilityCreate, db: Session = Depends(get_db)):
    data = payload.model_dump(exclude_unset=True)
    fac = Facility(**data)
    db.add(fac)
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise HTTPException(status_code=409, detail="facility_unique_constraint_violation")
    db.refresh(fac)
    return fac


@router.get("", response_model=list[FacilityOut])
def list_facilities(db: Session = Depends(get_db)):
    return db.query(Facility).order_by(Facility.created_at).all()


@router.get("/{facility_id}", response_model=FacilityOut)
def get_facility(facility_id: str, db: Session = Depends(get_db)):
    fac = db.get(Facility, facility_id)
    if not fac:
        raise HTTPException(status_code=404, detail="facility_not_found")
    return fac
