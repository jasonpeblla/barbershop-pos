from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime

from app.database import get_db
from app.models import (
    Customer, Order, OrderService, ServiceType, Barber, 
    WalkInQueue, Payment, LoyaltyTransaction
)

router = APIRouter(prefix="/quick", tags=["Quick Actions"])


class QuickWalkIn(BaseModel):
    customer_name: str
    phone: Optional[str] = None
    service_id: int
    barber_id: Optional[int] = None
    notes: Optional[str] = None


class QuickCheckout(BaseModel):
    order_id: int
    payment_method: str = "card"
    tip_percent: float = 20.0


# ===== QUICK WALK-IN =====

@router.post("/walkin")
def quick_walkin(data: QuickWalkIn, db: Session = Depends(get_db)):
    """Quick add walk-in customer - creates queue entry and order in one step"""
    from sqlalchemy import func
    
    # Look up or create customer
    customer = None
    if data.phone:
        customer = db.query(Customer).filter(Customer.phone == data.phone).first()
        if not customer:
            customer = Customer(name=data.customer_name, phone=data.phone)
            db.add(customer)
            db.commit()
            db.refresh(customer)
    
    # Get service
    service = db.query(ServiceType).filter(ServiceType.id == data.service_id).first()
    if not service:
        raise HTTPException(status_code=404, detail="Service not found")
    
    # Get queue position
    max_pos = db.query(func.max(WalkInQueue.position)).filter(
        WalkInQueue.status.in_(["waiting", "called"])
    ).scalar() or 0
    
    # Calculate wait
    waiting_count = db.query(WalkInQueue).filter(WalkInQueue.status == "waiting").count()
    active_barbers = db.query(Barber).filter(Barber.is_available == True).count()
    estimated_wait = (waiting_count * 25) // max(active_barbers, 1)
    
    # Create queue entry
    queue_entry = WalkInQueue(
        customer_name=data.customer_name,
        customer_phone=data.phone,
        customer_id=customer.id if customer else None,
        requested_barber_id=data.barber_id,
        service_notes=data.notes or service.name,
        position=max_pos + 1,
        estimated_wait=estimated_wait
    )
    db.add(queue_entry)
    db.commit()
    db.refresh(queue_entry)
    
    return {
        "success": True,
        "queue_id": queue_entry.id,
        "position": queue_entry.position,
        "estimated_wait": estimated_wait,
        "customer_id": customer.id if customer else None,
        "service": service.name,
        "message": f"{data.customer_name} added to queue at position {queue_entry.position}"
    }


@router.post("/start-service/{queue_id}")
def quick_start_service(queue_id: int, barber_id: int, db: Session = Depends(get_db)):
    """Quick start service - creates order from queue entry"""
    queue_entry = db.query(WalkInQueue).filter(WalkInQueue.id == queue_id).first()
    if not queue_entry:
        raise HTTPException(status_code=404, detail="Queue entry not found")
    
    barber = db.query(Barber).filter(Barber.id == barber_id).first()
    if not barber:
        raise HTTPException(status_code=404, detail="Barber not found")
    
    # Parse service from notes or get default
    service = db.query(ServiceType).filter(ServiceType.name == "Regular Haircut").first()
    if not service:
        service = db.query(ServiceType).first()
    
    # Create order
    order = Order(
        customer_id=queue_entry.customer_id,
        barber_id=barber_id,
        status="in_progress",
        started_at=datetime.utcnow(),
        notes=queue_entry.service_notes
    )
    db.add(order)
    db.commit()
    db.refresh(order)
    
    # Add service
    order_service = OrderService(
        order_id=order.id,
        service_type_id=service.id,
        quantity=1,
        unit_price=service.base_price,
        notes=queue_entry.service_notes
    )
    db.add(order_service)
    
    # Update order totals
    order.subtotal = service.base_price
    order.tax = round(service.base_price * 0.0875, 2)  # 8.75% tax
    order.total = order.subtotal + order.tax
    
    # Update queue entry
    queue_entry.status = "in_service"
    
    db.commit()
    
    return {
        "success": True,
        "order_id": order.id,
        "customer_name": queue_entry.customer_name,
        "barber": barber.name,
        "service": service.name,
        "subtotal": order.subtotal,
        "tax": order.tax,
        "total": order.total
    }


@router.post("/checkout")
def quick_checkout(data: QuickCheckout, db: Session = Depends(get_db)):
    """Quick checkout - complete order with payment"""
    order = db.query(Order).filter(Order.id == data.order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    
    if order.status == "completed":
        raise HTTPException(status_code=400, detail="Order already completed")
    
    # Calculate tip
    tip_amount = round(order.subtotal * (data.tip_percent / 100), 2)
    
    # Create payment
    payment = Payment(
        order_id=order.id,
        amount=order.subtotal + order.tax,
        tip_amount=tip_amount,
        method=data.payment_method
    )
    db.add(payment)
    
    # Update order
    order.tip = tip_amount
    order.total = order.subtotal + order.tax + tip_amount
    order.status = "completed"
    order.completed_at = datetime.utcnow()
    
    # Award loyalty points
    if order.customer_id:
        customer = db.query(Customer).filter(Customer.id == order.customer_id).first()
        if customer:
            points = int(order.subtotal)  # 1 point per dollar
            customer.loyalty_points = (customer.loyalty_points or 0) + points
            customer.lifetime_points = (customer.lifetime_points or 0) + points
            customer.visit_count = (customer.visit_count or 0) + 1
            customer.total_spent = (customer.total_spent or 0) + order.total
            customer.last_visit_date = datetime.utcnow()
            
            # Log loyalty
            loyalty = LoyaltyTransaction(
                customer_id=customer.id,
                order_id=order.id,
                points=points,
                transaction_type="earned",
                description=f"Order #{order.id}"
            )
            db.add(loyalty)
    
    # Complete queue entry if exists
    queue_entry = db.query(WalkInQueue).filter(
        WalkInQueue.customer_id == order.customer_id,
        WalkInQueue.status == "in_service"
    ).first()
    if queue_entry:
        queue_entry.status = "completed"
        queue_entry.completed_time = datetime.utcnow()
    
    db.commit()
    
    return {
        "success": True,
        "order_id": order.id,
        "subtotal": order.subtotal,
        "tax": order.tax,
        "tip": tip_amount,
        "total": order.total,
        "payment_method": data.payment_method,
        "points_earned": int(order.subtotal) if order.customer_id else 0
    }


# ===== QUICK LOOKUPS =====

@router.get("/customer/{phone}")
def quick_customer_lookup(phone: str, db: Session = Depends(get_db)):
    """Quick customer lookup by phone"""
    customer = db.query(Customer).filter(Customer.phone.contains(phone)).first()
    
    if not customer:
        return {"found": False, "phone": phone}
    
    # Get last service
    last_order = db.query(Order).filter(
        Order.customer_id == customer.id,
        Order.status == "completed"
    ).order_by(Order.completed_at.desc()).first()
    
    last_service = None
    if last_order and last_order.services:
        os = last_order.services[0]
        service = db.query(ServiceType).filter(ServiceType.id == os.service_type_id).first()
        if service:
            last_service = service.name
    
    return {
        "found": True,
        "id": customer.id,
        "name": customer.name,
        "phone": customer.phone,
        "loyalty_points": customer.loyalty_points or 0,
        "vip_tier": customer.vip_tier or "bronze",
        "visit_count": customer.visit_count or 0,
        "last_service": last_service,
        "preferred_barber_id": customer.preferred_barber_id,
        "notes": customer.notes
    }


@router.get("/today")
def get_today_summary(db: Session = Depends(get_db)):
    """Quick summary of today's activity"""
    from sqlalchemy import func
    
    today = datetime.now().date()
    
    # Orders
    orders = db.query(Order).filter(
        func.date(Order.created_at) == today
    ).all()
    
    completed = [o for o in orders if o.status == "completed"]
    in_progress = [o for o in orders if o.status == "in_progress"]
    
    # Queue
    waiting = db.query(WalkInQueue).filter(
        WalkInQueue.status == "waiting"
    ).count()
    
    # Barbers
    active_barbers = db.query(Barber).filter(Barber.is_available == True).count()
    
    return {
        "date": today.isoformat(),
        "orders": {
            "completed": len(completed),
            "in_progress": len(in_progress),
            "total_revenue": round(sum(o.subtotal for o in completed), 2),
            "total_tips": round(sum(o.tip or 0 for o in completed), 2)
        },
        "queue": {
            "waiting": waiting,
            "estimated_wait": waiting * 25 // max(active_barbers, 1)
        },
        "barbers_active": active_barbers
    }


@router.get("/services/popular")
def get_popular_services(db: Session = Depends(get_db)):
    """Get most popular services for quick selection"""
    services = db.query(ServiceType).filter(
        ServiceType.is_active == True,
        ServiceType.category.in_(["haircut", "combo"])
    ).order_by(ServiceType.base_price).limit(6).all()
    
    return [
        {
            "id": s.id,
            "name": s.name,
            "price": s.base_price,
            "duration": s.duration_minutes
        }
        for s in services
    ]
