from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List, Optional
from pydantic import BaseModel
from datetime import datetime, date, timedelta

from app.database import get_db
from app.models import Appointment, Customer, Barber, ServiceType

router = APIRouter(prefix="/appointments", tags=["appointments"])


class AppointmentCreate(BaseModel):
    customer_name: str
    customer_phone: str
    customer_id: Optional[int] = None
    barber_id: Optional[int] = None
    service_type_id: int
    scheduled_time: datetime
    duration_minutes: int = 30
    notes: Optional[str] = None


class AppointmentResponse(BaseModel):
    id: int
    customer_name: str
    customer_phone: str
    customer_id: Optional[int]
    barber_id: Optional[int]
    barber_name: Optional[str] = None
    service_type_id: int
    service_name: Optional[str] = None
    scheduled_time: datetime
    duration_minutes: int
    status: str
    notes: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


@router.get("/")
def list_appointments(
    date: Optional[str] = None,
    barber_id: Optional[int] = None,
    status: Optional[str] = None,
    db: Session = Depends(get_db)
):
    query = db.query(Appointment)
    
    if date:
        target_date = datetime.strptime(date, "%Y-%m-%d").date()
        query = query.filter(func.date(Appointment.scheduled_time) == target_date)
    
    if barber_id:
        query = query.filter(Appointment.barber_id == barber_id)
    
    if status:
        query = query.filter(Appointment.status == status)
    
    appointments = query.order_by(Appointment.scheduled_time).all()
    
    result = []
    for appt in appointments:
        barber_name = None
        if appt.barber_id:
            barber = db.query(Barber).filter(Barber.id == appt.barber_id).first()
            if barber:
                barber_name = barber.name
        
        service = db.query(ServiceType).filter(ServiceType.id == appt.service_type_id).first()
        service_name = service.name if service else "Unknown"
        
        result.append({
            "id": appt.id,
            "customer_name": appt.customer_name,
            "customer_phone": appt.customer_phone,
            "customer_id": appt.customer_id,
            "barber_id": appt.barber_id,
            "barber_name": barber_name,
            "service_type_id": appt.service_type_id,
            "service_name": service_name,
            "scheduled_time": appt.scheduled_time,
            "duration_minutes": appt.duration_minutes,
            "status": appt.status,
            "notes": appt.notes,
            "created_at": appt.created_at
        })
    
    return result


@router.get("/available-slots")
def get_available_slots(
    date: str,
    service_type_id: int,
    barber_id: Optional[int] = None,
    db: Session = Depends(get_db)
):
    """Get available time slots for a given date and service"""
    target_date = datetime.strptime(date, "%Y-%m-%d").date()
    
    service = db.query(ServiceType).filter(ServiceType.id == service_type_id).first()
    if not service:
        raise HTTPException(status_code=404, detail="Service not found")
    
    duration = service.duration_minutes
    
    # Business hours: 9 AM to 7 PM
    start_hour = 9
    end_hour = 19
    
    # Get existing appointments for the date
    query = db.query(Appointment).filter(
        func.date(Appointment.scheduled_time) == target_date,
        Appointment.status.in_(["scheduled", "confirmed", "in_progress"])
    )
    if barber_id:
        query = query.filter(Appointment.barber_id == barber_id)
    
    existing = query.all()
    
    # Generate 30-minute slots
    slots = []
    current_time = datetime.combine(target_date, datetime.min.time().replace(hour=start_hour))
    end_time = datetime.combine(target_date, datetime.min.time().replace(hour=end_hour))
    
    while current_time + timedelta(minutes=duration) <= end_time:
        slot_end = current_time + timedelta(minutes=duration)
        
        # Check if slot conflicts with existing appointments
        available = True
        for appt in existing:
            appt_end = appt.scheduled_time + timedelta(minutes=appt.duration_minutes)
            if (current_time < appt_end and slot_end > appt.scheduled_time):
                available = False
                break
        
        if available:
            slots.append({
                "time": current_time.strftime("%H:%M"),
                "datetime": current_time.isoformat(),
                "available": True
            })
        
        current_time += timedelta(minutes=30)
    
    return slots


@router.post("/")
def create_appointment(appt: AppointmentCreate, db: Session = Depends(get_db)):
    # Validate service
    service = db.query(ServiceType).filter(ServiceType.id == appt.service_type_id).first()
    if not service:
        raise HTTPException(status_code=404, detail="Service not found")
    
    # Check for conflicts
    existing = db.query(Appointment).filter(
        Appointment.barber_id == appt.barber_id,
        Appointment.scheduled_time == appt.scheduled_time,
        Appointment.status.in_(["scheduled", "confirmed"])
    ).first()
    
    if existing:
        raise HTTPException(status_code=400, detail="Time slot not available")
    
    appointment = Appointment(
        customer_name=appt.customer_name,
        customer_phone=appt.customer_phone,
        customer_id=appt.customer_id,
        barber_id=appt.barber_id,
        service_type_id=appt.service_type_id,
        scheduled_time=appt.scheduled_time,
        duration_minutes=appt.duration_minutes or service.duration_minutes,
        notes=appt.notes
    )
    db.add(appointment)
    db.commit()
    db.refresh(appointment)
    
    return {
        "id": appointment.id,
        "scheduled_time": appointment.scheduled_time,
        "status": appointment.status,
        "message": "Appointment booked"
    }


@router.patch("/{appointment_id}/status")
def update_appointment_status(
    appointment_id: int,
    status: str,
    db: Session = Depends(get_db)
):
    appointment = db.query(Appointment).filter(Appointment.id == appointment_id).first()
    if not appointment:
        raise HTTPException(status_code=404, detail="Appointment not found")
    
    valid_statuses = ["scheduled", "confirmed", "in_progress", "completed", "cancelled", "no_show"]
    if status not in valid_statuses:
        raise HTTPException(status_code=400, detail=f"Invalid status. Must be one of: {valid_statuses}")
    
    appointment.status = status
    db.commit()
    
    return {"message": "Status updated", "status": appointment.status}


@router.delete("/{appointment_id}")
def cancel_appointment(appointment_id: int, db: Session = Depends(get_db)):
    appointment = db.query(Appointment).filter(Appointment.id == appointment_id).first()
    if not appointment:
        raise HTTPException(status_code=404, detail="Appointment not found")
    
    appointment.status = "cancelled"
    db.commit()
    
    return {"message": "Appointment cancelled"}


@router.get("/today")
def get_todays_appointments(db: Session = Depends(get_db)):
    """Get all appointments for today"""
    today = date.today()
    return list_appointments(date=today.isoformat(), db=db)
