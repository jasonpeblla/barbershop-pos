from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional
from pydantic import BaseModel
from datetime import datetime, date

from app.database import get_db
from app.models import Discount, DiscountUsage, Customer

router = APIRouter(prefix="/discounts", tags=["discounts"])


class DiscountCreate(BaseModel):
    code: str
    name: str
    description: Optional[str] = None
    discount_type: str  # "percent" or "fixed"
    discount_value: float  # percentage (0-100) or dollar amount
    min_purchase: float = 0.0
    max_discount: Optional[float] = None  # cap for percentage discounts
    max_uses: Optional[int] = None  # total uses allowed
    max_uses_per_customer: int = 1
    valid_from: Optional[datetime] = None
    valid_until: Optional[datetime] = None
    first_visit_only: bool = False
    service_ids: Optional[List[int]] = None  # restrict to specific services


class DiscountResponse(BaseModel):
    id: int
    code: str
    name: str
    discount_type: str
    discount_value: float
    is_active: bool
    times_used: int

    class Config:
        from_attributes = True


class ApplyDiscountRequest(BaseModel):
    code: str
    subtotal: float
    customer_id: Optional[int] = None
    service_ids: Optional[List[int]] = None


@router.get("/")
def list_discounts(active_only: bool = True, db: Session = Depends(get_db)):
    """List all discount codes"""
    query = db.query(Discount)
    if active_only:
        now = datetime.utcnow()
        query = query.filter(
            Discount.is_active == True,
            (Discount.valid_until == None) | (Discount.valid_until > now)
        )
    
    discounts = query.order_by(Discount.created_at.desc()).all()
    
    return [
        {
            "id": d.id,
            "code": d.code,
            "name": d.name,
            "description": d.description,
            "discount_type": d.discount_type,
            "discount_value": d.discount_value,
            "min_purchase": d.min_purchase,
            "max_discount": d.max_discount,
            "max_uses": d.max_uses,
            "times_used": d.times_used,
            "valid_from": d.valid_from,
            "valid_until": d.valid_until,
            "is_active": d.is_active
        }
        for d in discounts
    ]


@router.post("/")
def create_discount(discount: DiscountCreate, db: Session = Depends(get_db)):
    """Create a new discount code"""
    # Check for duplicate code
    existing = db.query(Discount).filter(Discount.code == discount.code.upper()).first()
    if existing:
        raise HTTPException(status_code=400, detail="Discount code already exists")
    
    # Validate discount value
    if discount.discount_type == "percent" and (discount.discount_value <= 0 or discount.discount_value > 100):
        raise HTTPException(status_code=400, detail="Percentage must be between 1 and 100")
    if discount.discount_type == "fixed" and discount.discount_value <= 0:
        raise HTTPException(status_code=400, detail="Fixed discount must be positive")
    
    db_discount = Discount(
        code=discount.code.upper(),
        name=discount.name,
        description=discount.description,
        discount_type=discount.discount_type,
        discount_value=discount.discount_value,
        min_purchase=discount.min_purchase,
        max_discount=discount.max_discount,
        max_uses=discount.max_uses,
        max_uses_per_customer=discount.max_uses_per_customer,
        valid_from=discount.valid_from,
        valid_until=discount.valid_until,
        first_visit_only=discount.first_visit_only,
        service_ids=",".join(str(s) for s in discount.service_ids) if discount.service_ids else None
    )
    db.add(db_discount)
    db.commit()
    db.refresh(db_discount)
    
    return {
        "id": db_discount.id,
        "code": db_discount.code,
        "message": "Discount code created"
    }


@router.post("/apply")
def apply_discount(request: ApplyDiscountRequest, db: Session = Depends(get_db)):
    """Validate and calculate discount for an order"""
    discount = db.query(Discount).filter(Discount.code == request.code.upper()).first()
    if not discount:
        raise HTTPException(status_code=404, detail="Invalid discount code")
    
    # Check if active
    if not discount.is_active:
        raise HTTPException(status_code=400, detail="Discount code is no longer active")
    
    # Check date validity
    now = datetime.utcnow()
    if discount.valid_from and now < discount.valid_from:
        raise HTTPException(status_code=400, detail="Discount code is not yet valid")
    if discount.valid_until and now > discount.valid_until:
        raise HTTPException(status_code=400, detail="Discount code has expired")
    
    # Check max uses
    if discount.max_uses and discount.times_used >= discount.max_uses:
        raise HTTPException(status_code=400, detail="Discount code has reached maximum uses")
    
    # Check min purchase
    if request.subtotal < discount.min_purchase:
        raise HTTPException(
            status_code=400, 
            detail=f"Minimum purchase of ${discount.min_purchase:.2f} required"
        )
    
    # Check customer-specific limits
    if request.customer_id:
        customer_uses = db.query(DiscountUsage).filter(
            DiscountUsage.discount_id == discount.id,
            DiscountUsage.customer_id == request.customer_id
        ).count()
        
        if customer_uses >= discount.max_uses_per_customer:
            raise HTTPException(status_code=400, detail="You've already used this discount code")
        
        # Check first visit only
        if discount.first_visit_only:
            from app.models import Order
            previous_orders = db.query(Order).filter(
                Order.customer_id == request.customer_id,
                Order.status == "completed"
            ).count()
            if previous_orders > 0:
                raise HTTPException(status_code=400, detail="This discount is for first-time customers only")
    
    # Calculate discount amount
    if discount.discount_type == "percent":
        discount_amount = request.subtotal * (discount.discount_value / 100)
        if discount.max_discount:
            discount_amount = min(discount_amount, discount.max_discount)
    else:
        discount_amount = min(discount.discount_value, request.subtotal)
    
    return {
        "valid": True,
        "code": discount.code,
        "name": discount.name,
        "discount_type": discount.discount_type,
        "discount_value": discount.discount_value,
        "discount_amount": round(discount_amount, 2),
        "new_subtotal": round(request.subtotal - discount_amount, 2),
        "message": f"${discount_amount:.2f} discount applied!"
    }


@router.post("/use")
def record_discount_use(
    code: str,
    order_id: int,
    amount: float,
    customer_id: Optional[int] = None,
    db: Session = Depends(get_db)
):
    """Record that a discount was used on an order"""
    discount = db.query(Discount).filter(Discount.code == code.upper()).first()
    if not discount:
        raise HTTPException(status_code=404, detail="Discount not found")
    
    usage = DiscountUsage(
        discount_id=discount.id,
        order_id=order_id,
        customer_id=customer_id,
        amount_saved=amount
    )
    db.add(usage)
    
    discount.times_used += 1
    db.commit()
    
    return {"message": "Discount usage recorded"}


@router.patch("/{discount_id}/deactivate")
def deactivate_discount(discount_id: int, db: Session = Depends(get_db)):
    """Deactivate a discount code"""
    discount = db.query(Discount).filter(Discount.id == discount_id).first()
    if not discount:
        raise HTTPException(status_code=404, detail="Discount not found")
    
    discount.is_active = False
    db.commit()
    
    return {"message": "Discount deactivated"}


# Seed some common discounts
SEED_DISCOUNTS = [
    {
        "code": "WELCOME10",
        "name": "Welcome 10% Off",
        "description": "10% off your first visit",
        "discount_type": "percent",
        "discount_value": 10,
        "first_visit_only": True
    },
    {
        "code": "SUMMER25",
        "name": "Summer Special",
        "description": "$5 off any service",
        "discount_type": "fixed",
        "discount_value": 5,
        "min_purchase": 20
    },
    {
        "code": "BUDDY",
        "name": "Buddy Discount",
        "description": "15% off when you refer a friend",
        "discount_type": "percent",
        "discount_value": 15,
        "max_discount": 10
    }
]
