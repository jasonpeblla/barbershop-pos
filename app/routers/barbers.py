from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List, Optional
from pydantic import BaseModel
from datetime import datetime, date, timedelta

from app.database import get_db
from app.models import Barber, TimeClock, Order, Payment

router = APIRouter(prefix="/barbers", tags=["barbers"])


class BarberCreate(BaseModel):
    name: str
    phone: Optional[str] = None
    email: Optional[str] = None
    commission_rate: float = 0.5
    specialties: Optional[str] = None


class BarberUpdate(BaseModel):
    name: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    commission_rate: Optional[float] = None
    specialties: Optional[str] = None
    is_active: Optional[bool] = None
    is_available: Optional[bool] = None


class BarberResponse(BaseModel):
    id: int
    name: str
    phone: Optional[str]
    email: Optional[str]
    commission_rate: float
    specialties: Optional[str]
    is_active: bool
    is_available: bool
    created_at: datetime

    class Config:
        from_attributes = True


@router.get("/", response_model=List[BarberResponse])
def list_barbers(active_only: bool = False, db: Session = Depends(get_db)):
    query = db.query(Barber)
    if active_only:
        query = query.filter(Barber.is_active == True)
    return query.all()


@router.get("/available")
def list_available_barbers(db: Session = Depends(get_db)):
    """Get barbers who are currently available (clocked in and not busy)"""
    barbers = db.query(Barber).filter(
        Barber.is_active == True,
        Barber.is_available == True
    ).all()
    
    result = []
    for barber in barbers:
        # Check if clocked in today
        today = date.today()
        clock = db.query(TimeClock).filter(
            TimeClock.barber_id == barber.id,
            func.date(TimeClock.clock_in) == today,
            TimeClock.clock_out == None
        ).first()
        
        # Count active orders
        active_orders = db.query(Order).filter(
            Order.barber_id == barber.id,
            Order.status == "in_progress"
        ).count()
        
        result.append({
            **BarberResponse.model_validate(barber).model_dump(),
            "is_clocked_in": clock is not None,
            "active_orders": active_orders
        })
    
    return result


@router.get("/{barber_id}", response_model=BarberResponse)
def get_barber(barber_id: int, db: Session = Depends(get_db)):
    barber = db.query(Barber).filter(Barber.id == barber_id).first()
    if not barber:
        raise HTTPException(status_code=404, detail="Barber not found")
    return barber


@router.post("/", response_model=BarberResponse)
def create_barber(barber: BarberCreate, db: Session = Depends(get_db)):
    db_barber = Barber(**barber.model_dump())
    db.add(db_barber)
    db.commit()
    db.refresh(db_barber)
    return db_barber


@router.patch("/{barber_id}", response_model=BarberResponse)
def update_barber(barber_id: int, barber: BarberUpdate, db: Session = Depends(get_db)):
    db_barber = db.query(Barber).filter(Barber.id == barber_id).first()
    if not db_barber:
        raise HTTPException(status_code=404, detail="Barber not found")
    
    update_data = barber.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(db_barber, field, value)
    
    db.commit()
    db.refresh(db_barber)
    return db_barber


@router.post("/{barber_id}/clock-in")
def clock_in(barber_id: int, db: Session = Depends(get_db)):
    barber = db.query(Barber).filter(Barber.id == barber_id).first()
    if not barber:
        raise HTTPException(status_code=404, detail="Barber not found")
    
    # Check if already clocked in
    today = date.today()
    existing = db.query(TimeClock).filter(
        TimeClock.barber_id == barber_id,
        func.date(TimeClock.clock_in) == today,
        TimeClock.clock_out == None
    ).first()
    
    if existing:
        raise HTTPException(status_code=400, detail="Already clocked in")
    
    entry = TimeClock(barber_id=barber_id)
    db.add(entry)
    barber.is_available = True
    db.commit()
    
    return {"message": "Clocked in", "time": entry.clock_in}


@router.post("/{barber_id}/clock-out")
def clock_out(barber_id: int, db: Session = Depends(get_db)):
    barber = db.query(Barber).filter(Barber.id == barber_id).first()
    if not barber:
        raise HTTPException(status_code=404, detail="Barber not found")
    
    today = date.today()
    entry = db.query(TimeClock).filter(
        TimeClock.barber_id == barber_id,
        func.date(TimeClock.clock_in) == today,
        TimeClock.clock_out == None
    ).first()
    
    if not entry:
        raise HTTPException(status_code=400, detail="Not clocked in")
    
    entry.clock_out = datetime.utcnow()
    barber.is_available = False
    db.commit()
    
    # Calculate hours worked
    hours = (entry.clock_out - entry.clock_in).total_seconds() / 3600
    
    return {
        "message": "Clocked out",
        "clock_in": entry.clock_in,
        "clock_out": entry.clock_out,
        "hours_worked": round(hours, 2)
    }


@router.get("/{barber_id}/earnings")
def get_barber_earnings(
    barber_id: int,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    db: Session = Depends(get_db)
):
    barber = db.query(Barber).filter(Barber.id == barber_id).first()
    if not barber:
        raise HTTPException(status_code=404, detail="Barber not found")
    
    if not start_date:
        start_date = date.today().replace(day=1)
    if not end_date:
        end_date = date.today()
    
    # Get completed orders in range
    orders = db.query(Order).filter(
        Order.barber_id == barber_id,
        Order.status == "completed",
        func.date(Order.completed_at) >= start_date,
        func.date(Order.completed_at) <= end_date
    ).all()
    
    total_services = len(orders)
    total_revenue = sum(o.subtotal for o in orders)
    total_tips = sum(o.tip for o in orders)
    commission = total_revenue * barber.commission_rate
    
    return {
        "barber_id": barber.id,
        "barber_name": barber.name,
        "period_start": start_date.isoformat(),
        "period_end": end_date.isoformat(),
        "commission_rate": barber.commission_rate,
        "total_services": total_services,
        "total_service_revenue": round(total_revenue, 2),
        "commission_earned": round(commission, 2),
        "total_tips": round(total_tips, 2),
        "total_earnings": round(commission + total_tips, 2)
    }
