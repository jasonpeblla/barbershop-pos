from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import Optional
from pydantic import BaseModel
from datetime import datetime

from app.database import get_db
from app.models import WalkInQueue, Customer, Barber, ServiceType

router = APIRouter(prefix="/queue", tags=["queue"])


class QueueEntryCreate(BaseModel):
    customer_name: str
    customer_phone: Optional[str] = None
    customer_id: Optional[int] = None
    requested_barber_id: Optional[int] = None
    service_notes: Optional[str] = None


class QueueEntryResponse(BaseModel):
    id: int
    customer_name: str
    customer_phone: Optional[str]
    customer_id: Optional[int]
    requested_barber_id: Optional[int]
    requested_barber_name: Optional[str] = None
    service_notes: Optional[str]
    position: int
    status: str
    estimated_wait: Optional[int]
    check_in_time: datetime
    called_time: Optional[datetime]

    class Config:
        from_attributes = True


@router.get("/")
def get_queue(db: Session = Depends(get_db)):
    """Get all waiting/called entries in the queue"""
    entries = db.query(WalkInQueue).filter(
        WalkInQueue.status.in_(["waiting", "called"])
    ).order_by(WalkInQueue.position).all()
    
    result = []
    for entry in entries:
        barber_name = None
        if entry.requested_barber_id:
            barber = db.query(Barber).filter(Barber.id == entry.requested_barber_id).first()
            if barber:
                barber_name = barber.name
        
        result.append({
            "id": entry.id,
            "customer_name": entry.customer_name,
            "customer_phone": entry.customer_phone,
            "customer_id": entry.customer_id,
            "requested_barber_id": entry.requested_barber_id,
            "requested_barber_name": barber_name,
            "service_notes": entry.service_notes,
            "position": entry.position,
            "status": entry.status,
            "estimated_wait": entry.estimated_wait,
            "check_in_time": entry.check_in_time,
            "called_time": entry.called_time,
            "wait_time_minutes": int((datetime.utcnow() - entry.check_in_time).total_seconds() / 60)
        })
    
    return result


@router.post("/")
def add_to_queue(entry: QueueEntryCreate, db: Session = Depends(get_db)):
    """Add a customer to the walk-in queue"""
    # Get next position
    max_pos = db.query(func.max(WalkInQueue.position)).filter(
        WalkInQueue.status.in_(["waiting", "called"])
    ).scalar() or 0
    
    # Calculate estimated wait (avg 25 min per person ahead)
    waiting_count = db.query(WalkInQueue).filter(
        WalkInQueue.status == "waiting"
    ).count()
    estimated_wait = waiting_count * 25
    
    # Create entry
    queue_entry = WalkInQueue(
        customer_name=entry.customer_name,
        customer_phone=entry.customer_phone,
        customer_id=entry.customer_id,
        requested_barber_id=entry.requested_barber_id,
        service_notes=entry.service_notes,
        position=max_pos + 1,
        estimated_wait=estimated_wait
    )
    db.add(queue_entry)
    db.commit()
    db.refresh(queue_entry)
    
    return {
        "id": queue_entry.id,
        "position": queue_entry.position,
        "estimated_wait": estimated_wait,
        "message": f"Added to queue at position {queue_entry.position}"
    }


@router.post("/{entry_id}/call")
def call_customer(entry_id: int, db: Session = Depends(get_db)):
    """Mark a customer as called (their turn)"""
    entry = db.query(WalkInQueue).filter(WalkInQueue.id == entry_id).first()
    if not entry:
        raise HTTPException(status_code=404, detail="Queue entry not found")
    
    entry.status = "called"
    entry.called_time = datetime.utcnow()
    db.commit()
    
    return {"message": "Customer called", "status": entry.status}


@router.post("/{entry_id}/start")
def start_service(entry_id: int, barber_id: int, db: Session = Depends(get_db)):
    """Start service for a queued customer"""
    entry = db.query(WalkInQueue).filter(WalkInQueue.id == entry_id).first()
    if not entry:
        raise HTTPException(status_code=404, detail="Queue entry not found")
    
    barber = db.query(Barber).filter(Barber.id == barber_id).first()
    if not barber:
        raise HTTPException(status_code=404, detail="Barber not found")
    
    entry.status = "in_service"
    db.commit()
    
    return {
        "message": "Service started",
        "customer_name": entry.customer_name,
        "barber_name": barber.name
    }


@router.post("/{entry_id}/complete")
def complete_queue_entry(entry_id: int, db: Session = Depends(get_db)):
    """Mark a queue entry as completed"""
    entry = db.query(WalkInQueue).filter(WalkInQueue.id == entry_id).first()
    if not entry:
        raise HTTPException(status_code=404, detail="Queue entry not found")
    
    entry.status = "completed"
    entry.completed_time = datetime.utcnow()
    db.commit()
    
    return {"message": "Service completed"}


@router.post("/{entry_id}/remove")
def remove_from_queue(entry_id: int, db: Session = Depends(get_db)):
    """Remove a customer from the queue (left without service)"""
    entry = db.query(WalkInQueue).filter(WalkInQueue.id == entry_id).first()
    if not entry:
        raise HTTPException(status_code=404, detail="Queue entry not found")
    
    entry.status = "left"
    db.commit()
    
    # Reorder remaining queue positions
    remaining = db.query(WalkInQueue).filter(
        WalkInQueue.status == "waiting",
        WalkInQueue.position > entry.position
    ).all()
    
    for e in remaining:
        e.position -= 1
    db.commit()
    
    return {"message": "Removed from queue"}


@router.get("/stats")
def get_queue_stats(db: Session = Depends(get_db)):
    """Get current queue statistics"""
    waiting = db.query(WalkInQueue).filter(WalkInQueue.status == "waiting").count()
    called = db.query(WalkInQueue).filter(WalkInQueue.status == "called").count()
    in_service = db.query(WalkInQueue).filter(WalkInQueue.status == "in_service").count()
    
    # Average wait time for today's completed
    today_completed = db.query(WalkInQueue).filter(
        WalkInQueue.status == "completed",
        func.date(WalkInQueue.check_in_time) == func.date(datetime.utcnow())
    ).all()
    
    avg_wait = 0
    if today_completed:
        waits = [(e.called_time - e.check_in_time).total_seconds() / 60 
                 for e in today_completed if e.called_time]
        avg_wait = sum(waits) / len(waits) if waits else 0
    
    # Get active barbers count for better estimation
    active_barbers = db.query(Barber).filter(Barber.is_available == True).count()
    estimated_wait = (waiting * 25) // max(active_barbers, 1)
    
    return {
        "waiting": waiting,
        "called": called,
        "in_service": in_service,
        "active_barbers": active_barbers,
        "average_wait_minutes": round(avg_wait, 1),
        "estimated_wait_new": estimated_wait
    }


@router.get("/wait-times")
def get_detailed_wait_times(db: Session = Depends(get_db)):
    """Get detailed wait time analysis with historical data"""
    from datetime import timedelta
    from app.models import Order, TimeClock
    
    now = datetime.utcnow()
    today = now.date()
    
    # Current queue status
    waiting = db.query(WalkInQueue).filter(WalkInQueue.status == "waiting").count()
    in_service = db.query(WalkInQueue).filter(WalkInQueue.status == "in_service").count()
    
    # Active barbers (clocked in today)
    active_barbers = db.query(Barber).filter(Barber.is_available == True).count()
    
    # Historical average service time (last 7 days)
    week_ago = now - timedelta(days=7)
    completed_orders = db.query(Order).filter(
        Order.status == "completed",
        Order.completed_at >= week_ago,
        Order.started_at.isnot(None)
    ).all()
    
    avg_service_time = 25  # default
    if completed_orders:
        service_times = [
            (o.completed_at - o.started_at).total_seconds() / 60
            for o in completed_orders
            if o.started_at and o.completed_at
        ]
        if service_times:
            avg_service_time = sum(service_times) / len(service_times)
    
    # Calculate smart wait estimate
    if active_barbers > 0:
        # Time until current services complete (estimate half done)
        current_wait = (in_service * avg_service_time * 0.5) / active_barbers
        # Time for queue
        queue_wait = (waiting * avg_service_time) / active_barbers
        total_estimate = current_wait + queue_wait
    else:
        total_estimate = waiting * avg_service_time
    
    # Busiest hours analysis (for today)
    hour_distribution = {}
    today_entries = db.query(WalkInQueue).filter(
        func.date(WalkInQueue.check_in_time) == today
    ).all()
    
    for entry in today_entries:
        hour = entry.check_in_time.hour
        hour_distribution[hour] = hour_distribution.get(hour, 0) + 1
    
    busiest_hour = max(hour_distribution.items(), key=lambda x: x[1])[0] if hour_distribution else None
    
    return {
        "current_queue": {
            "waiting": waiting,
            "in_service": in_service,
            "active_barbers": active_barbers
        },
        "estimates": {
            "new_walkin_wait_minutes": round(total_estimate),
            "average_service_time": round(avg_service_time),
            "historical_data_days": 7
        },
        "today_stats": {
            "total_customers": len(today_entries),
            "busiest_hour": f"{busiest_hour}:00" if busiest_hour else None,
            "hourly_distribution": {f"{h}:00": c for h, c in sorted(hour_distribution.items())}
        },
        "recommendation": get_wait_recommendation(total_estimate)
    }


def get_wait_recommendation(wait_minutes: float) -> dict:
    """Get a recommendation based on wait time"""
    if wait_minutes <= 10:
        return {"level": "low", "message": "Almost no wait - great time to come in!", "color": "green"}
    elif wait_minutes <= 25:
        return {"level": "moderate", "message": "Short wait expected", "color": "yellow"}
    elif wait_minutes <= 45:
        return {"level": "busy", "message": "Moderate wait - consider booking appointment", "color": "orange"}
    else:
        return {"level": "very_busy", "message": "Long wait - we recommend booking an appointment", "color": "red"}


@router.get("/barber/{barber_id}/queue")
def get_barber_specific_queue(barber_id: int, db: Session = Depends(get_db)):
    """Get queue specifically waiting for a particular barber"""
    entries = db.query(WalkInQueue).filter(
        WalkInQueue.requested_barber_id == barber_id,
        WalkInQueue.status.in_(["waiting", "called"])
    ).order_by(WalkInQueue.position).all()
    
    barber = db.query(Barber).filter(Barber.id == barber_id).first()
    if not barber:
        raise HTTPException(status_code=404, detail="Barber not found")
    
    return {
        "barber_id": barber_id,
        "barber_name": barber.name,
        "is_available": barber.is_available,
        "queue_count": len(entries),
        "estimated_wait": len(entries) * 25,
        "customers": [
            {
                "id": e.id,
                "customer_name": e.customer_name,
                "position": e.position,
                "service_notes": e.service_notes,
                "wait_time": int((datetime.utcnow() - e.check_in_time).total_seconds() / 60)
            }
            for e in entries
        ]
    }


@router.get("/{entry_id}/status")
def get_queue_position(entry_id: int, db: Session = Depends(get_db)):
    """Get current position and estimated wait for a queue entry (for customer self-check)"""
    entry = db.query(WalkInQueue).filter(WalkInQueue.id == entry_id).first()
    if not entry:
        raise HTTPException(status_code=404, detail="Queue entry not found")
    
    # Count people ahead
    ahead = db.query(WalkInQueue).filter(
        WalkInQueue.status == "waiting",
        WalkInQueue.position < entry.position
    ).count()
    
    active_barbers = db.query(Barber).filter(Barber.is_available == True).count()
    estimated_wait = (ahead * 25) // max(active_barbers, 1)
    
    return {
        "id": entry.id,
        "customer_name": entry.customer_name,
        "position": entry.position,
        "people_ahead": ahead,
        "status": entry.status,
        "estimated_wait_minutes": estimated_wait,
        "check_in_time": entry.check_in_time,
        "wait_time_so_far": int((datetime.utcnow() - entry.check_in_time).total_seconds() / 60)
    }


@router.post("/{entry_id}/notify-ready")
def notify_customer_ready(entry_id: int, db: Session = Depends(get_db)):
    """Prepare notification data for when customer is next (SMS-ready)"""
    entry = db.query(WalkInQueue).filter(WalkInQueue.id == entry_id).first()
    if not entry:
        raise HTTPException(status_code=404, detail="Queue entry not found")
    
    # This returns data that could be sent via SMS/text
    notification = {
        "to_phone": entry.customer_phone,
        "customer_name": entry.customer_name,
        "message": f"Hi {entry.customer_name}! You're next in line at the barbershop. Please come to the front.",
        "type": "ready",
        "entry_id": entry.id
    }
    
    # In production, this would integrate with Twilio/SMS service
    # For now, we log and return the notification data
    
    return {
        "notification": notification,
        "status": "prepared",
        "message": "Notification ready to send" if entry.customer_phone else "No phone number on file"
    }


@router.post("/{entry_id}/notify-soon")
def notify_customer_soon(entry_id: int, db: Session = Depends(get_db)):
    """Notify customer they're coming up soon (SMS-ready)"""
    entry = db.query(WalkInQueue).filter(WalkInQueue.id == entry_id).first()
    if not entry:
        raise HTTPException(status_code=404, detail="Queue entry not found")
    
    # Count people ahead
    ahead = db.query(WalkInQueue).filter(
        WalkInQueue.status == "waiting",
        WalkInQueue.position < entry.position
    ).count()
    
    notification = {
        "to_phone": entry.customer_phone,
        "customer_name": entry.customer_name,
        "message": f"Hi {entry.customer_name}! Just {ahead} {'person' if ahead == 1 else 'people'} ahead of you. Please head back to the shop!",
        "type": "soon",
        "people_ahead": ahead,
        "entry_id": entry.id
    }
    
    return {
        "notification": notification,
        "status": "prepared",
        "message": "Notification ready to send" if entry.customer_phone else "No phone number on file"
    }


@router.get("/lookup/{phone}")
def lookup_queue_by_phone(phone: str, db: Session = Depends(get_db)):
    """Look up queue position by phone number (for customer self-service)"""
    entry = db.query(WalkInQueue).filter(
        WalkInQueue.customer_phone.contains(phone),
        WalkInQueue.status.in_(["waiting", "called"])
    ).first()
    
    if not entry:
        return {"found": False, "message": "No active queue entry found for this phone number"}
    
    ahead = db.query(WalkInQueue).filter(
        WalkInQueue.status == "waiting",
        WalkInQueue.position < entry.position
    ).count()
    
    active_barbers = db.query(Barber).filter(Barber.is_available == True).count()
    estimated_wait = (ahead * 25) // max(active_barbers, 1)
    
    return {
        "found": True,
        "id": entry.id,
        "customer_name": entry.customer_name,
        "position": entry.position,
        "people_ahead": ahead,
        "status": entry.status,
        "estimated_wait_minutes": estimated_wait
    }
