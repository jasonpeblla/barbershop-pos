from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional
from pydantic import BaseModel
from datetime import datetime

from app.database import get_db
from app.models import Customer, LoyaltyTransaction, Order

router = APIRouter(prefix="/loyalty", tags=["loyalty"])

# Points configuration
POINTS_PER_DOLLAR = 1  # 1 point per $1 spent
POINTS_TO_DOLLAR = 100  # 100 points = $1 redemption value
SIGNUP_BONUS = 50  # Points for new customers


class LoyaltyBalance(BaseModel):
    customer_id: int
    customer_name: str
    current_points: int
    lifetime_points: int
    redemption_value: float  # Dollar value of current points


class LoyaltyTransactionCreate(BaseModel):
    customer_id: int
    points: int
    transaction_type: str
    description: Optional[str] = None
    order_id: Optional[int] = None


class LoyaltyTransactionResponse(BaseModel):
    id: int
    customer_id: int
    order_id: Optional[int]
    points: int
    transaction_type: str
    description: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


class RedeemRequest(BaseModel):
    customer_id: int
    points: int


@router.get("/balance/{customer_id}", response_model=LoyaltyBalance)
def get_loyalty_balance(customer_id: int, db: Session = Depends(get_db)):
    """Get customer's current loyalty points balance"""
    customer = db.query(Customer).filter(Customer.id == customer_id).first()
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    
    return LoyaltyBalance(
        customer_id=customer.id,
        customer_name=customer.name,
        current_points=customer.loyalty_points or 0,
        lifetime_points=customer.lifetime_points or 0,
        redemption_value=(customer.loyalty_points or 0) / POINTS_TO_DOLLAR
    )


@router.get("/history/{customer_id}", response_model=List[LoyaltyTransactionResponse])
def get_loyalty_history(customer_id: int, limit: int = 20, db: Session = Depends(get_db)):
    """Get customer's loyalty points transaction history"""
    transactions = db.query(LoyaltyTransaction).filter(
        LoyaltyTransaction.customer_id == customer_id
    ).order_by(LoyaltyTransaction.created_at.desc()).limit(limit).all()
    return transactions


@router.post("/earn")
def earn_points(order_id: int, db: Session = Depends(get_db)):
    """Award loyalty points for a completed order (1 point per $1 spent)"""
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    
    if not order.customer_id:
        return {"message": "No customer linked to order - no points awarded"}
    
    customer = db.query(Customer).filter(Customer.id == order.customer_id).first()
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    
    # Calculate points (1 per dollar spent, excluding tax)
    points_earned = int(order.subtotal * POINTS_PER_DOLLAR)
    
    if points_earned <= 0:
        return {"message": "No points earned", "points": 0}
    
    # Check if points already awarded for this order
    existing = db.query(LoyaltyTransaction).filter(
        LoyaltyTransaction.order_id == order_id,
        LoyaltyTransaction.transaction_type == "earned"
    ).first()
    if existing:
        return {"message": "Points already awarded for this order", "points": existing.points}
    
    # Award points
    customer.loyalty_points = (customer.loyalty_points or 0) + points_earned
    customer.lifetime_points = (customer.lifetime_points or 0) + points_earned
    
    transaction = LoyaltyTransaction(
        customer_id=customer.id,
        order_id=order_id,
        points=points_earned,
        transaction_type="earned",
        description=f"Earned from order #{order_id}"
    )
    db.add(transaction)
    db.commit()
    
    return {
        "message": f"Awarded {points_earned} points",
        "points_earned": points_earned,
        "new_balance": customer.loyalty_points
    }


@router.post("/redeem")
def redeem_points(request: RedeemRequest, db: Session = Depends(get_db)):
    """Redeem loyalty points for discount (100 points = $1)"""
    customer = db.query(Customer).filter(Customer.id == request.customer_id).first()
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    
    current_points = customer.loyalty_points or 0
    if request.points > current_points:
        raise HTTPException(status_code=400, detail=f"Insufficient points. Balance: {current_points}")
    
    if request.points < POINTS_TO_DOLLAR:
        raise HTTPException(status_code=400, detail=f"Minimum redemption is {POINTS_TO_DOLLAR} points")
    
    # Calculate discount value
    discount_value = request.points / POINTS_TO_DOLLAR
    
    # Deduct points
    customer.loyalty_points = current_points - request.points
    
    transaction = LoyaltyTransaction(
        customer_id=customer.id,
        points=-request.points,
        transaction_type="redeemed",
        description=f"Redeemed for ${discount_value:.2f} discount"
    )
    db.add(transaction)
    db.commit()
    
    return {
        "message": f"Redeemed {request.points} points for ${discount_value:.2f} discount",
        "discount_value": discount_value,
        "points_redeemed": request.points,
        "new_balance": customer.loyalty_points
    }


@router.post("/bonus")
def award_bonus(customer_id: int, points: int, reason: str, db: Session = Depends(get_db)):
    """Award bonus points (signup bonus, promotions, etc.)"""
    customer = db.query(Customer).filter(Customer.id == customer_id).first()
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    
    customer.loyalty_points = (customer.loyalty_points or 0) + points
    customer.lifetime_points = (customer.lifetime_points or 0) + points
    
    transaction = LoyaltyTransaction(
        customer_id=customer.id,
        points=points,
        transaction_type="bonus",
        description=reason
    )
    db.add(transaction)
    db.commit()
    
    return {
        "message": f"Awarded {points} bonus points",
        "reason": reason,
        "new_balance": customer.loyalty_points
    }


@router.get("/config")
def get_loyalty_config():
    """Get loyalty program configuration"""
    return {
        "points_per_dollar": POINTS_PER_DOLLAR,
        "points_to_dollar": POINTS_TO_DOLLAR,
        "signup_bonus": SIGNUP_BONUS,
        "min_redemption": POINTS_TO_DOLLAR
    }
