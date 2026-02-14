from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List, Optional
from pydantic import BaseModel
from datetime import datetime, date, timedelta

from app.database import get_db
from app.models import Barber, TimeClock, Order, Payment, BarberBreak

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


# ===== BREAK MANAGEMENT =====

class BreakStart(BaseModel):
    break_type: str = "short"  # lunch, short, personal
    duration_minutes: Optional[int] = None  # If set, auto-schedules end time
    notes: Optional[str] = None


BREAK_DURATIONS = {
    "short": 15,
    "lunch": 30,
    "personal": 15
}


@router.post("/{barber_id}/break/start")
def start_break(barber_id: int, data: BreakStart, db: Session = Depends(get_db)):
    """Start a break for a barber"""
    barber = db.query(Barber).filter(Barber.id == barber_id).first()
    if not barber:
        raise HTTPException(status_code=404, detail="Barber not found")
    
    # Check if already on break
    active_break = db.query(BarberBreak).filter(
        BarberBreak.barber_id == barber_id,
        BarberBreak.end_time.is_(None)
    ).first()
    
    if active_break:
        raise HTTPException(status_code=400, detail="Already on break")
    
    # Calculate scheduled end time
    duration = data.duration_minutes or BREAK_DURATIONS.get(data.break_type, 15)
    scheduled_end = datetime.utcnow() + timedelta(minutes=duration)
    
    # Create break record
    break_record = BarberBreak(
        barber_id=barber_id,
        break_type=data.break_type,
        scheduled_end_time=scheduled_end,
        notes=data.notes
    )
    db.add(break_record)
    
    # Mark barber as unavailable
    barber.is_available = False
    db.commit()
    db.refresh(break_record)
    
    return {
        "message": f"Break started ({data.break_type})",
        "break_id": break_record.id,
        "start_time": break_record.start_time,
        "scheduled_end": scheduled_end,
        "duration_minutes": duration
    }


@router.post("/{barber_id}/break/end")
def end_break(barber_id: int, db: Session = Depends(get_db)):
    """End a barber's current break"""
    barber = db.query(Barber).filter(Barber.id == barber_id).first()
    if not barber:
        raise HTTPException(status_code=404, detail="Barber not found")
    
    active_break = db.query(BarberBreak).filter(
        BarberBreak.barber_id == barber_id,
        BarberBreak.end_time.is_(None)
    ).first()
    
    if not active_break:
        raise HTTPException(status_code=400, detail="Not currently on break")
    
    active_break.end_time = datetime.utcnow()
    barber.is_available = True
    db.commit()
    
    duration = (active_break.end_time - active_break.start_time).total_seconds() / 60
    
    return {
        "message": "Break ended",
        "break_type": active_break.break_type,
        "duration_minutes": round(duration, 1),
        "was_over_scheduled": duration > (active_break.scheduled_end_time - active_break.start_time).total_seconds() / 60 if active_break.scheduled_end_time else False
    }


@router.get("/{barber_id}/break/status")
def get_break_status(barber_id: int, db: Session = Depends(get_db)):
    """Check if barber is currently on break"""
    barber = db.query(Barber).filter(Barber.id == barber_id).first()
    if not barber:
        raise HTTPException(status_code=404, detail="Barber not found")
    
    active_break = db.query(BarberBreak).filter(
        BarberBreak.barber_id == barber_id,
        BarberBreak.end_time.is_(None)
    ).first()
    
    if not active_break:
        return {
            "on_break": False,
            "barber_name": barber.name,
            "is_available": barber.is_available
        }
    
    elapsed = (datetime.utcnow() - active_break.start_time).total_seconds() / 60
    remaining = 0
    over_time = False
    
    if active_break.scheduled_end_time:
        remaining = (active_break.scheduled_end_time - datetime.utcnow()).total_seconds() / 60
        if remaining < 0:
            over_time = True
            remaining = abs(remaining)
    
    return {
        "on_break": True,
        "barber_name": barber.name,
        "break_type": active_break.break_type,
        "start_time": active_break.start_time,
        "elapsed_minutes": round(elapsed, 1),
        "scheduled_end": active_break.scheduled_end_time,
        "remaining_minutes": round(remaining, 1) if not over_time else 0,
        "over_time": over_time,
        "over_by_minutes": round(remaining, 1) if over_time else 0
    }


@router.get("/breaks/active")
def get_all_active_breaks(db: Session = Depends(get_db)):
    """Get all barbers currently on break"""
    active_breaks = db.query(BarberBreak).filter(
        BarberBreak.end_time.is_(None)
    ).all()
    
    result = []
    for brk in active_breaks:
        barber = db.query(Barber).filter(Barber.id == brk.barber_id).first()
        elapsed = (datetime.utcnow() - brk.start_time).total_seconds() / 60
        
        over_time = False
        remaining = 0
        if brk.scheduled_end_time:
            remaining = (brk.scheduled_end_time - datetime.utcnow()).total_seconds() / 60
            if remaining < 0:
                over_time = True
                remaining = abs(remaining)
        
        result.append({
            "break_id": brk.id,
            "barber_id": brk.barber_id,
            "barber_name": barber.name if barber else "Unknown",
            "break_type": brk.break_type,
            "start_time": brk.start_time,
            "elapsed_minutes": round(elapsed, 1),
            "over_time": over_time,
            "over_by_minutes": round(remaining, 1) if over_time else 0
        })
    
    return result


@router.get("/{barber_id}/breaks/today")
def get_barber_breaks_today(barber_id: int, db: Session = Depends(get_db)):
    """Get all breaks for a barber today"""
    today = date.today()
    
    breaks = db.query(BarberBreak).filter(
        BarberBreak.barber_id == barber_id,
        func.date(BarberBreak.start_time) == today
    ).order_by(BarberBreak.start_time).all()
    
    total_break_time = 0
    for brk in breaks:
        if brk.end_time:
            total_break_time += (brk.end_time - brk.start_time).total_seconds() / 60
    
    return {
        "barber_id": barber_id,
        "date": today.isoformat(),
        "total_break_minutes": round(total_break_time, 1),
        "break_count": len([b for b in breaks if b.end_time]),
        "breaks": [
            {
                "id": b.id,
                "break_type": b.break_type,
                "start_time": b.start_time,
                "end_time": b.end_time,
                "duration_minutes": round((b.end_time - b.start_time).total_seconds() / 60, 1) if b.end_time else None
            }
            for b in breaks
        ]
    }
