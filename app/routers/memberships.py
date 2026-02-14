from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime, timedelta

from app.database import get_db
from app.models import MembershipPlan, CustomerMembership, Customer

router = APIRouter(prefix="/memberships", tags=["Memberships"])


class PlanCreate(BaseModel):
    name: str
    description: Optional[str] = None
    monthly_price: float
    haircuts_included: int = 0  # 0 = unlimited
    discount_percent: int = 0
    priority_booking: bool = False
    free_products_monthly: int = 0


class PlanUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    monthly_price: Optional[float] = None
    haircuts_included: Optional[int] = None
    discount_percent: Optional[int] = None
    priority_booking: Optional[bool] = None
    is_active: Optional[bool] = None


class MembershipSubscribe(BaseModel):
    customer_id: int
    plan_id: int


# ===== PLANS MANAGEMENT =====

@router.get("/plans")
def list_plans(include_inactive: bool = False, db: Session = Depends(get_db)):
    """Get all membership plans"""
    query = db.query(MembershipPlan)
    if not include_inactive:
        query = query.filter(MembershipPlan.is_active == True)
    
    plans = query.order_by(MembershipPlan.monthly_price).all()
    
    return [
        {
            "id": p.id,
            "name": p.name,
            "description": p.description,
            "monthly_price": p.monthly_price,
            "haircuts_included": p.haircuts_included if p.haircuts_included > 0 else "Unlimited",
            "discount_percent": p.discount_percent,
            "priority_booking": p.priority_booking,
            "free_products_monthly": p.free_products_monthly,
            "is_active": p.is_active
        }
        for p in plans
    ]


@router.post("/plans")
def create_plan(plan: PlanCreate, db: Session = Depends(get_db)):
    """Create a new membership plan"""
    db_plan = MembershipPlan(**plan.model_dump())
    db.add(db_plan)
    db.commit()
    db.refresh(db_plan)
    
    return {"message": "Plan created", "id": db_plan.id}


@router.patch("/plans/{plan_id}")
def update_plan(plan_id: int, update: PlanUpdate, db: Session = Depends(get_db)):
    """Update a membership plan"""
    plan = db.query(MembershipPlan).filter(MembershipPlan.id == plan_id).first()
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found")
    
    update_data = update.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(plan, field, value)
    
    db.commit()
    return {"message": "Plan updated"}


# ===== CUSTOMER MEMBERSHIPS =====

@router.post("/subscribe")
def subscribe_customer(data: MembershipSubscribe, db: Session = Depends(get_db)):
    """Subscribe a customer to a membership plan"""
    customer = db.query(Customer).filter(Customer.id == data.customer_id).first()
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    
    plan = db.query(MembershipPlan).filter(MembershipPlan.id == data.plan_id).first()
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found")
    
    # Check if customer already has active membership
    existing = db.query(CustomerMembership).filter(
        CustomerMembership.customer_id == data.customer_id,
        CustomerMembership.status == "active"
    ).first()
    
    if existing:
        raise HTTPException(status_code=400, detail="Customer already has an active membership")
    
    # Create membership
    now = datetime.utcnow()
    membership = CustomerMembership(
        customer_id=data.customer_id,
        plan_id=data.plan_id,
        start_date=now,
        next_billing_date=now + timedelta(days=30),
        last_reset_date=now
    )
    db.add(membership)
    db.commit()
    db.refresh(membership)
    
    return {
        "message": "Membership activated",
        "membership_id": membership.id,
        "plan_name": plan.name,
        "next_billing_date": membership.next_billing_date
    }


@router.get("/customer/{customer_id}")
def get_customer_membership(customer_id: int, db: Session = Depends(get_db)):
    """Get customer's membership status"""
    membership = db.query(CustomerMembership).filter(
        CustomerMembership.customer_id == customer_id,
        CustomerMembership.status == "active"
    ).first()
    
    if not membership:
        return {"has_membership": False}
    
    plan = db.query(MembershipPlan).filter(MembershipPlan.id == membership.plan_id).first()
    
    # Check if needs monthly reset
    now = datetime.utcnow()
    if membership.last_reset_date:
        days_since_reset = (now - membership.last_reset_date).days
        if days_since_reset >= 30:
            membership.haircuts_used_this_month = 0
            membership.last_reset_date = now
            db.commit()
    
    haircuts_remaining = None
    if plan.haircuts_included > 0:
        haircuts_remaining = plan.haircuts_included - membership.haircuts_used_this_month
    
    return {
        "has_membership": True,
        "membership_id": membership.id,
        "plan_name": plan.name,
        "status": membership.status,
        "start_date": membership.start_date,
        "next_billing_date": membership.next_billing_date,
        "benefits": {
            "haircuts_included": plan.haircuts_included if plan.haircuts_included > 0 else "Unlimited",
            "haircuts_used_this_month": membership.haircuts_used_this_month,
            "haircuts_remaining": haircuts_remaining if haircuts_remaining is not None else "Unlimited",
            "discount_percent": plan.discount_percent,
            "priority_booking": plan.priority_booking
        }
    }


@router.post("/customer/{customer_id}/use-haircut")
def use_membership_haircut(customer_id: int, db: Session = Depends(get_db)):
    """Record usage of a membership haircut"""
    membership = db.query(CustomerMembership).filter(
        CustomerMembership.customer_id == customer_id,
        CustomerMembership.status == "active"
    ).first()
    
    if not membership:
        raise HTTPException(status_code=404, detail="No active membership")
    
    plan = db.query(MembershipPlan).filter(MembershipPlan.id == membership.plan_id).first()
    
    # Check if haircuts are available
    if plan.haircuts_included > 0:
        if membership.haircuts_used_this_month >= plan.haircuts_included:
            return {
                "success": False,
                "message": "No more included haircuts this month",
                "pay_regular_price": True,
                "discount_percent": plan.discount_percent
            }
    
    membership.haircuts_used_this_month += 1
    db.commit()
    
    remaining = None
    if plan.haircuts_included > 0:
        remaining = plan.haircuts_included - membership.haircuts_used_this_month
    
    return {
        "success": True,
        "message": "Membership haircut used",
        "haircuts_remaining": remaining if remaining is not None else "Unlimited"
    }


@router.post("/customer/{customer_id}/pause")
def pause_membership(customer_id: int, db: Session = Depends(get_db)):
    """Pause a membership"""
    membership = db.query(CustomerMembership).filter(
        CustomerMembership.customer_id == customer_id,
        CustomerMembership.status == "active"
    ).first()
    
    if not membership:
        raise HTTPException(status_code=404, detail="No active membership")
    
    membership.status = "paused"
    db.commit()
    
    return {"message": "Membership paused"}


@router.post("/customer/{customer_id}/resume")
def resume_membership(customer_id: int, db: Session = Depends(get_db)):
    """Resume a paused membership"""
    membership = db.query(CustomerMembership).filter(
        CustomerMembership.customer_id == customer_id,
        CustomerMembership.status == "paused"
    ).first()
    
    if not membership:
        raise HTTPException(status_code=404, detail="No paused membership found")
    
    membership.status = "active"
    membership.next_billing_date = datetime.utcnow() + timedelta(days=30)
    db.commit()
    
    return {"message": "Membership resumed", "next_billing_date": membership.next_billing_date}


@router.post("/customer/{customer_id}/cancel")
def cancel_membership(customer_id: int, db: Session = Depends(get_db)):
    """Cancel a membership"""
    membership = db.query(CustomerMembership).filter(
        CustomerMembership.customer_id == customer_id,
        CustomerMembership.status.in_(["active", "paused"])
    ).first()
    
    if not membership:
        raise HTTPException(status_code=404, detail="No active/paused membership found")
    
    membership.status = "cancelled"
    membership.cancelled_at = datetime.utcnow()
    db.commit()
    
    return {"message": "Membership cancelled"}


@router.get("/active")
def list_active_memberships(db: Session = Depends(get_db)):
    """Get all active memberships"""
    memberships = db.query(CustomerMembership).filter(
        CustomerMembership.status == "active"
    ).all()
    
    result = []
    for m in memberships:
        customer = db.query(Customer).filter(Customer.id == m.customer_id).first()
        plan = db.query(MembershipPlan).filter(MembershipPlan.id == m.plan_id).first()
        
        result.append({
            "membership_id": m.id,
            "customer_id": m.customer_id,
            "customer_name": customer.name if customer else "Unknown",
            "customer_phone": customer.phone if customer else None,
            "plan_name": plan.name if plan else "Unknown",
            "monthly_price": plan.monthly_price if plan else 0,
            "start_date": m.start_date,
            "next_billing_date": m.next_billing_date
        })
    
    return result


@router.get("/revenue")
def get_membership_revenue(db: Session = Depends(get_db)):
    """Get monthly recurring revenue from memberships"""
    active_memberships = db.query(CustomerMembership).filter(
        CustomerMembership.status == "active"
    ).all()
    
    total_mrr = 0
    plan_breakdown = {}
    
    for m in active_memberships:
        plan = db.query(MembershipPlan).filter(MembershipPlan.id == m.plan_id).first()
        if plan:
            total_mrr += plan.monthly_price
            plan_name = plan.name
            if plan_name not in plan_breakdown:
                plan_breakdown[plan_name] = {"count": 0, "revenue": 0}
            plan_breakdown[plan_name]["count"] += 1
            plan_breakdown[plan_name]["revenue"] += plan.monthly_price
    
    return {
        "total_active_members": len(active_memberships),
        "monthly_recurring_revenue": round(total_mrr, 2),
        "annual_projected_revenue": round(total_mrr * 12, 2),
        "plan_breakdown": plan_breakdown
    }
