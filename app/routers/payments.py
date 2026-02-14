from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import Optional, List
from pydantic import BaseModel
from datetime import datetime

from app.database import get_db
from app.models import Payment, Order

router = APIRouter(prefix="/payments", tags=["payments"])

# Tip preset configuration
TIP_PRESETS = [
    {"percent": 15, "label": "15%"},
    {"percent": 18, "label": "18%"},
    {"percent": 20, "label": "20%"},
    {"percent": 25, "label": "25%"},
]


class PaymentCreate(BaseModel):
    order_id: int
    amount: float
    tip_amount: float = 0.0
    method: str = "card"


class SplitPayment(BaseModel):
    method: str
    amount: float
    tip_amount: float = 0.0


class PaymentResponse(BaseModel):
    id: int
    order_id: int
    amount: float
    tip_amount: float
    method: str
    created_at: datetime

    class Config:
        from_attributes = True


@router.post("/", response_model=PaymentResponse)
def process_payment(payment: PaymentCreate, db: Session = Depends(get_db)):
    order = db.query(Order).filter(Order.id == payment.order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    
    # Check if already paid
    existing = db.query(Payment).filter(Payment.order_id == payment.order_id).first()
    if existing:
        raise HTTPException(status_code=400, detail="Order already paid")
    
    # Update order with tip
    order.tip = payment.tip_amount
    order.total = order.subtotal + order.tax + payment.tip_amount
    order.status = "completed"
    order.completed_at = datetime.utcnow()
    
    # Create payment record
    db_payment = Payment(
        order_id=payment.order_id,
        amount=payment.amount,
        tip_amount=payment.tip_amount,
        method=payment.method
    )
    db.add(db_payment)
    db.commit()
    db.refresh(db_payment)
    
    return db_payment


@router.get("/order/{order_id}")
def get_payment_for_order(order_id: int, db: Session = Depends(get_db)):
    payment = db.query(Payment).filter(Payment.order_id == order_id).first()
    if not payment:
        raise HTTPException(status_code=404, detail="Payment not found")
    return payment


# ===== TIP PRESETS =====

@router.get("/tips/presets/{order_id}")
def get_tip_presets(order_id: int, db: Session = Depends(get_db)):
    """Get tip preset amounts for an order"""
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    
    subtotal = order.subtotal
    
    presets = []
    for preset in TIP_PRESETS:
        tip_amount = round(subtotal * (preset["percent"] / 100), 2)
        presets.append({
            "percent": preset["percent"],
            "label": preset["label"],
            "amount": tip_amount
        })
    
    # Add custom option
    presets.append({"percent": None, "label": "Custom", "amount": None})
    
    return {
        "order_id": order_id,
        "subtotal": subtotal,
        "presets": presets,
        "suggested": presets[2] if len(presets) > 2 else presets[0]  # Suggest 20%
    }


@router.get("/tips/calculate")
def calculate_tip(amount: float, percent: float):
    """Calculate tip amount"""
    tip = round(amount * (percent / 100), 2)
    return {
        "subtotal": amount,
        "tip_percent": percent,
        "tip_amount": tip,
        "total": round(amount + tip, 2)
    }


# ===== SPLIT PAYMENTS =====

@router.post("/split/{order_id}")
def process_split_payment(order_id: int, payments: List[SplitPayment], db: Session = Depends(get_db)):
    """Process a split payment across multiple methods"""
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    
    # Check if already paid
    existing = db.query(Payment).filter(Payment.order_id == order_id).first()
    if existing:
        raise HTTPException(status_code=400, detail="Order already paid")
    
    # Validate split amounts
    total_paid = sum(p.amount for p in payments)
    total_tip = sum(p.tip_amount for p in payments)
    expected_total = order.subtotal + order.tax
    
    if abs(total_paid - expected_total) > 0.01:
        return {
            "error": "Split amounts don't match order total",
            "order_total": expected_total,
            "split_total": total_paid,
            "difference": round(expected_total - total_paid, 2)
        }
    
    # Process each payment
    payment_records = []
    for i, p in enumerate(payments):
        db_payment = Payment(
            order_id=order_id,
            amount=p.amount,
            tip_amount=p.tip_amount,
            method=p.method
        )
        db.add(db_payment)
        payment_records.append({
            "method": p.method,
            "amount": p.amount,
            "tip": p.tip_amount
        })
    
    # Update order
    order.tip = total_tip
    order.total = order.subtotal + order.tax + total_tip
    order.status = "completed"
    order.completed_at = datetime.utcnow()
    
    db.commit()
    
    return {
        "message": "Split payment processed",
        "order_id": order_id,
        "payments": payment_records,
        "total_paid": total_paid,
        "total_tip": total_tip
    }


@router.get("/split/suggest/{order_id}")
def suggest_split(order_id: int, num_ways: int = 2, db: Session = Depends(get_db)):
    """Suggest even split for an order"""
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    
    total = order.subtotal + order.tax
    per_person = round(total / num_ways, 2)
    
    # Handle rounding
    split_amounts = [per_person] * num_ways
    remainder = round(total - sum(split_amounts), 2)
    if remainder != 0:
        split_amounts[0] = round(split_amounts[0] + remainder, 2)
    
    return {
        "order_id": order_id,
        "order_total": total,
        "num_ways": num_ways,
        "per_person": per_person,
        "split_amounts": split_amounts,
        "suggested_tip_per_person": round(per_person * 0.20, 2)  # 20% tip suggestion
    }


# ===== PAYMENT METHODS =====

@router.get("/methods")
def get_payment_methods():
    """Get available payment methods"""
    return {
        "methods": [
            {"id": "cash", "name": "Cash", "icon": "💵"},
            {"id": "card", "name": "Credit/Debit Card", "icon": "💳"},
            {"id": "apple_pay", "name": "Apple Pay", "icon": "🍎"},
            {"id": "google_pay", "name": "Google Pay", "icon": "🔷"},
            {"id": "venmo", "name": "Venmo", "icon": "💜"},
            {"id": "gift_card", "name": "Gift Card", "icon": "🎁"},
        ]
    }


@router.post("/quick-cash/{order_id}")
def process_quick_cash(order_id: int, amount_given: float, tip_percent: float = 0, db: Session = Depends(get_db)):
    """Quick cash payment with change calculation"""
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    
    # Check if already paid
    existing = db.query(Payment).filter(Payment.order_id == order_id).first()
    if existing:
        raise HTTPException(status_code=400, detail="Order already paid")
    
    subtotal = order.subtotal + order.tax
    tip_amount = round(subtotal * (tip_percent / 100), 2)
    total_due = subtotal + tip_amount
    
    if amount_given < total_due:
        return {
            "error": "Insufficient payment",
            "total_due": total_due,
            "amount_given": amount_given,
            "short_by": round(total_due - amount_given, 2)
        }
    
    change = round(amount_given - total_due, 2)
    
    # Create payment
    db_payment = Payment(
        order_id=order_id,
        amount=subtotal,
        tip_amount=tip_amount,
        method="cash"
    )
    db.add(db_payment)
    
    # Update order
    order.tip = tip_amount
    order.total = total_due
    order.status = "completed"
    order.completed_at = datetime.utcnow()
    
    db.commit()
    
    return {
        "message": "Cash payment processed",
        "subtotal": subtotal,
        "tip": tip_amount,
        "total": total_due,
        "amount_given": amount_given,
        "change_due": change
    }
