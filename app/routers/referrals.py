from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional
from datetime import datetime
import random
import string

from app.database import get_db
from app.models import Referral, Customer, LoyaltyTransaction

router = APIRouter(prefix="/referrals", tags=["Referral Program"])

# Referral rewards configuration
REFERRAL_CONFIG = {
    "referrer_reward_type": "points",
    "referrer_reward_value": 100,  # 100 loyalty points
    "referred_reward_type": "discount",
    "referred_reward_value": 15,  # 15% off first visit
}


def generate_referral_code(length: int = 8) -> str:
    """Generate a unique referral code"""
    chars = string.ascii_uppercase + string.digits
    return ''.join(random.choices(chars, k=length))


class ReferralCreate(BaseModel):
    referred_name: Optional[str] = None
    referred_phone: Optional[str] = None


class ReferralComplete(BaseModel):
    referral_code: str
    new_customer_id: int


@router.get("/customer/{customer_id}/code")
def get_or_create_referral_code(customer_id: int, db: Session = Depends(get_db)):
    """Get or create a referral code for a customer"""
    customer = db.query(Customer).filter(Customer.id == customer_id).first()
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    
    # Check for existing unused referral code
    existing = db.query(Referral).filter(
        Referral.referrer_id == customer_id,
        Referral.status == "pending",
        Referral.referred_id.is_(None)
    ).first()
    
    if existing:
        return {
            "referral_code": existing.referral_code,
            "referrer_name": customer.name,
            "referrer_reward": f"{REFERRAL_CONFIG['referrer_reward_value']} {REFERRAL_CONFIG['referrer_reward_type']}",
            "referred_reward": f"{REFERRAL_CONFIG['referred_reward_value']}% off first visit"
        }
    
    # Create new referral code
    code = generate_referral_code()
    while db.query(Referral).filter(Referral.referral_code == code).first():
        code = generate_referral_code()
    
    referral = Referral(
        referrer_id=customer_id,
        referral_code=code,
        referrer_reward_type=REFERRAL_CONFIG["referrer_reward_type"],
        referrer_reward_value=REFERRAL_CONFIG["referrer_reward_value"],
        referred_reward_type=REFERRAL_CONFIG["referred_reward_type"],
        referred_reward_value=REFERRAL_CONFIG["referred_reward_value"]
    )
    db.add(referral)
    db.commit()
    db.refresh(referral)
    
    return {
        "referral_code": referral.referral_code,
        "referrer_name": customer.name,
        "referrer_reward": f"{REFERRAL_CONFIG['referrer_reward_value']} {REFERRAL_CONFIG['referrer_reward_type']}",
        "referred_reward": f"{REFERRAL_CONFIG['referred_reward_value']}% off first visit"
    }


@router.get("/validate/{code}")
def validate_referral_code(code: str, db: Session = Depends(get_db)):
    """Validate a referral code"""
    referral = db.query(Referral).filter(
        Referral.referral_code == code.upper(),
        Referral.status == "pending"
    ).first()
    
    if not referral:
        return {"valid": False, "message": "Invalid or already used referral code"}
    
    referrer = db.query(Customer).filter(Customer.id == referral.referrer_id).first()
    
    return {
        "valid": True,
        "referrer_name": referrer.name if referrer else "Unknown",
        "discount_percent": referral.referred_reward_value,
        "message": f"Valid! You'll get {referral.referred_reward_value}% off your first visit"
    }


@router.post("/complete")
def complete_referral(data: ReferralComplete, db: Session = Depends(get_db)):
    """Complete a referral when new customer makes first purchase"""
    referral = db.query(Referral).filter(
        Referral.referral_code == data.referral_code.upper(),
        Referral.status == "pending"
    ).first()
    
    if not referral:
        raise HTTPException(status_code=404, detail="Invalid or already used referral code")
    
    new_customer = db.query(Customer).filter(Customer.id == data.new_customer_id).first()
    if not new_customer:
        raise HTTPException(status_code=404, detail="New customer not found")
    
    # Update referral
    referral.referred_id = data.new_customer_id
    referral.status = "completed"
    
    # Award referrer
    referrer = db.query(Customer).filter(Customer.id == referral.referrer_id).first()
    if referrer and referral.referrer_reward_type == "points":
        referrer.loyalty_points = (referrer.loyalty_points or 0) + int(referral.referrer_reward_value)
        referrer.lifetime_points = (referrer.lifetime_points or 0) + int(referral.referrer_reward_value)
        
        # Log loyalty transaction
        transaction = LoyaltyTransaction(
            customer_id=referrer.id,
            points=int(referral.referrer_reward_value),
            transaction_type="bonus",
            description=f"Referral bonus - {new_customer.name} signed up"
        )
        db.add(transaction)
    
    referral.rewarded_at = datetime.utcnow()
    referral.status = "rewarded"
    db.commit()
    
    return {
        "message": "Referral completed",
        "referrer_rewarded": True,
        "referrer_reward": f"{referral.referrer_reward_value} {referral.referrer_reward_type}",
        "referred_discount": f"{referral.referred_reward_value}%"
    }


@router.get("/customer/{customer_id}/stats")
def get_referral_stats(customer_id: int, db: Session = Depends(get_db)):
    """Get referral statistics for a customer"""
    customer = db.query(Customer).filter(Customer.id == customer_id).first()
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    
    referrals = db.query(Referral).filter(
        Referral.referrer_id == customer_id
    ).all()
    
    total_referrals = len([r for r in referrals if r.status in ["completed", "rewarded"]])
    pending_referrals = len([r for r in referrals if r.status == "pending" and r.referred_id])
    total_rewards = sum(r.referrer_reward_value for r in referrals if r.status == "rewarded")
    
    referred_customers = []
    for r in referrals:
        if r.referred_id:
            referred = db.query(Customer).filter(Customer.id == r.referred_id).first()
            if referred:
                referred_customers.append({
                    "name": referred.name,
                    "status": r.status,
                    "date": r.created_at
                })
    
    return {
        "customer_id": customer_id,
        "customer_name": customer.name,
        "total_successful_referrals": total_referrals,
        "pending_referrals": pending_referrals,
        "total_rewards_earned": total_rewards,
        "reward_type": REFERRAL_CONFIG["referrer_reward_type"],
        "referred_customers": referred_customers
    }


@router.get("/customer/{customer_id}/history")
def get_referral_history(customer_id: int, db: Session = Depends(get_db)):
    """Get all referrals made by a customer"""
    referrals = db.query(Referral).filter(
        Referral.referrer_id == customer_id
    ).order_by(Referral.created_at.desc()).all()
    
    return [
        {
            "id": r.id,
            "code": r.referral_code,
            "status": r.status,
            "referred_name": db.query(Customer).filter(Customer.id == r.referred_id).first().name if r.referred_id else r.referred_name,
            "reward_earned": r.referrer_reward_value if r.status == "rewarded" else 0,
            "created_at": r.created_at,
            "rewarded_at": r.rewarded_at
        }
        for r in referrals
    ]


@router.get("/leaderboard")
def get_referral_leaderboard(limit: int = 10, db: Session = Depends(get_db)):
    """Get top referrers"""
    from sqlalchemy import func
    
    # Get counts of successful referrals per customer
    results = db.query(
        Referral.referrer_id,
        func.count(Referral.id).label('count')
    ).filter(
        Referral.status.in_(["completed", "rewarded"])
    ).group_by(Referral.referrer_id).order_by(func.count(Referral.id).desc()).limit(limit).all()
    
    leaderboard = []
    for referrer_id, count in results:
        customer = db.query(Customer).filter(Customer.id == referrer_id).first()
        if customer:
            leaderboard.append({
                "rank": len(leaderboard) + 1,
                "customer_id": referrer_id,
                "customer_name": customer.name,
                "referral_count": count,
                "total_rewards": count * REFERRAL_CONFIG["referrer_reward_value"]
            })
    
    return leaderboard


@router.get("/config")
def get_referral_config():
    """Get current referral program configuration"""
    return {
        "referrer_reward": {
            "type": REFERRAL_CONFIG["referrer_reward_type"],
            "value": REFERRAL_CONFIG["referrer_reward_value"],
            "description": f"{REFERRAL_CONFIG['referrer_reward_value']} loyalty points per successful referral"
        },
        "referred_reward": {
            "type": REFERRAL_CONFIG["referred_reward_type"],
            "value": REFERRAL_CONFIG["referred_reward_value"],
            "description": f"{REFERRAL_CONFIG['referred_reward_value']}% off first visit"
        }
    }
