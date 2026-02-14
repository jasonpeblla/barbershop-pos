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


# ===== VIP TIER SYSTEM =====

VIP_TIERS = {
    "bronze": {"min_spent": 0, "min_visits": 0, "discount": 0, "points_multiplier": 1.0},
    "silver": {"min_spent": 200, "min_visits": 5, "discount": 5, "points_multiplier": 1.25},
    "gold": {"min_spent": 500, "min_visits": 15, "discount": 10, "points_multiplier": 1.5},
    "platinum": {"min_spent": 1000, "min_visits": 30, "discount": 15, "points_multiplier": 2.0}
}


def calculate_vip_tier(total_spent: float, visit_count: int) -> str:
    """Calculate VIP tier based on spending and visits"""
    tier = "bronze"
    for tier_name, requirements in VIP_TIERS.items():
        if total_spent >= requirements["min_spent"] and visit_count >= requirements["min_visits"]:
            tier = tier_name
    return tier


@router.get("/{customer_id}/vip-status")
def get_vip_status(customer_id: int, db: Session = Depends(get_db)):
    """Get customer's VIP tier status and benefits"""
    customer = db.query(Customer).filter(Customer.id == customer_id).first()
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    
    current_tier = customer.vip_tier or "bronze"
    tier_benefits = VIP_TIERS.get(current_tier, VIP_TIERS["bronze"])
    
    # Calculate progress to next tier
    tier_order = ["bronze", "silver", "gold", "platinum"]
    current_index = tier_order.index(current_tier)
    
    next_tier = None
    next_tier_progress = None
    
    if current_index < len(tier_order) - 1:
        next_tier = tier_order[current_index + 1]
        next_requirements = VIP_TIERS[next_tier]
        
        spent_progress = min(100, (customer.total_spent / next_requirements["min_spent"]) * 100) if next_requirements["min_spent"] > 0 else 100
        visits_progress = min(100, (customer.visit_count / next_requirements["min_visits"]) * 100) if next_requirements["min_visits"] > 0 else 100
        
        next_tier_progress = {
            "tier": next_tier,
            "spent_needed": next_requirements["min_spent"] - customer.total_spent,
            "visits_needed": next_requirements["min_visits"] - customer.visit_count,
            "spent_progress_percent": round(spent_progress, 1),
            "visits_progress_percent": round(visits_progress, 1)
        }
    
    return {
        "customer_id": customer.id,
        "customer_name": customer.name,
        "current_tier": current_tier,
        "total_spent": customer.total_spent or 0,
        "visit_count": customer.visit_count or 0,
        "benefits": {
            "discount_percent": tier_benefits["discount"],
            "points_multiplier": tier_benefits["points_multiplier"]
        },
        "next_tier_progress": next_tier_progress
    }


@router.post("/{customer_id}/update-tier")
def update_customer_tier(customer_id: int, db: Session = Depends(get_db)):
    """Recalculate and update customer's VIP tier based on current stats"""
    customer = db.query(Customer).filter(Customer.id == customer_id).first()
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    
    # Calculate stats from orders if not tracked
    if not customer.total_spent or not customer.visit_count:
        orders = db.query(Order).filter(
            Order.customer_id == customer_id,
            Order.status == "completed"
        ).all()
        
        customer.total_spent = sum(o.total for o in orders)
        customer.visit_count = len(orders)
    
    old_tier = customer.vip_tier or "bronze"
    new_tier = calculate_vip_tier(customer.total_spent, customer.visit_count)
    customer.vip_tier = new_tier
    
    db.commit()
    
    tier_changed = old_tier != new_tier
    
    return {
        "customer_id": customer.id,
        "old_tier": old_tier,
        "new_tier": new_tier,
        "tier_upgraded": tier_changed and tier_order.index(new_tier) > tier_order.index(old_tier) if tier_changed else False,
        "benefits": VIP_TIERS[new_tier]
    }


@router.get("/vip/all")
def get_all_vip_customers(tier: Optional[str] = None, db: Session = Depends(get_db)):
    """Get all customers by VIP tier"""
    query = db.query(Customer)
    
    if tier:
        query = query.filter(Customer.vip_tier == tier)
    else:
        # Exclude bronze by default to show VIP customers
        query = query.filter(Customer.vip_tier.in_(["silver", "gold", "platinum"]))
    
    customers = query.order_by(Customer.total_spent.desc()).all()
    
    return [
        {
            "id": c.id,
            "name": c.name,
            "phone": c.phone,
            "vip_tier": c.vip_tier or "bronze",
            "total_spent": c.total_spent or 0,
            "visit_count": c.visit_count or 0,
            "discount_percent": VIP_TIERS.get(c.vip_tier or "bronze", {}).get("discount", 0)
        }
        for c in customers
    ]


@router.get("/vip/tiers")
def get_vip_tier_info():
    """Get VIP tier requirements and benefits"""
    return {
        "tiers": [
            {
                "name": name,
                "min_spent": details["min_spent"],
                "min_visits": details["min_visits"],
                "discount_percent": details["discount"],
                "points_multiplier": details["points_multiplier"]
            }
            for name, details in VIP_TIERS.items()
        ]
    }


# Helper variable for tier order
tier_order = ["bronze", "silver", "gold", "platinum"]


# ===== CUSTOMER TAGS/PREFERENCES =====

PREDEFINED_TAGS = [
    "prefers-quiet",
    "chatty",
    "senior",
    "student",
    "military",
    "cash-only",
    "card-preferred",
    "walk-in-regular",
    "appointment-only",
    "sensitive-scalp",
    "thick-hair",
    "thinning-hair",
    "beard-enthusiast",
    "quick-service",
    "takes-time",
    "tips-well",
    "first-responder",
    "local-business",
    "referred",
    "influencer"
]


@router.get("/tags/available")
def get_available_tags():
    """Get list of predefined tags"""
    return {
        "tags": PREDEFINED_TAGS,
        "categories": {
            "personality": ["prefers-quiet", "chatty"],
            "demographics": ["senior", "student", "military", "first-responder"],
            "payment": ["cash-only", "card-preferred"],
            "booking": ["walk-in-regular", "appointment-only"],
            "hair_type": ["sensitive-scalp", "thick-hair", "thinning-hair", "beard-enthusiast"],
            "service": ["quick-service", "takes-time"],
            "business": ["local-business", "influencer", "tips-well"]
        }
    }


@router.post("/{customer_id}/tags/add")
def add_customer_tag(customer_id: int, tag: str, db: Session = Depends(get_db)):
    """Add a tag to a customer"""
    customer = db.query(Customer).filter(Customer.id == customer_id).first()
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    
    tag = tag.lower().strip()
    current_tags = customer.tags.split(",") if customer.tags else []
    
    if tag in current_tags:
        return {"message": "Tag already exists", "tags": current_tags}
    
    current_tags.append(tag)
    customer.tags = ",".join(current_tags)
    db.commit()
    
    return {"message": "Tag added", "tags": current_tags}


@router.post("/{customer_id}/tags/remove")
def remove_customer_tag(customer_id: int, tag: str, db: Session = Depends(get_db)):
    """Remove a tag from a customer"""
    customer = db.query(Customer).filter(Customer.id == customer_id).first()
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    
    tag = tag.lower().strip()
    current_tags = customer.tags.split(",") if customer.tags else []
    
    if tag not in current_tags:
        return {"message": "Tag not found", "tags": current_tags}
    
    current_tags.remove(tag)
    customer.tags = ",".join(current_tags) if current_tags else None
    db.commit()
    
    return {"message": "Tag removed", "tags": current_tags}


@router.get("/{customer_id}/tags")
def get_customer_tags(customer_id: int, db: Session = Depends(get_db)):
    """Get all tags for a customer"""
    customer = db.query(Customer).filter(Customer.id == customer_id).first()
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    
    tags = customer.tags.split(",") if customer.tags else []
    
    return {
        "customer_id": customer_id,
        "customer_name": customer.name,
        "tags": tags,
        "communication_preference": customer.communication_preference or "any"
    }


@router.get("/by-tag/{tag}")
def get_customers_by_tag(tag: str, db: Session = Depends(get_db)):
    """Get all customers with a specific tag"""
    tag = tag.lower().strip()
    
    customers = db.query(Customer).filter(
        Customer.tags.contains(tag)
    ).all()
    
    return [
        {
            "id": c.id,
            "name": c.name,
            "phone": c.phone,
            "tags": c.tags.split(",") if c.tags else []
        }
        for c in customers
    ]


@router.patch("/{customer_id}/communication-preference")
def set_communication_preference(customer_id: int, preference: str, db: Session = Depends(get_db)):
    """Set customer's communication preference"""
    if preference not in ["sms", "email", "any", "none"]:
        raise HTTPException(status_code=400, detail="Invalid preference. Use: sms, email, any, or none")
    
    customer = db.query(Customer).filter(Customer.id == customer_id).first()
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    
    customer.communication_preference = preference
    db.commit()
    
    return {"message": "Preference updated", "communication_preference": preference}


# ===== VISIT STREAK SYSTEM =====

STREAK_REWARDS = {
    3: {"type": "discount", "value": 5, "description": "5% off your next visit"},
    5: {"type": "discount", "value": 10, "description": "10% off your next visit"},
    10: {"type": "free_service", "value": "eyebrow_trim", "description": "Free eyebrow trim"},
    15: {"type": "discount", "value": 15, "description": "15% off your next visit"},
    20: {"type": "free_service", "value": "beard_trim", "description": "Free beard trim"},
    25: {"type": "discount", "value": 20, "description": "20% off your next visit"},
}


@router.post("/{customer_id}/record-visit")
def record_customer_visit(customer_id: int, db: Session = Depends(get_db)):
    """Record a customer visit and update streak"""
    customer = db.query(Customer).filter(Customer.id == customer_id).first()
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    
    today = datetime.now().date()
    streak_maintained = False
    streak_broken = False
    new_reward = None
    
    if customer.last_visit_date:
        last_visit = customer.last_visit_date.date() if isinstance(customer.last_visit_date, datetime) else customer.last_visit_date
        days_since = (today - last_visit).days
        
        if days_since == 0:
            # Same day visit - don't update streak
            return {
                "message": "Visit already recorded today",
                "current_streak": customer.current_streak,
                "longest_streak": customer.longest_streak
            }
        elif days_since <= 35:  # Within ~monthly window
            # Streak continues
            customer.current_streak = (customer.current_streak or 0) + 1
            streak_maintained = True
        else:
            # Streak broken
            customer.current_streak = 1
            streak_broken = True
    else:
        # First visit
        customer.current_streak = 1
    
    # Update last visit
    customer.last_visit_date = datetime.now()
    
    # Update longest streak
    if customer.current_streak > (customer.longest_streak or 0):
        customer.longest_streak = customer.current_streak
    
    # Update visit count
    customer.visit_count = (customer.visit_count or 0) + 1
    
    # Check for streak reward
    if customer.current_streak in STREAK_REWARDS:
        new_reward = STREAK_REWARDS[customer.current_streak]
    
    db.commit()
    
    return {
        "message": "Visit recorded",
        "current_streak": customer.current_streak,
        "longest_streak": customer.longest_streak,
        "streak_maintained": streak_maintained,
        "streak_broken": streak_broken,
        "new_reward": new_reward,
        "next_reward_at": get_next_reward_milestone(customer.current_streak)
    }


def get_next_reward_milestone(current_streak: int) -> dict:
    """Get the next streak milestone"""
    for milestone in sorted(STREAK_REWARDS.keys()):
        if milestone > current_streak:
            return {
                "streak_needed": milestone,
                "visits_until": milestone - current_streak,
                "reward": STREAK_REWARDS[milestone]["description"]
            }
    return None


@router.get("/{customer_id}/streak")
def get_customer_streak(customer_id: int, db: Session = Depends(get_db)):
    """Get customer's current streak status"""
    customer = db.query(Customer).filter(Customer.id == customer_id).first()
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    
    today = datetime.now().date()
    streak_at_risk = False
    days_until_expires = None
    
    if customer.last_visit_date:
        last_visit = customer.last_visit_date.date() if isinstance(customer.last_visit_date, datetime) else customer.last_visit_date
        days_since = (today - last_visit).days
        days_until_expires = 35 - days_since
        streak_at_risk = days_until_expires <= 7
    
    return {
        "customer_id": customer_id,
        "customer_name": customer.name,
        "current_streak": customer.current_streak or 0,
        "longest_streak": customer.longest_streak or 0,
        "last_visit": customer.last_visit_date.isoformat() if customer.last_visit_date else None,
        "streak_at_risk": streak_at_risk,
        "days_until_streak_expires": max(0, days_until_expires) if days_until_expires else None,
        "next_reward": get_next_reward_milestone(customer.current_streak or 0),
        "available_rewards": [
            {"milestone": m, **r}
            for m, r in STREAK_REWARDS.items()
            if m <= (customer.current_streak or 0)
        ]
    }


@router.get("/streaks/leaderboard")
def get_streak_leaderboard(limit: int = 10, db: Session = Depends(get_db)):
    """Get customers with highest streaks"""
    customers = db.query(Customer).filter(
        Customer.current_streak > 0
    ).order_by(Customer.current_streak.desc()).limit(limit).all()
    
    return [
        {
            "rank": i + 1,
            "customer_id": c.id,
            "customer_name": c.name,
            "current_streak": c.current_streak,
            "longest_streak": c.longest_streak,
            "badge": "🔥" if c.current_streak >= 10 else ("⚡" if c.current_streak >= 5 else "")
        }
        for i, c in enumerate(customers)
    ]


@router.get("/streaks/at-risk")
def get_at_risk_streaks(db: Session = Depends(get_db)):
    """Get customers whose streaks are about to expire"""
    today = datetime.now()
    cutoff_warning = today - timedelta(days=28)  # 7 days warning
    cutoff_danger = today - timedelta(days=32)  # 3 days warning
    
    customers = db.query(Customer).filter(
        Customer.current_streak >= 3,  # Only care about meaningful streaks
        Customer.last_visit_date <= cutoff_warning
    ).order_by(Customer.last_visit_date).all()
    
    at_risk = []
    for c in customers:
        if c.last_visit_date:
            days_since = (today.date() - c.last_visit_date.date()).days
            days_left = 35 - days_since
            
            at_risk.append({
                "customer_id": c.id,
                "customer_name": c.name,
                "phone": c.phone,
                "current_streak": c.current_streak,
                "days_since_visit": days_since,
                "days_until_expires": max(0, days_left),
                "urgency": "critical" if days_left <= 3 else "warning"
            })
    
    return at_risk
