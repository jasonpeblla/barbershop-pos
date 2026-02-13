from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import or_
from typing import List, Optional
from pydantic import BaseModel
from datetime import datetime

from app.database import get_db
from app.models import Customer, Order, OrderService, ServiceType

router = APIRouter(prefix="/customers", tags=["customers"])


class CustomerCreate(BaseModel):
    name: str
    phone: str
    email: Optional[str] = None
    preferred_barber_id: Optional[int] = None
    preferred_cut: Optional[str] = None
    notes: Optional[str] = None


class CustomerUpdate(BaseModel):
    name: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    preferred_barber_id: Optional[int] = None
    preferred_cut: Optional[str] = None
    notes: Optional[str] = None


class CustomerResponse(BaseModel):
    id: int
    name: str
    phone: str
    email: Optional[str]
    preferred_barber_id: Optional[int]
    preferred_cut: Optional[str]
    notes: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


@router.get("/", response_model=List[CustomerResponse])
def list_customers(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    return db.query(Customer).offset(skip).limit(limit).all()


@router.get("/search")
def search_customers(q: str, db: Session = Depends(get_db)):
    results = db.query(Customer).filter(
        or_(
            Customer.phone.contains(q),
            Customer.name.ilike(f"%{q}%")
        )
    ).limit(10).all()
    return results


@router.get("/{customer_id}", response_model=CustomerResponse)
def get_customer(customer_id: int, db: Session = Depends(get_db)):
    customer = db.query(Customer).filter(Customer.id == customer_id).first()
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    return customer


@router.post("/", response_model=CustomerResponse)
def create_customer(customer: CustomerCreate, db: Session = Depends(get_db)):
    # Check if phone already exists
    existing = db.query(Customer).filter(Customer.phone == customer.phone).first()
    if existing:
        raise HTTPException(status_code=400, detail="Phone number already registered")
    
    db_customer = Customer(**customer.model_dump())
    db.add(db_customer)
    db.commit()
    db.refresh(db_customer)
    return db_customer


@router.patch("/{customer_id}", response_model=CustomerResponse)
def update_customer(customer_id: int, customer: CustomerUpdate, db: Session = Depends(get_db)):
    db_customer = db.query(Customer).filter(Customer.id == customer_id).first()
    if not db_customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    
    update_data = customer.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(db_customer, field, value)
    
    db.commit()
    db.refresh(db_customer)
    return db_customer


@router.get("/{customer_id}/history")
def get_customer_history(customer_id: int, db: Session = Depends(get_db)):
    customer = db.query(Customer).filter(Customer.id == customer_id).first()
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    
    # Get order history
    orders = db.query(Order).filter(
        Order.customer_id == customer_id,
        Order.status == "completed"
    ).order_by(Order.completed_at.desc()).limit(20).all()
    
    # Calculate stats
    total_visits = len(orders)
    total_spent = sum(o.total for o in orders)
    avg_tip = sum(o.tip for o in orders) / total_visits if total_visits > 0 else 0
    
    # Find favorite services
    service_counts = {}
    for order in orders:
        for os in order.services:
            svc = db.query(ServiceType).filter(ServiceType.id == os.service_type_id).first()
            if svc:
                service_counts[svc.name] = service_counts.get(svc.name, 0) + os.quantity
    
    favorite_services = sorted(service_counts.items(), key=lambda x: x[1], reverse=True)[:3]
    
    # Recent visits details
    recent_visits = []
    for order in orders[:10]:
        services = []
        for os in order.services:
            svc = db.query(ServiceType).filter(ServiceType.id == os.service_type_id).first()
            if svc:
                services.append({
                    "name": svc.name,
                    "price": os.unit_price
                })
        recent_visits.append({
            "order_id": order.id,
            "date": order.completed_at.isoformat() if order.completed_at else order.created_at.isoformat(),
            "barber_id": order.barber_id,
            "services": services,
            "total": order.total,
            "tip": order.tip
        })
    
    return {
        "customer": {
            "id": customer.id,
            "name": customer.name,
            "phone": customer.phone,
            "email": customer.email,
            "preferred_cut": customer.preferred_cut,
            "notes": customer.notes,
            "member_since": customer.created_at.isoformat()
        },
        "stats": {
            "total_visits": total_visits,
            "total_spent": total_spent,
            "average_spend": total_spent / total_visits if total_visits > 0 else 0,
            "average_tip": avg_tip,
            "favorite_services": [{"name": s[0], "count": s[1]} for s in favorite_services]
        },
        "recent_visits": recent_visits
    }
