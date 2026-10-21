"""Producer and obligation endpoints."""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import ObligationRecord, Producer
from app.schemas import ObligationCreate, ObligationOut, ProducerCreate, ProducerOut

router = APIRouter(prefix="/producers", tags=["producers"])


@router.post("", response_model=ProducerOut, status_code=status.HTTP_201_CREATED)
def create_producer(payload: ProducerCreate, db: Session = Depends(get_db)):
    data = payload.model_dump(exclude_unset=True)
    prod = Producer(**data)
    db.add(prod)
    db.commit()
    db.refresh(prod)
    return prod


@router.post("/{producer_id}/obligations", response_model=ObligationOut, status_code=status.HTTP_201_CREATED)
def create_obligation(producer_id: str, payload: ObligationCreate, db: Session = Depends(get_db)):
    producer = db.get(Producer, producer_id)
    if not producer:
        raise HTTPException(status_code=404, detail="producer_not_found")
    data = payload.model_dump(exclude_unset=True)
    data["producer_id"] = producer_id
    data.setdefault("fulfilled_kg", 0.0)
    obl = ObligationRecord(**data)
    db.add(obl)
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise HTTPException(status_code=409, detail="obligation_unique_constraint_violation")
    db.refresh(obl)
    return obl


@router.get("/{producer_id}/obligations", response_model=list[ObligationOut])
def list_obligations(producer_id: str, db: Session = Depends(get_db)):
    producer = db.get(Producer, producer_id)
    if not producer:
        raise HTTPException(status_code=404, detail="producer_not_found")
    return db.query(ObligationRecord).filter(ObligationRecord.producer_id == producer_id).all()
