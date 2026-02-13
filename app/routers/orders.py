from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional
from pydantic import BaseModel
from datetime import datetime

from app.database import get_db
from app.models import Order, OrderService, ServiceType, Customer, Barber

router = APIRouter(prefix="/orders", tags=["orders"])

TAX_RATE = 0.0875


class OrderServiceCreate(BaseModel):
    service_type_id: int
    quantity: int = 1
    notes: Optional[str] = None


class OrderCreate(BaseModel):
    customer_id: Optional[int] = None
    barber_id: Optional[int] = None
    services: List[OrderServiceCreate]
    notes: Optional[str] = None


class OrderResponse(BaseModel):
    id: int
    customer_id: Optional[int]
    customer_name: Optional[str] = None
    barber_id: Optional[int]
    barber_name: Optional[str] = None
    status: str
    subtotal: float
    tax: float
    tip: float
    total: float
    notes: Optional[str]
    created_at: datetime
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    services: list

    class Config:
        from_attributes = True


@router.get("/", response_model=List[OrderResponse])
def list_orders(
    status: Optional[str] = None,
    barber_id: Optional[int] = None,
    limit: int = 50,
    db: Session = Depends(get_db)
):
    query = db.query(Order)
    if status:
        query = query.filter(Order.status == status)
    if barber_id:
        query = query.filter(Order.barber_id == barber_id)
    
    orders = query.order_by(Order.created_at.desc()).limit(limit).all()
    
    result = []
    for order in orders:
        customer_name = None
        if order.customer:
            customer_name = order.customer.name
        barber_name = None
        if order.barber:
            barber_name = order.barber.name
        
        services = []
        for os in order.services:
            svc = db.query(ServiceType).filter(ServiceType.id == os.service_type_id).first()
            services.append({
                "id": os.id,
                "service_type_id": os.service_type_id,
                "service_name": svc.name if svc else "Unknown",
                "quantity": os.quantity,
                "unit_price": os.unit_price,
                "notes": os.notes
            })
        
        result.append({
            **OrderResponse.model_validate(order).model_dump(),
            "customer_name": customer_name,
            "barber_name": barber_name,
            "services": services
        })
    
    return result


@router.get("/{order_id}")
def get_order(order_id: int, db: Session = Depends(get_db)):
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    
    customer_name = None
    if order.customer:
        customer_name = order.customer.name
    barber_name = None
    if order.barber:
        barber_name = order.barber.name
    
    services = []
    for os in order.services:
        svc = db.query(ServiceType).filter(ServiceType.id == os.service_type_id).first()
        services.append({
            "id": os.id,
            "service_type_id": os.service_type_id,
            "service_name": svc.name if svc else "Unknown",
            "quantity": os.quantity,
            "unit_price": os.unit_price,
            "notes": os.notes
        })
    
    return {
        "id": order.id,
        "customer_id": order.customer_id,
        "customer_name": customer_name,
        "barber_id": order.barber_id,
        "barber_name": barber_name,
        "status": order.status,
        "subtotal": order.subtotal,
        "tax": order.tax,
        "tip": order.tip,
        "total": order.total,
        "notes": order.notes,
        "created_at": order.created_at,
        "started_at": order.started_at,
        "completed_at": order.completed_at,
        "services": services
    }


@router.post("/")
def create_order(order_data: OrderCreate, db: Session = Depends(get_db)):
    # Calculate subtotal
    subtotal = 0.0
    service_items = []
    
    for svc in order_data.services:
        service = db.query(ServiceType).filter(ServiceType.id == svc.service_type_id).first()
        if not service:
            raise HTTPException(status_code=400, detail=f"Service {svc.service_type_id} not found")
        
        unit_price = service.base_price
        subtotal += unit_price * svc.quantity
        service_items.append({
            "service_type_id": svc.service_type_id,
            "quantity": svc.quantity,
            "unit_price": unit_price,
            "notes": svc.notes
        })
    
    tax = round(subtotal * TAX_RATE, 2)
    total = round(subtotal + tax, 2)
    
    # Create order
    order = Order(
        customer_id=order_data.customer_id,
        barber_id=order_data.barber_id,
        status="waiting" if not order_data.barber_id else "in_progress",
        subtotal=round(subtotal, 2),
        tax=tax,
        total=total,
        notes=order_data.notes,
        started_at=datetime.utcnow() if order_data.barber_id else None
    )
    db.add(order)
    db.flush()
    
    # Add services
    for item in service_items:
        os = OrderService(
            order_id=order.id,
            **item
        )
        db.add(os)
    
    db.commit()
    db.refresh(order)
    
    return get_order(order.id, db)


@router.patch("/{order_id}/status")
def update_order_status(order_id: int, status: str, db: Session = Depends(get_db)):
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    
    valid_statuses = ["waiting", "in_progress", "completed", "cancelled"]
    if status not in valid_statuses:
        raise HTTPException(status_code=400, detail=f"Invalid status. Must be one of: {valid_statuses}")
    
    order.status = status
    
    if status == "in_progress" and not order.started_at:
        order.started_at = datetime.utcnow()
    elif status == "completed":
        order.completed_at = datetime.utcnow()
    
    db.commit()
    return {"message": "Status updated", "status": order.status}


@router.patch("/{order_id}/assign")
def assign_barber(order_id: int, barber_id: int, db: Session = Depends(get_db)):
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    
    barber = db.query(Barber).filter(Barber.id == barber_id).first()
    if not barber:
        raise HTTPException(status_code=404, detail="Barber not found")
    
    order.barber_id = barber_id
    if order.status == "waiting":
        order.status = "in_progress"
        order.started_at = datetime.utcnow()
    
    db.commit()
    return {"message": "Barber assigned", "barber_id": barber_id}


@router.get("/{order_id}/receipt")
def get_receipt(order_id: int, db: Session = Depends(get_db)):
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    
    customer_name = "Walk-in"
    customer_phone = ""
    if order.customer:
        customer_name = order.customer.name
        customer_phone = order.customer.phone
    
    barber_name = "Any"
    if order.barber:
        barber_name = order.barber.name
    
    services = []
    for os in order.services:
        svc = db.query(ServiceType).filter(ServiceType.id == os.service_type_id).first()
        services.append({
            "name": svc.name if svc else "Unknown",
            "quantity": os.quantity,
            "unit_price": os.unit_price,
            "total": os.unit_price * os.quantity
        })
    
    return {
        "shop_name": "Classic Cuts Barbershop",
        "shop_address": "123 Main Street",
        "shop_phone": "(555) 123-4567",
        "order_id": order.id,
        "date": (order.completed_at or order.created_at).strftime("%Y-%m-%d %H:%M"),
        "customer_name": customer_name,
        "customer_phone": customer_phone,
        "barber": barber_name,
        "services": services,
        "subtotal": order.subtotal,
        "tax": order.tax,
        "tax_rate": "8.75%",
        "tip": order.tip,
        "total": order.total,
        "thank_you_message": "Thanks for visiting! See you next time!"
    }
