from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime, timedelta

from app.database import get_db
from app.models import RecurringAppointment, Appointment, Customer, Barber, ServiceType

router = APIRouter(prefix="/recurring", tags=["Recurring Appointments"])


class RecurringCreate(BaseModel):
    customer_id: int
    barber_id: Optional[int] = None
    service_type_id: int
    frequency: str  # weekly, biweekly, monthly
    day_of_week: Optional[int] = None  # 0=Monday, 6=Sunday
    time_of_day: str  # "10:00"
    start_date: str  # "2026-02-14"
    end_date: Optional[str] = None
    auto_generate_weeks: int = 8  # Generate this many weeks of appointments


class RecurringUpdate(BaseModel):
    barber_id: Optional[int] = None
    time_of_day: Optional[str] = None
    is_active: Optional[bool] = None
    end_date: Optional[str] = None


@router.get("/")
def list_recurring_appointments(active_only: bool = True, db: Session = Depends(get_db)):
    """Get all recurring appointment templates"""
    query = db.query(RecurringAppointment)
    
    if active_only:
        query = query.filter(RecurringAppointment.is_active == True)
    
    recurring = query.order_by(RecurringAppointment.day_of_week).all()
    
    day_names = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    
    return [
        {
            "id": r.id,
            "customer_id": r.customer_id,
            "customer_name": r.customer.name if r.customer else None,
            "barber_id": r.barber_id,
            "barber_name": r.barber.name if r.barber else "Any",
            "service_type_id": r.service_type_id,
            "service_name": r.service_type.name if r.service_type else None,
            "frequency": r.frequency,
            "day_of_week": r.day_of_week,
            "day_name": day_names[r.day_of_week] if r.day_of_week is not None else None,
            "time_of_day": r.time_of_day,
            "start_date": r.start_date.isoformat() if r.start_date else None,
            "end_date": r.end_date.isoformat() if r.end_date else None,
            "is_active": r.is_active
        }
        for r in recurring
    ]


@router.get("/customer/{customer_id}")
def get_customer_recurring(customer_id: int, db: Session = Depends(get_db)):
    """Get recurring appointments for a customer"""
    recurring = db.query(RecurringAppointment).filter(
        RecurringAppointment.customer_id == customer_id,
        RecurringAppointment.is_active == True
    ).all()
    
    return [
        {
            "id": r.id,
            "barber_name": r.barber.name if r.barber else "Any",
            "service_name": r.service_type.name if r.service_type else None,
            "frequency": r.frequency,
            "day_of_week": r.day_of_week,
            "time_of_day": r.time_of_day
        }
        for r in recurring
    ]


@router.post("/")
def create_recurring_appointment(data: RecurringCreate, db: Session = Depends(get_db)):
    """Create a recurring appointment and generate future appointments"""
    # Validate customer and service
    customer = db.query(Customer).filter(Customer.id == data.customer_id).first()
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    
    service = db.query(ServiceType).filter(ServiceType.id == data.service_type_id).first()
    if not service:
        raise HTTPException(status_code=404, detail="Service not found")
    
    start = datetime.strptime(data.start_date, "%Y-%m-%d")
    end = datetime.strptime(data.end_date, "%Y-%m-%d") if data.end_date else None
    
    # Create recurring template
    recurring = RecurringAppointment(
        customer_id=data.customer_id,
        barber_id=data.barber_id,
        service_type_id=data.service_type_id,
        frequency=data.frequency,
        day_of_week=data.day_of_week,
        time_of_day=data.time_of_day,
        start_date=start,
        end_date=end
    )
    db.add(recurring)
    db.commit()
    db.refresh(recurring)
    
    # Generate appointments
    appointments_created = generate_appointments(
        db, recurring, data.auto_generate_weeks, customer, service
    )
    
    return {
        "message": "Recurring appointment created",
        "recurring_id": recurring.id,
        "appointments_created": appointments_created
    }


def generate_appointments(
    db: Session,
    recurring: RecurringAppointment,
    weeks: int,
    customer: Customer,
    service: ServiceType
) -> int:
    """Generate individual appointments from recurring template"""
    created = 0
    current = recurring.start_date
    end_limit = current + timedelta(weeks=weeks)
    
    if recurring.end_date and recurring.end_date < end_limit:
        end_limit = recurring.end_date
    
    # Parse time
    hour, minute = map(int, recurring.time_of_day.split(":"))
    
    while current <= end_limit:
        # Check if this day matches the pattern
        should_create = False
        
        if recurring.frequency == "weekly":
            if recurring.day_of_week is not None and current.weekday() == recurring.day_of_week:
                should_create = True
        elif recurring.frequency == "biweekly":
            # Every 2 weeks on the specified day
            weeks_since_start = (current - recurring.start_date).days // 7
            if recurring.day_of_week is not None and current.weekday() == recurring.day_of_week:
                if weeks_since_start % 2 == 0:
                    should_create = True
        elif recurring.frequency == "monthly":
            # Same day of month as start date
            if current.day == recurring.start_date.day:
                should_create = True
        
        if should_create:
            scheduled_time = current.replace(hour=hour, minute=minute, second=0, microsecond=0)
            
            # Check if appointment already exists
            existing = db.query(Appointment).filter(
                Appointment.customer_id == customer.id,
                Appointment.scheduled_time == scheduled_time
            ).first()
            
            if not existing:
                appointment = Appointment(
                    customer_id=customer.id,
                    customer_name=customer.name,
                    customer_phone=customer.phone,
                    barber_id=recurring.barber_id,
                    service_type_id=recurring.service_type_id,
                    scheduled_time=scheduled_time,
                    duration_minutes=service.duration_minutes,
                    recurring_id=recurring.id,
                    status="scheduled"
                )
                db.add(appointment)
                created += 1
        
        current += timedelta(days=1)
    
    db.commit()
    return created


@router.post("/{recurring_id}/generate")
def generate_more_appointments(recurring_id: int, weeks: int = 4, db: Session = Depends(get_db)):
    """Generate more appointments from a recurring template"""
    recurring = db.query(RecurringAppointment).filter(
        RecurringAppointment.id == recurring_id
    ).first()
    
    if not recurring:
        raise HTTPException(status_code=404, detail="Recurring appointment not found")
    
    if not recurring.is_active:
        raise HTTPException(status_code=400, detail="Recurring appointment is not active")
    
    customer = db.query(Customer).filter(Customer.id == recurring.customer_id).first()
    service = db.query(ServiceType).filter(ServiceType.id == recurring.service_type_id).first()
    
    # Find the latest generated appointment
    latest = db.query(Appointment).filter(
        Appointment.recurring_id == recurring_id
    ).order_by(Appointment.scheduled_time.desc()).first()
    
    if latest:
        recurring.start_date = latest.scheduled_time + timedelta(days=1)
    
    created = generate_appointments(db, recurring, weeks, customer, service)
    
    return {
        "message": f"Generated {created} new appointments",
        "appointments_created": created
    }


@router.patch("/{recurring_id}")
def update_recurring(recurring_id: int, update: RecurringUpdate, db: Session = Depends(get_db)):
    """Update a recurring appointment"""
    recurring = db.query(RecurringAppointment).filter(
        RecurringAppointment.id == recurring_id
    ).first()
    
    if not recurring:
        raise HTTPException(status_code=404, detail="Recurring appointment not found")
    
    if update.barber_id is not None:
        recurring.barber_id = update.barber_id
    if update.time_of_day is not None:
        recurring.time_of_day = update.time_of_day
    if update.is_active is not None:
        recurring.is_active = update.is_active
    if update.end_date is not None:
        recurring.end_date = datetime.strptime(update.end_date, "%Y-%m-%d")
    
    db.commit()
    return {"message": "Recurring appointment updated"}


@router.delete("/{recurring_id}")
def cancel_recurring(recurring_id: int, cancel_future: bool = True, db: Session = Depends(get_db)):
    """Cancel a recurring appointment"""
    recurring = db.query(RecurringAppointment).filter(
        RecurringAppointment.id == recurring_id
    ).first()
    
    if not recurring:
        raise HTTPException(status_code=404, detail="Recurring appointment not found")
    
    recurring.is_active = False
    
    cancelled_count = 0
    if cancel_future:
        # Cancel all future appointments from this recurring
        now = datetime.now()
        future_appointments = db.query(Appointment).filter(
            Appointment.recurring_id == recurring_id,
            Appointment.scheduled_time > now,
            Appointment.status == "scheduled"
        ).all()
        
        for apt in future_appointments:
            apt.status = "cancelled"
            cancelled_count += 1
    
    db.commit()
    
    return {
        "message": "Recurring appointment cancelled",
        "future_appointments_cancelled": cancelled_count
    }
