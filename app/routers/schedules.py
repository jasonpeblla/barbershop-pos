"""Barber Schedule Management Router"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import and_
from datetime import datetime, date, time
from typing import List, Optional
from pydantic import BaseModel

from app.database import get_db
from app.models import BarberSchedule, BarberTimeOff, Barber

router = APIRouter(prefix="/schedules", tags=["schedules"])


class ScheduleCreate(BaseModel):
    barber_id: int
    day_of_week: int  # 0=Monday, 6=Sunday
    start_time: str  # "09:00"
    end_time: str  # "18:00"
    is_active: bool = True


class ScheduleUpdate(BaseModel):
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    is_active: Optional[bool] = None


class TimeOffCreate(BaseModel):
    barber_id: int
    start_date: str  # "2024-02-20"
    end_date: str
    reason: Optional[str] = None
    is_approved: bool = True


class ScheduleResponse(BaseModel):
    id: int
    barber_id: int
    barber_name: str
    day_of_week: int
    day_name: str
    start_time: str
    end_time: str
    is_active: bool

    class Config:
        from_attributes = True


@router.get("/barber/{barber_id}")
def get_barber_schedule(barber_id: int, db: Session = Depends(get_db)):
    """Get weekly schedule for a barber"""
    barber = db.query(Barber).filter(Barber.id == barber_id).first()
    if not barber:
        raise HTTPException(status_code=404, detail="Barber not found")
    
    schedules = db.query(BarberSchedule).filter(
        BarberSchedule.barber_id == barber_id
    ).order_by(BarberSchedule.day_of_week).all()
    
    day_names = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    
    return [{
        "id": s.id,
        "barber_id": s.barber_id,
        "barber_name": barber.name,
        "day_of_week": s.day_of_week,
        "day_name": day_names[s.day_of_week],
        "start_time": s.start_time,
        "end_time": s.end_time,
        "is_active": s.is_active
    } for s in schedules]


@router.post("/")
def create_schedule(schedule: ScheduleCreate, db: Session = Depends(get_db)):
    """Create a schedule entry for a barber"""
    barber = db.query(Barber).filter(Barber.id == schedule.barber_id).first()
    if not barber:
        raise HTTPException(status_code=404, detail="Barber not found")
    
    # Check for existing schedule on this day
    existing = db.query(BarberSchedule).filter(
        and_(
            BarberSchedule.barber_id == schedule.barber_id,
            BarberSchedule.day_of_week == schedule.day_of_week
        )
    ).first()
    
    if existing:
        raise HTTPException(status_code=400, detail="Schedule already exists for this day")
    
    db_schedule = BarberSchedule(
        barber_id=schedule.barber_id,
        day_of_week=schedule.day_of_week,
        start_time=schedule.start_time,
        end_time=schedule.end_time,
        is_active=schedule.is_active
    )
    db.add(db_schedule)
    db.commit()
    db.refresh(db_schedule)
    
    return {"message": "Schedule created", "id": db_schedule.id}


@router.put("/{schedule_id}")
def update_schedule(schedule_id: int, update: ScheduleUpdate, db: Session = Depends(get_db)):
    """Update a schedule entry"""
    schedule = db.query(BarberSchedule).filter(BarberSchedule.id == schedule_id).first()
    if not schedule:
        raise HTTPException(status_code=404, detail="Schedule not found")
    
    if update.start_time is not None:
        schedule.start_time = update.start_time
    if update.end_time is not None:
        schedule.end_time = update.end_time
    if update.is_active is not None:
        schedule.is_active = update.is_active
    
    db.commit()
    return {"message": "Schedule updated"}


@router.delete("/{schedule_id}")
def delete_schedule(schedule_id: int, db: Session = Depends(get_db)):
    """Delete a schedule entry"""
    schedule = db.query(BarberSchedule).filter(BarberSchedule.id == schedule_id).first()
    if not schedule:
        raise HTTPException(status_code=404, detail="Schedule not found")
    
    db.delete(schedule)
    db.commit()
    return {"message": "Schedule deleted"}


@router.post("/bulk/{barber_id}")
def create_default_schedule(barber_id: int, db: Session = Depends(get_db)):
    """Create default Mon-Sat 9-6 schedule for barber"""
    barber = db.query(Barber).filter(Barber.id == barber_id).first()
    if not barber:
        raise HTTPException(status_code=404, detail="Barber not found")
    
    # Delete existing schedules
    db.query(BarberSchedule).filter(BarberSchedule.barber_id == barber_id).delete()
    
    # Create Mon-Sat 9-6
    for day in range(6):  # 0-5 = Mon-Sat
        schedule = BarberSchedule(
            barber_id=barber_id,
            day_of_week=day,
            start_time="09:00",
            end_time="18:00",
            is_active=True
        )
        db.add(schedule)
    
    # Sunday off
    sunday = BarberSchedule(
        barber_id=barber_id,
        day_of_week=6,
        start_time="00:00",
        end_time="00:00",
        is_active=False
    )
    db.add(sunday)
    
    db.commit()
    return {"message": "Default schedule created for barber", "barber_id": barber_id}


# Time Off Management
@router.get("/time-off/{barber_id}")
def get_time_off(barber_id: int, db: Session = Depends(get_db)):
    """Get time off requests for a barber"""
    time_offs = db.query(BarberTimeOff).filter(
        BarberTimeOff.barber_id == barber_id
    ).order_by(BarberTimeOff.start_date.desc()).all()
    
    return [{
        "id": t.id,
        "barber_id": t.barber_id,
        "start_date": t.start_date,
        "end_date": t.end_date,
        "reason": t.reason,
        "is_approved": t.is_approved,
        "created_at": t.created_at.isoformat() if t.created_at else None
    } for t in time_offs]


@router.post("/time-off")
def request_time_off(request: TimeOffCreate, db: Session = Depends(get_db)):
    """Request time off for a barber"""
    barber = db.query(Barber).filter(Barber.id == request.barber_id).first()
    if not barber:
        raise HTTPException(status_code=404, detail="Barber not found")
    
    time_off = BarberTimeOff(
        barber_id=request.barber_id,
        start_date=request.start_date,
        end_date=request.end_date,
        reason=request.reason,
        is_approved=request.is_approved
    )
    db.add(time_off)
    db.commit()
    db.refresh(time_off)
    
    return {"message": "Time off request created", "id": time_off.id}


@router.delete("/time-off/{time_off_id}")
def cancel_time_off(time_off_id: int, db: Session = Depends(get_db)):
    """Cancel a time off request"""
    time_off = db.query(BarberTimeOff).filter(BarberTimeOff.id == time_off_id).first()
    if not time_off:
        raise HTTPException(status_code=404, detail="Time off not found")
    
    db.delete(time_off)
    db.commit()
    return {"message": "Time off cancelled"}


@router.get("/working-today")
def get_barbers_working_today(db: Session = Depends(get_db)):
    """Get list of barbers scheduled to work today"""
    today = datetime.now()
    day_of_week = today.weekday()  # 0=Monday
    today_str = today.strftime("%Y-%m-%d")
    
    # Get barbers with active schedules today
    schedules = db.query(BarberSchedule).filter(
        and_(
            BarberSchedule.day_of_week == day_of_week,
            BarberSchedule.is_active == True
        )
    ).all()
    
    barber_ids = [s.barber_id for s in schedules]
    
    # Exclude barbers on time off
    time_offs = db.query(BarberTimeOff).filter(
        and_(
            BarberTimeOff.start_date <= today_str,
            BarberTimeOff.end_date >= today_str,
            BarberTimeOff.is_approved == True
        )
    ).all()
    
    off_barber_ids = [t.barber_id for t in time_offs]
    
    working_barber_ids = [bid for bid in barber_ids if bid not in off_barber_ids]
    
    barbers = db.query(Barber).filter(
        and_(
            Barber.id.in_(working_barber_ids),
            Barber.is_active == True
        )
    ).all()
    
    result = []
    for barber in barbers:
        schedule = next((s for s in schedules if s.barber_id == barber.id), None)
        result.append({
            "id": barber.id,
            "name": barber.name,
            "start_time": schedule.start_time if schedule else None,
            "end_time": schedule.end_time if schedule else None,
            "is_clocked_in": barber.is_available
        })
    
    return result


@router.get("/availability/{barber_id}/{date}")
def check_barber_availability(barber_id: int, date: str, db: Session = Depends(get_db)):
    """Check if barber is available on a specific date"""
    barber = db.query(Barber).filter(Barber.id == barber_id).first()
    if not barber:
        raise HTTPException(status_code=404, detail="Barber not found")
    
    # Parse date
    try:
        check_date = datetime.strptime(date, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format")
    
    day_of_week = check_date.weekday()
    
    # Check schedule
    schedule = db.query(BarberSchedule).filter(
        and_(
            BarberSchedule.barber_id == barber_id,
            BarberSchedule.day_of_week == day_of_week
        )
    ).first()
    
    if not schedule or not schedule.is_active:
        return {
            "barber_id": barber_id,
            "date": date,
            "is_available": False,
            "reason": "Not scheduled to work"
        }
    
    # Check time off
    time_off = db.query(BarberTimeOff).filter(
        and_(
            BarberTimeOff.barber_id == barber_id,
            BarberTimeOff.start_date <= date,
            BarberTimeOff.end_date >= date,
            BarberTimeOff.is_approved == True
        )
    ).first()
    
    if time_off:
        return {
            "barber_id": barber_id,
            "date": date,
            "is_available": False,
            "reason": f"Time off: {time_off.reason or 'Personal'}"
        }
    
    return {
        "barber_id": barber_id,
        "date": date,
        "is_available": True,
        "working_hours": {
            "start": schedule.start_time,
            "end": schedule.end_time
        }
    }
