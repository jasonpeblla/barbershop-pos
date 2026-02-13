from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import Optional
from pydantic import BaseModel
from datetime import datetime

from app.database import get_db
from app.models import Payment, Order

router = APIRouter(prefix="/payments", tags=["payments"])


class PaymentCreate(BaseModel):
    order_id: int
    amount: float
    tip_amount: float = 0.0
    method: str = "card"


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
