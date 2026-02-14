from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional
from pydantic import BaseModel
from datetime import datetime, date
import secrets
import string

from app.database import get_db
from app.models import GiftCard, GiftCardTransaction

router = APIRouter(prefix="/gift-cards", tags=["gift-cards"])


def generate_card_code():
    """Generate a unique 16-character gift card code"""
    chars = string.ascii_uppercase + string.digits
    return '-'.join([''.join(secrets.choice(chars) for _ in range(4)) for _ in range(4)])


class GiftCardCreate(BaseModel):
    initial_balance: float
    purchaser_name: Optional[str] = None
    purchaser_email: Optional[str] = None
    recipient_name: Optional[str] = None
    recipient_email: Optional[str] = None
    message: Optional[str] = None


class GiftCardResponse(BaseModel):
    id: int
    code: str
    initial_balance: float
    current_balance: float
    purchaser_name: Optional[str]
    recipient_name: Optional[str]
    is_active: bool
    created_at: datetime
    expires_at: Optional[datetime]

    class Config:
        from_attributes = True


class RedeemRequest(BaseModel):
    code: str
    amount: float


@router.post("/")
def create_gift_card(card: GiftCardCreate, db: Session = Depends(get_db)):
    """Purchase a new gift card"""
    if card.initial_balance < 10:
        raise HTTPException(status_code=400, detail="Minimum gift card value is $10")
    if card.initial_balance > 500:
        raise HTTPException(status_code=400, detail="Maximum gift card value is $500")
    
    # Generate unique code
    code = generate_card_code()
    while db.query(GiftCard).filter(GiftCard.code == code).first():
        code = generate_card_code()
    
    gift_card = GiftCard(
        code=code,
        initial_balance=card.initial_balance,
        current_balance=card.initial_balance,
        purchaser_name=card.purchaser_name,
        purchaser_email=card.purchaser_email,
        recipient_name=card.recipient_name,
        recipient_email=card.recipient_email,
        message=card.message
    )
    db.add(gift_card)
    db.commit()
    db.refresh(gift_card)
    
    # Record initial transaction
    transaction = GiftCardTransaction(
        gift_card_id=gift_card.id,
        amount=card.initial_balance,
        transaction_type="purchase",
        description="Gift card purchased"
    )
    db.add(transaction)
    db.commit()
    
    return {
        "id": gift_card.id,
        "code": gift_card.code,
        "balance": gift_card.current_balance,
        "message": f"Gift card created with ${card.initial_balance:.2f} balance"
    }


@router.get("/lookup/{code}")
def lookup_gift_card(code: str, db: Session = Depends(get_db)):
    """Look up a gift card by code"""
    card = db.query(GiftCard).filter(GiftCard.code == code.upper()).first()
    if not card:
        raise HTTPException(status_code=404, detail="Gift card not found")
    
    return {
        "id": card.id,
        "code": card.code,
        "current_balance": card.current_balance,
        "initial_balance": card.initial_balance,
        "is_active": card.is_active,
        "recipient_name": card.recipient_name,
        "created_at": card.created_at
    }


@router.post("/redeem")
def redeem_gift_card(request: RedeemRequest, db: Session = Depends(get_db)):
    """Redeem gift card balance for payment"""
    card = db.query(GiftCard).filter(GiftCard.code == request.code.upper()).first()
    if not card:
        raise HTTPException(status_code=404, detail="Gift card not found")
    
    if not card.is_active:
        raise HTTPException(status_code=400, detail="Gift card is not active")
    
    if card.current_balance < request.amount:
        raise HTTPException(
            status_code=400, 
            detail=f"Insufficient balance. Available: ${card.current_balance:.2f}"
        )
    
    # Deduct balance
    card.current_balance -= request.amount
    
    # Record transaction
    transaction = GiftCardTransaction(
        gift_card_id=card.id,
        amount=-request.amount,
        transaction_type="redemption",
        description=f"Redeemed ${request.amount:.2f} for purchase"
    )
    db.add(transaction)
    db.commit()
    
    return {
        "message": f"Redeemed ${request.amount:.2f}",
        "remaining_balance": card.current_balance,
        "amount_applied": request.amount
    }


@router.post("/reload/{code}")
def reload_gift_card(code: str, amount: float, db: Session = Depends(get_db)):
    """Add balance to an existing gift card"""
    card = db.query(GiftCard).filter(GiftCard.code == code.upper()).first()
    if not card:
        raise HTTPException(status_code=404, detail="Gift card not found")
    
    if amount < 10:
        raise HTTPException(status_code=400, detail="Minimum reload amount is $10")
    
    card.current_balance += amount
    
    transaction = GiftCardTransaction(
        gift_card_id=card.id,
        amount=amount,
        transaction_type="reload",
        description=f"Reloaded ${amount:.2f}"
    )
    db.add(transaction)
    db.commit()
    
    return {
        "message": f"Reloaded ${amount:.2f}",
        "new_balance": card.current_balance
    }


@router.get("/{card_id}/history")
def gift_card_history(card_id: int, db: Session = Depends(get_db)):
    """Get transaction history for a gift card"""
    card = db.query(GiftCard).filter(GiftCard.id == card_id).first()
    if not card:
        raise HTTPException(status_code=404, detail="Gift card not found")
    
    transactions = db.query(GiftCardTransaction).filter(
        GiftCardTransaction.gift_card_id == card_id
    ).order_by(GiftCardTransaction.created_at.desc()).all()
    
    return {
        "card": {
            "code": card.code,
            "current_balance": card.current_balance,
            "initial_balance": card.initial_balance
        },
        "transactions": [
            {
                "id": t.id,
                "amount": t.amount,
                "type": t.transaction_type,
                "description": t.description,
                "created_at": t.created_at
            }
            for t in transactions
        ]
    }


@router.get("/")
def list_gift_cards(active_only: bool = True, db: Session = Depends(get_db)):
    """List all gift cards"""
    query = db.query(GiftCard)
    if active_only:
        query = query.filter(GiftCard.is_active == True, GiftCard.current_balance > 0)
    
    cards = query.order_by(GiftCard.created_at.desc()).limit(50).all()
    
    return [
        {
            "id": c.id,
            "code": c.code,
            "current_balance": c.current_balance,
            "initial_balance": c.initial_balance,
            "recipient_name": c.recipient_name,
            "is_active": c.is_active,
            "created_at": c.created_at
        }
        for c in cards
    ]
