from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional
from pydantic import BaseModel
from datetime import datetime

from app.database import get_db
from app.models import ServiceType

router = APIRouter(prefix="/services", tags=["services"])


# Peak hours configuration
PEAK_HOURS = {
    "weekday_peak": [(17, 20)],  # 5pm-8pm weekdays
    "weekend_peak": [(10, 18)],  # 10am-6pm weekends
    "off_peak": [(9, 12)],  # 9am-12pm weekdays
}


def get_current_pricing_tier() -> str:
    """Determine current pricing tier based on time"""
    now = datetime.now()
    hour = now.hour
    weekday = now.weekday()  # 0=Monday, 6=Sunday
    
    is_weekend = weekday >= 5
    
    if is_weekend:
        for start, end in PEAK_HOURS["weekend_peak"]:
            if start <= hour < end:
                return "peak"
    else:
        for start, end in PEAK_HOURS["weekday_peak"]:
            if start <= hour < end:
                return "peak"
        for start, end in PEAK_HOURS["off_peak"]:
            if start <= hour < end:
                return "off_peak"
    
    return "standard"


class ServiceCreate(BaseModel):
    name: str
    category: str
    base_price: float
    peak_price: Optional[float] = None
    off_peak_price: Optional[float] = None
    duration_minutes: int = 30
    description: Optional[str] = None


class ServiceUpdate(BaseModel):
    name: Optional[str] = None
    category: Optional[str] = None
    base_price: Optional[float] = None
    peak_price: Optional[float] = None
    off_peak_price: Optional[float] = None
    duration_minutes: Optional[int] = None
    description: Optional[str] = None
    is_active: Optional[bool] = None


class ServiceResponse(BaseModel):
    id: int
    name: str
    category: str
    base_price: float
    duration_minutes: int
    description: Optional[str]
    is_active: bool

    class Config:
        from_attributes = True


@router.get("/")
def list_services(
    category: Optional[str] = None,
    active_only: bool = True,
    include_pricing_tier: bool = True,
    db: Session = Depends(get_db)
):
    query = db.query(ServiceType)
    if active_only:
        query = query.filter(ServiceType.is_active == True)
    if category:
        query = query.filter(ServiceType.category == category)
    
    services = query.all()
    pricing_tier = get_current_pricing_tier() if include_pricing_tier else "standard"
    
    result = []
    for s in services:
        # Determine current price based on tier
        if pricing_tier == "peak" and s.peak_price:
            current_price = s.peak_price
        elif pricing_tier == "off_peak" and s.off_peak_price:
            current_price = s.off_peak_price
        else:
            current_price = s.base_price
        
        result.append({
            "id": s.id,
            "name": s.name,
            "category": s.category,
            "base_price": s.base_price,
            "peak_price": s.peak_price,
            "off_peak_price": s.off_peak_price,
            "current_price": current_price,
            "pricing_tier": pricing_tier,
            "duration_minutes": s.duration_minutes,
            "description": s.description,
            "is_active": s.is_active
        })
    
    return result


@router.get("/categories")
def list_categories(db: Session = Depends(get_db)):
    categories = db.query(ServiceType.category).distinct().all()
    return [c[0] for c in categories]


@router.get("/{service_id}", response_model=ServiceResponse)
def get_service(service_id: int, db: Session = Depends(get_db)):
    service = db.query(ServiceType).filter(ServiceType.id == service_id).first()
    if not service:
        raise HTTPException(status_code=404, detail="Service not found")
    return service


@router.post("/", response_model=ServiceResponse)
def create_service(service: ServiceCreate, db: Session = Depends(get_db)):
    db_service = ServiceType(**service.model_dump())
    db.add(db_service)
    db.commit()
    db.refresh(db_service)
    return db_service


@router.patch("/{service_id}", response_model=ServiceResponse)
def update_service(service_id: int, service: ServiceUpdate, db: Session = Depends(get_db)):
    db_service = db.query(ServiceType).filter(ServiceType.id == service_id).first()
    if not db_service:
        raise HTTPException(status_code=404, detail="Service not found")
    
    update_data = service.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(db_service, field, value)
    
    db.commit()
    db.refresh(db_service)
    return db_service


# ===== PRICING TIER ENDPOINTS =====

@router.get("/pricing/current")
def get_current_pricing():
    """Get current pricing tier information"""
    tier = get_current_pricing_tier()
    now = datetime.now()
    
    tier_info = {
        "standard": {
            "name": "Standard",
            "description": "Regular pricing",
            "multiplier": 1.0
        },
        "peak": {
            "name": "Peak Hours",
            "description": "Weekend or evening premium pricing",
            "multiplier": 1.1  # 10% premium
        },
        "off_peak": {
            "name": "Off-Peak",
            "description": "Early weekday discount pricing",
            "multiplier": 0.9  # 10% discount
        }
    }
    
    return {
        "current_tier": tier,
        "tier_info": tier_info[tier],
        "current_time": now.strftime("%H:%M"),
        "day_of_week": now.strftime("%A"),
        "is_weekend": now.weekday() >= 5,
        "peak_hours": PEAK_HOURS
    }


@router.post("/{service_id}/set-peak-pricing")
def set_peak_pricing(service_id: int, peak_price: float, off_peak_price: Optional[float] = None, db: Session = Depends(get_db)):
    """Set peak and off-peak pricing for a service"""
    service = db.query(ServiceType).filter(ServiceType.id == service_id).first()
    if not service:
        raise HTTPException(status_code=404, detail="Service not found")
    
    service.peak_price = peak_price
    if off_peak_price is not None:
        service.off_peak_price = off_peak_price
    
    db.commit()
    
    return {
        "message": "Pricing updated",
        "service_name": service.name,
        "base_price": service.base_price,
        "peak_price": service.peak_price,
        "off_peak_price": service.off_peak_price
    }


@router.post("/pricing/bulk-update")
def bulk_update_pricing(peak_multiplier: float = 1.1, off_peak_multiplier: float = 0.9, db: Session = Depends(get_db)):
    """Set peak/off-peak pricing for all services based on multipliers"""
    services = db.query(ServiceType).filter(ServiceType.is_active == True).all()
    
    updated = 0
    for s in services:
        s.peak_price = round(s.base_price * peak_multiplier, 2)
        s.off_peak_price = round(s.base_price * off_peak_multiplier, 2)
        updated += 1
    
    db.commit()
    
    return {
        "message": f"Updated pricing for {updated} services",
        "peak_multiplier": peak_multiplier,
        "off_peak_multiplier": off_peak_multiplier
    }


@router.get("/{service_id}/price")
def get_service_current_price(service_id: int, db: Session = Depends(get_db)):
    """Get the current price for a service based on time"""
    service = db.query(ServiceType).filter(ServiceType.id == service_id).first()
    if not service:
        raise HTTPException(status_code=404, detail="Service not found")
    
    tier = get_current_pricing_tier()
    
    if tier == "peak" and service.peak_price:
        price = service.peak_price
        savings = None
    elif tier == "off_peak" and service.off_peak_price:
        price = service.off_peak_price
        savings = service.base_price - service.off_peak_price
    else:
        price = service.base_price
        savings = None
    
    return {
        "service_id": service.id,
        "service_name": service.name,
        "current_price": price,
        "base_price": service.base_price,
        "pricing_tier": tier,
        "savings": savings
    }
