from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime, date, timedelta

from app.database import get_db
from app.models import BusinessHours, Holiday

router = APIRouter(prefix="/business", tags=["Business Hours"])

DAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


class HoursUpdate(BaseModel):
    open_time: Optional[str] = None  # "09:00"
    close_time: Optional[str] = None
    is_closed: bool = False


class HolidayCreate(BaseModel):
    date: str  # "2026-02-14"
    name: str
    is_closed: bool = True
    modified_hours: Optional[str] = None  # "10:00-14:00"


# ===== BUSINESS HOURS =====

@router.get("/hours")
def get_business_hours(db: Session = Depends(get_db)):
    """Get all business hours"""
    hours = db.query(BusinessHours).order_by(BusinessHours.day_of_week).all()
    
    # If no hours set, return defaults
    if not hours:
        return {
            "hours": [
                {"day": i, "day_name": DAY_NAMES[i], "open": "09:00", "close": "19:00", "is_closed": i == 6}
                for i in range(7)
            ],
            "is_default": True
        }
    
    return {
        "hours": [
            {
                "day": h.day_of_week,
                "day_name": DAY_NAMES[h.day_of_week],
                "open": h.open_time,
                "close": h.close_time,
                "is_closed": h.is_closed
            }
            for h in hours
        ],
        "is_default": False
    }


@router.post("/hours/{day_of_week}")
def set_hours(day_of_week: int, hours: HoursUpdate, db: Session = Depends(get_db)):
    """Set hours for a specific day"""
    if day_of_week < 0 or day_of_week > 6:
        raise HTTPException(status_code=400, detail="Invalid day of week (0-6)")
    
    existing = db.query(BusinessHours).filter(BusinessHours.day_of_week == day_of_week).first()
    
    if existing:
        existing.open_time = hours.open_time
        existing.close_time = hours.close_time
        existing.is_closed = hours.is_closed
    else:
        new_hours = BusinessHours(
            day_of_week=day_of_week,
            open_time=hours.open_time,
            close_time=hours.close_time,
            is_closed=hours.is_closed
        )
        db.add(new_hours)
    
    db.commit()
    return {"message": f"Hours set for {DAY_NAMES[day_of_week]}"}


@router.post("/hours/bulk")
def set_all_hours(hours_list: List[HoursUpdate], db: Session = Depends(get_db)):
    """Set hours for all days at once"""
    if len(hours_list) != 7:
        raise HTTPException(status_code=400, detail="Must provide hours for all 7 days")
    
    # Clear existing
    db.query(BusinessHours).delete()
    
    for day, hours in enumerate(hours_list):
        new_hours = BusinessHours(
            day_of_week=day,
            open_time=hours.open_time,
            close_time=hours.close_time,
            is_closed=hours.is_closed
        )
        db.add(new_hours)
    
    db.commit()
    return {"message": "All hours updated"}


@router.get("/status")
def get_current_status(db: Session = Depends(get_db)):
    """Get current open/closed status"""
    now = datetime.now()
    today = now.weekday()
    current_time = now.strftime("%H:%M")
    
    # Check for holiday
    holiday = db.query(Holiday).filter(
        Holiday.date == now.date()
    ).first()
    
    if holiday:
        if holiday.is_closed:
            return {
                "is_open": False,
                "reason": f"Closed for {holiday.name}",
                "next_open": get_next_open(db)
            }
        elif holiday.modified_hours:
            open_time, close_time = holiday.modified_hours.split("-")
            is_open = open_time <= current_time < close_time
            return {
                "is_open": is_open,
                "reason": f"Holiday hours for {holiday.name}",
                "hours_today": holiday.modified_hours,
                "closes_at": close_time if is_open else None
            }
    
    # Check regular hours
    hours = db.query(BusinessHours).filter(BusinessHours.day_of_week == today).first()
    
    if not hours or hours.is_closed:
        return {
            "is_open": False,
            "reason": "Closed today",
            "next_open": get_next_open(db)
        }
    
    is_open = hours.open_time <= current_time < hours.close_time
    
    return {
        "is_open": is_open,
        "current_time": current_time,
        "today_hours": f"{hours.open_time} - {hours.close_time}",
        "opens_at": hours.open_time if not is_open and current_time < hours.open_time else None,
        "closes_at": hours.close_time if is_open else None,
        "next_open": get_next_open(db) if not is_open else None
    }


def get_next_open(db: Session) -> dict:
    """Find when shop next opens"""
    now = datetime.now()
    
    for i in range(1, 8):
        check_date = now + timedelta(days=i)
        day_of_week = check_date.weekday()
        
        # Check for holiday
        holiday = db.query(Holiday).filter(
            Holiday.date == check_date.date()
        ).first()
        
        if holiday and holiday.is_closed:
            continue
        
        hours = db.query(BusinessHours).filter(BusinessHours.day_of_week == day_of_week).first()
        
        if hours and not hours.is_closed:
            return {
                "date": check_date.date().isoformat(),
                "day": DAY_NAMES[day_of_week],
                "opens_at": hours.open_time
            }
    
    return None


# ===== HOLIDAYS =====

@router.get("/holidays")
def get_holidays(upcoming_only: bool = True, db: Session = Depends(get_db)):
    """Get holidays"""
    query = db.query(Holiday)
    
    if upcoming_only:
        query = query.filter(Holiday.date >= date.today())
    
    holidays = query.order_by(Holiday.date).all()
    
    return [
        {
            "id": h.id,
            "date": h.date.date().isoformat() if isinstance(h.date, datetime) else h.date.isoformat(),
            "name": h.name,
            "is_closed": h.is_closed,
            "modified_hours": h.modified_hours
        }
        for h in holidays
    ]


@router.post("/holidays")
def add_holiday(holiday: HolidayCreate, db: Session = Depends(get_db)):
    """Add a holiday"""
    holiday_date = datetime.strptime(holiday.date, "%Y-%m-%d")
    
    # Check for existing
    existing = db.query(Holiday).filter(Holiday.date == holiday_date.date()).first()
    if existing:
        raise HTTPException(status_code=400, detail="Holiday already exists for this date")
    
    db_holiday = Holiday(
        date=holiday_date,
        name=holiday.name,
        is_closed=holiday.is_closed,
        modified_hours=holiday.modified_hours
    )
    db.add(db_holiday)
    db.commit()
    db.refresh(db_holiday)
    
    return {"message": "Holiday added", "id": db_holiday.id}


@router.delete("/holidays/{holiday_id}")
def delete_holiday(holiday_id: int, db: Session = Depends(get_db)):
    """Delete a holiday"""
    holiday = db.query(Holiday).filter(Holiday.id == holiday_id).first()
    if not holiday:
        raise HTTPException(status_code=404, detail="Holiday not found")
    
    db.delete(holiday)
    db.commit()
    return {"message": "Holiday deleted"}


@router.post("/holidays/add-common")
def add_common_holidays(year: int, db: Session = Depends(get_db)):
    """Add common US holidays for a year"""
    common_holidays = [
        (f"{year}-01-01", "New Year's Day"),
        (f"{year}-07-04", "Independence Day"),
        (f"{year}-11-28", "Thanksgiving"),  # Approximate
        (f"{year}-12-25", "Christmas Day"),
    ]
    
    added = 0
    for date_str, name in common_holidays:
        holiday_date = datetime.strptime(date_str, "%Y-%m-%d")
        
        existing = db.query(Holiday).filter(Holiday.date == holiday_date.date()).first()
        if not existing:
            db_holiday = Holiday(date=holiday_date, name=name, is_closed=True)
            db.add(db_holiday)
            added += 1
    
    db.commit()
    return {"message": f"Added {added} holidays for {year}"}
