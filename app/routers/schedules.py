from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime, time
from app.database import SessionLocal
from app.models import BarberSchedule, Barber

router = APIRouter(prefix="/schedules", tags=["Barber Schedules"])


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


class ScheduleCreate(BaseModel):
    barber_id: int
    day_of_week: int  # 0=Monday, 6=Sunday
    start_time: str  # "09:00"
    end_time: str    # "17:00"
    is_available: bool = True


class ScheduleUpdate(BaseModel):
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    is_available: Optional[bool] = None


class DayOffCreate(BaseModel):
    barber_id: int
    date: str  # "2026-02-14"
    reason: Optional[str] = None


@router.get("/barber/{barber_id}")
def get_barber_schedule(barber_id: int, db: Session = Depends(get_db)):
    """Get weekly schedule for a barber"""
    schedules = db.query(BarberSchedule).filter(
        BarberSchedule.barber_id == barber_id
    ).order_by(BarberSchedule.day_of_week).all()
    
    barber = db.query(Barber).filter(Barber.id == barber_id).first()
    if not barber:
        raise HTTPException(status_code=404, detail="Barber not found")
    
    day_names = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    
    return {
        "barber_id": barber_id,
        "barber_name": barber.name,
        "schedules": [
            {
                "id": s.id,
                "day_of_week": s.day_of_week,
                "day_name": day_names[s.day_of_week],
                "start_time": s.start_time,
                "end_time": s.end_time,
                "is_available": s.is_available
            }
            for s in schedules
        ]
    }


@router.post("/")
def create_schedule(schedule: ScheduleCreate, db: Session = Depends(get_db)):
    """Set schedule for a barber on a specific day"""
    # Check if schedule exists for this day
    existing = db.query(BarberSchedule).filter(
        BarberSchedule.barber_id == schedule.barber_id,
        BarberSchedule.day_of_week == schedule.day_of_week
    ).first()
    
    if existing:
        # Update existing
        existing.start_time = schedule.start_time
        existing.end_time = schedule.end_time
        existing.is_available = schedule.is_available
        db.commit()
        return {"message": "Schedule updated", "id": existing.id}
    
    # Create new
    db_schedule = BarberSchedule(
        barber_id=schedule.barber_id,
        day_of_week=schedule.day_of_week,
        start_time=schedule.start_time,
        end_time=schedule.end_time,
        is_available=schedule.is_available
    )
    db.add(db_schedule)
    db.commit()
    db.refresh(db_schedule)
    
    return {"message": "Schedule created", "id": db_schedule.id}


@router.post("/bulk/{barber_id}")
def set_weekly_schedule(barber_id: int, schedules: List[ScheduleCreate], db: Session = Depends(get_db)):
    """Set full weekly schedule for a barber"""
    # Clear existing schedules
    db.query(BarberSchedule).filter(BarberSchedule.barber_id == barber_id).delete()
    
    for schedule in schedules:
        db_schedule = BarberSchedule(
            barber_id=barber_id,
            day_of_week=schedule.day_of_week,
            start_time=schedule.start_time,
            end_time=schedule.end_time,
            is_available=schedule.is_available
        )
        db.add(db_schedule)
    
    db.commit()
    return {"message": f"Set {len(schedules)} schedule entries for barber {barber_id}"}


@router.patch("/{schedule_id}")
def update_schedule(schedule_id: int, update: ScheduleUpdate, db: Session = Depends(get_db)):
    """Update a specific schedule entry"""
    schedule = db.query(BarberSchedule).filter(BarberSchedule.id == schedule_id).first()
    if not schedule:
        raise HTTPException(status_code=404, detail="Schedule not found")
    
    if update.start_time is not None:
        schedule.start_time = update.start_time
    if update.end_time is not None:
        schedule.end_time = update.end_time
    if update.is_available is not None:
        schedule.is_available = update.is_available
    
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


@router.post("/day-off")
def add_day_off(day_off: DayOffCreate, db: Session = Depends(get_db)):
    """Add a day off for a barber"""
    from app.models import BarberDayOff
    
    off_date = datetime.strptime(day_off.date, "%Y-%m-%d").date()
    
    # Check if already exists
    existing = db.query(BarberDayOff).filter(
        BarberDayOff.barber_id == day_off.barber_id,
        BarberDayOff.date == off_date
    ).first()
    
    if existing:
        return {"message": "Day off already exists", "id": existing.id}
    
    db_off = BarberDayOff(
        barber_id=day_off.barber_id,
        date=off_date,
        reason=day_off.reason
    )
    db.add(db_off)
    db.commit()
    db.refresh(db_off)
    
    return {"message": "Day off added", "id": db_off.id}


@router.get("/days-off/{barber_id}")
def get_days_off(barber_id: int, db: Session = Depends(get_db)):
    """Get all days off for a barber"""
    from app.models import BarberDayOff
    
    days_off = db.query(BarberDayOff).filter(
        BarberDayOff.barber_id == barber_id,
        BarberDayOff.date >= datetime.now().date()
    ).order_by(BarberDayOff.date).all()
    
    return [
        {
            "id": d.id,
            "date": d.date.isoformat(),
            "reason": d.reason
        }
        for d in days_off
    ]


@router.delete("/day-off/{day_off_id}")
def remove_day_off(day_off_id: int, db: Session = Depends(get_db)):
    """Remove a day off"""
    from app.models import BarberDayOff
    
    day_off = db.query(BarberDayOff).filter(BarberDayOff.id == day_off_id).first()
    if not day_off:
        raise HTTPException(status_code=404, detail="Day off not found")
    
    db.delete(day_off)
    db.commit()
    return {"message": "Day off removed"}


@router.get("/available-today")
def get_available_barbers_today(db: Session = Depends(get_db)):
    """Get all barbers available today with their hours"""
    from app.models import BarberDayOff
    
    today = datetime.now()
    day_of_week = today.weekday()
    today_date = today.date()
    
    # Get all active barbers
    barbers = db.query(Barber).filter(Barber.is_active == True).all()
    
    available = []
    for barber in barbers:
        # Check if day off
        day_off = db.query(BarberDayOff).filter(
            BarberDayOff.barber_id == barber.id,
            BarberDayOff.date == today_date
        ).first()
        
        if day_off:
            continue
        
        # Get schedule for today
        schedule = db.query(BarberSchedule).filter(
            BarberSchedule.barber_id == barber.id,
            BarberSchedule.day_of_week == day_of_week,
            BarberSchedule.is_available == True
        ).first()
        
        if schedule:
            available.append({
                "barber_id": barber.id,
                "name": barber.name,
                "start_time": schedule.start_time,
                "end_time": schedule.end_time,
                "is_clocked_in": barber.is_available
            })
    
    return available
