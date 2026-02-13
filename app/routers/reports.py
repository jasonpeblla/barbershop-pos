from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import datetime, date, timedelta
from typing import Optional

from app.database import get_db
from app.models import Order, Payment, Barber, ServiceType, OrderService, Customer

router = APIRouter(prefix="/reports", tags=["reports"])


@router.get("/daily")
def daily_report(report_date: Optional[str] = None, db: Session = Depends(get_db)):
    """Get daily sales and stats"""
    if report_date:
        target_date = datetime.strptime(report_date, "%Y-%m-%d").date()
    else:
        target_date = date.today()
    
    orders = db.query(Order).filter(
        func.date(Order.created_at) == target_date,
        Order.status == "completed"
    ).all()
    
    total_revenue = sum(o.subtotal for o in orders)
    total_tips = sum(o.tip for o in orders)
    total_tax = sum(o.tax for o in orders)
    num_customers = len(orders)
    avg_ticket = total_revenue / num_customers if num_customers > 0 else 0
    
    # Revenue by payment method
    payments = db.query(Payment).filter(
        func.date(Payment.created_at) == target_date
    ).all()
    
    by_method = {}
    for p in payments:
        by_method[p.method] = by_method.get(p.method, 0) + p.amount
    
    # Revenue by barber
    by_barber = {}
    for o in orders:
        if o.barber_id:
            barber = db.query(Barber).filter(Barber.id == o.barber_id).first()
            name = barber.name if barber else "Unknown"
            if name not in by_barber:
                by_barber[name] = {"revenue": 0, "tips": 0, "customers": 0}
            by_barber[name]["revenue"] += o.subtotal
            by_barber[name]["tips"] += o.tip
            by_barber[name]["customers"] += 1
    
    return {
        "date": target_date.isoformat(),
        "summary": {
            "total_revenue": round(total_revenue, 2),
            "total_tips": round(total_tips, 2),
            "total_tax": round(total_tax, 2),
            "total_collected": round(total_revenue + total_tips + total_tax, 2),
            "num_customers": num_customers,
            "average_ticket": round(avg_ticket, 2)
        },
        "by_payment_method": by_method,
        "by_barber": by_barber
    }


@router.get("/earnings")
def earnings_report(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """Get commission/earnings report for all barbers"""
    if start_date:
        start = datetime.strptime(start_date, "%Y-%m-%d").date()
    else:
        start = date.today().replace(day=1)
    
    if end_date:
        end = datetime.strptime(end_date, "%Y-%m-%d").date()
    else:
        end = date.today()
    
    barbers = db.query(Barber).filter(Barber.is_active == True).all()
    
    results = []
    totals = {
        "total_revenue": 0,
        "total_commission": 0,
        "total_tips": 0,
        "total_earnings": 0
    }
    
    for barber in barbers:
        orders = db.query(Order).filter(
            Order.barber_id == barber.id,
            Order.status == "completed",
            func.date(Order.completed_at) >= start,
            func.date(Order.completed_at) <= end
        ).all()
        
        revenue = sum(o.subtotal for o in orders)
        tips = sum(o.tip for o in orders)
        commission = revenue * barber.commission_rate
        earnings = commission + tips
        
        results.append({
            "barber_id": barber.id,
            "barber_name": barber.name,
            "commission_rate": barber.commission_rate,
            "total_services": len(orders),
            "total_revenue": round(revenue, 2),
            "commission_earned": round(commission, 2),
            "tips_earned": round(tips, 2),
            "total_earnings": round(earnings, 2)
        })
        
        totals["total_revenue"] += revenue
        totals["total_commission"] += commission
        totals["total_tips"] += tips
        totals["total_earnings"] += earnings
    
    return {
        "period_start": start.isoformat(),
        "period_end": end.isoformat(),
        "barbers": results,
        "totals": {k: round(v, 2) for k, v in totals.items()}
    }


@router.get("/services")
def services_report(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """Get report of service popularity and revenue"""
    if start_date:
        start = datetime.strptime(start_date, "%Y-%m-%d").date()
    else:
        start = date.today() - timedelta(days=30)
    
    if end_date:
        end = datetime.strptime(end_date, "%Y-%m-%d").date()
    else:
        end = date.today()
    
    # Get all order services in range
    order_services = db.query(OrderService).join(Order).filter(
        Order.status == "completed",
        func.date(Order.completed_at) >= start,
        func.date(Order.completed_at) <= end
    ).all()
    
    service_stats = {}
    for os in order_services:
        service = db.query(ServiceType).filter(ServiceType.id == os.service_type_id).first()
        if not service:
            continue
        
        if service.id not in service_stats:
            service_stats[service.id] = {
                "service_id": service.id,
                "service_name": service.name,
                "category": service.category,
                "count": 0,
                "revenue": 0
            }
        
        service_stats[service.id]["count"] += os.quantity
        service_stats[service.id]["revenue"] += os.unit_price * os.quantity
    
    # Sort by count
    sorted_services = sorted(service_stats.values(), key=lambda x: x["count"], reverse=True)
    
    return {
        "period_start": start.isoformat(),
        "period_end": end.isoformat(),
        "services": sorted_services,
        "total_services_rendered": sum(s["count"] for s in sorted_services),
        "total_revenue": round(sum(s["revenue"] for s in sorted_services), 2)
    }


@router.get("/customers/top")
def top_customers(limit: int = 10, db: Session = Depends(get_db)):
    """Get top customers by spending"""
    customers = db.query(Customer).all()
    
    customer_stats = []
    for customer in customers:
        orders = db.query(Order).filter(
            Order.customer_id == customer.id,
            Order.status == "completed"
        ).all()
        
        if not orders:
            continue
        
        total_spent = sum(o.total for o in orders)
        total_visits = len(orders)
        
        customer_stats.append({
            "customer_id": customer.id,
            "name": customer.name,
            "phone": customer.phone,
            "total_visits": total_visits,
            "total_spent": round(total_spent, 2),
            "average_ticket": round(total_spent / total_visits, 2)
        })
    
    # Sort by total spent
    sorted_customers = sorted(customer_stats, key=lambda x: x["total_spent"], reverse=True)
    
    return sorted_customers[:limit]
