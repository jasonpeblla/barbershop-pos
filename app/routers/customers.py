from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import or_
from typing import List, Optional
from pydantic import BaseModel
from datetime import datetime, timedelta

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
    birthday: Optional[str] = None  # "MM-DD" or "YYYY-MM-DD"


class CustomerUpdate(BaseModel):
    name: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    preferred_barber_id: Optional[int] = None
    preferred_cut: Optional[str] = None
    notes: Optional[str] = None
    birthday: Optional[str] = None


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


@router.patch("/{customer_id}/birthday")
def set_customer_birthday(customer_id: int, birthday: str, db: Session = Depends(get_db)):
    """Set customer birthday (format: MM-DD or YYYY-MM-DD)"""
    customer = db.query(Customer).filter(Customer.id == customer_id).first()
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    
    # Parse birthday - accept MM-DD or YYYY-MM-DD
    try:
        if len(birthday) == 5:  # MM-DD
            month, day = birthday.split("-")
            bday = datetime(2000, int(month), int(day))  # Use 2000 as placeholder year
        else:  # YYYY-MM-DD
            bday = datetime.strptime(birthday, "%Y-%m-%d")
    except:
        raise HTTPException(status_code=400, detail="Invalid birthday format. Use MM-DD or YYYY-MM-DD")
    
    customer.birthday = bday
    db.commit()
    
    return {"message": "Birthday set", "birthday": bday.strftime("%m-%d")}


@router.get("/birthdays/today")
def get_todays_birthdays(db: Session = Depends(get_db)):
    """Get customers with birthdays today"""
    today = datetime.now()
    
    # Find customers whose birthday month/day match today
    customers = db.query(Customer).filter(
        Customer.birthday.isnot(None)
    ).all()
    
    birthday_customers = []
    for c in customers:
        if c.birthday and c.birthday.month == today.month and c.birthday.day == today.day:
            # Check if they've used discount this year
            discount_available = c.birthday_discount_used_year != today.year
            birthday_customers.append({
                "id": c.id,
                "name": c.name,
                "phone": c.phone,
                "discount_available": discount_available,
                "discount_amount": 20  # 20% birthday discount
            })
    
    return birthday_customers


@router.get("/birthdays/upcoming")
def get_upcoming_birthdays(days: int = 7, db: Session = Depends(get_db)):
    """Get customers with birthdays in the next N days"""
    from datetime import timedelta
    
    today = datetime.now()
    customers = db.query(Customer).filter(
        Customer.birthday.isnot(None)
    ).all()
    
    upcoming = []
    for c in customers:
        if c.birthday:
            # Create this year's birthday date
            this_year_bday = c.birthday.replace(year=today.year)
            if this_year_bday < today:
                this_year_bday = this_year_bday.replace(year=today.year + 1)
            
            days_until = (this_year_bday - today).days
            if 0 <= days_until <= days:
                upcoming.append({
                    "id": c.id,
                    "name": c.name,
                    "phone": c.phone,
                    "birthday": c.birthday.strftime("%m-%d"),
                    "days_until": days_until,
                    "date": this_year_bday.strftime("%Y-%m-%d")
                })
    
    return sorted(upcoming, key=lambda x: x["days_until"])


@router.post("/{customer_id}/birthday-discount")
def use_birthday_discount(customer_id: int, db: Session = Depends(get_db)):
    """Mark birthday discount as used for this year"""
    customer = db.query(Customer).filter(Customer.id == customer_id).first()
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    
    if not customer.birthday:
        raise HTTPException(status_code=400, detail="Customer has no birthday set")
    
    today = datetime.now()
    
    # Check if it's their birthday month (give a week window)
    bday_this_year = customer.birthday.replace(year=today.year)
    days_diff = abs((today - bday_this_year).days)
    
    if days_diff > 7:
        raise HTTPException(status_code=400, detail="Birthday discount only valid within 7 days of birthday")
    
    if customer.birthday_discount_used_year == today.year:
        raise HTTPException(status_code=400, detail="Birthday discount already used this year")
    
    customer.birthday_discount_used_year = today.year
    db.commit()
    
    return {
        "message": "Birthday discount applied",
        "discount_percent": 20,
        "valid_until": (bday_this_year + timedelta(days=7)).strftime("%Y-%m-%d") if days_diff <= 7 else None
    }


@router.get("/{customer_id}/birthday-status")
def get_birthday_status(customer_id: int, db: Session = Depends(get_db)):
    """Check if customer has birthday discount available"""
    from datetime import timedelta
    
    customer = db.query(Customer).filter(Customer.id == customer_id).first()
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    
    if not customer.birthday:
        return {"has_birthday": False, "discount_available": False}
    
    today = datetime.now()
    bday_this_year = customer.birthday.replace(year=today.year)
    
    # Check if within 7 days of birthday
    days_diff = (today - bday_this_year).days
    is_birthday_window = -7 <= days_diff <= 7
    
    discount_available = is_birthday_window and customer.birthday_discount_used_year != today.year
    
    return {
        "has_birthday": True,
        "birthday": customer.birthday.strftime("%m-%d"),
        "is_birthday_window": is_birthday_window,
        "discount_available": discount_available,
        "discount_percent": 20 if discount_available else 0,
        "already_used_this_year": customer.birthday_discount_used_year == today.year
    }
