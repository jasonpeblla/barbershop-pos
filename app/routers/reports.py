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


@router.get("/barber/{barber_id}")
def barber_performance(barber_id: int, days: int = 7, db: Session = Depends(get_db)):
    """Get detailed performance stats for a specific barber"""
    barber = db.query(Barber).filter(Barber.id == barber_id).first()
    if not barber:
        return {"error": "Barber not found"}
    
    end_date = date.today()
    start_date = end_date - timedelta(days=days)
    
    orders = db.query(Order).filter(
        Order.barber_id == barber_id,
        Order.status == "completed",
        func.date(Order.completed_at) >= start_date,
        func.date(Order.completed_at) <= end_date
    ).all()
    
    # Daily breakdown
    daily_stats = {}
    for o in orders:
        day = o.completed_at.date().isoformat() if o.completed_at else o.created_at.date().isoformat()
        if day not in daily_stats:
            daily_stats[day] = {"customers": 0, "revenue": 0, "tips": 0, "services": []}
        daily_stats[day]["customers"] += 1
        daily_stats[day]["revenue"] += o.subtotal
        daily_stats[day]["tips"] += o.tip
    
    # Hourly breakdown for today
    today_orders = [o for o in orders if o.completed_at and o.completed_at.date() == date.today()]
    hourly_stats = {}
    for o in today_orders:
        hour = o.completed_at.hour
        hour_label = f"{hour:02d}:00"
        if hour_label not in hourly_stats:
            hourly_stats[hour_label] = {"customers": 0, "revenue": 0}
        hourly_stats[hour_label]["customers"] += 1
        hourly_stats[hour_label]["revenue"] += o.subtotal
    
    # Service breakdown
    service_counts = {}
    for o in orders:
        for os in o.services:
            service = db.query(ServiceType).filter(ServiceType.id == os.service_type_id).first()
            if service:
                if service.name not in service_counts:
                    service_counts[service.name] = 0
                service_counts[service.name] += os.quantity
    
    total_revenue = sum(o.subtotal for o in orders)
    total_tips = sum(o.tip for o in orders)
    commission = total_revenue * barber.commission_rate
    
    return {
        "barber": {
            "id": barber.id,
            "name": barber.name,
            "commission_rate": barber.commission_rate,
            "specialties": barber.specialties
        },
        "period": {
            "start": start_date.isoformat(),
            "end": end_date.isoformat(),
            "days": days
        },
        "summary": {
            "total_customers": len(orders),
            "total_revenue": round(total_revenue, 2),
            "total_tips": round(total_tips, 2),
            "commission_earned": round(commission, 2),
            "total_earnings": round(commission + total_tips, 2),
            "avg_per_customer": round(total_revenue / len(orders), 2) if orders else 0,
            "avg_tip": round(total_tips / len(orders), 2) if orders else 0
        },
        "daily_breakdown": dict(sorted(daily_stats.items())),
        "hourly_today": dict(sorted(hourly_stats.items())),
        "top_services": dict(sorted(service_counts.items(), key=lambda x: x[1], reverse=True)[:5])
    }


@router.get("/leaderboard")
def barber_leaderboard(period: str = "today", db: Session = Depends(get_db)):
    """Get barber leaderboard for gamification"""
    if period == "today":
        start_date = date.today()
        end_date = date.today()
    elif period == "week":
        end_date = date.today()
        start_date = end_date - timedelta(days=7)
    elif period == "month":
        end_date = date.today()
        start_date = end_date.replace(day=1)
    else:
        start_date = date.today()
        end_date = date.today()
    
    barbers = db.query(Barber).filter(Barber.is_active == True).all()
    
    leaderboard = []
    for barber in barbers:
        orders = db.query(Order).filter(
            Order.barber_id == barber.id,
            Order.status == "completed",
            func.date(Order.completed_at) >= start_date,
            func.date(Order.completed_at) <= end_date
        ).all()
        
        revenue = sum(o.subtotal for o in orders)
        tips = sum(o.tip for o in orders)
        customers = len(orders)
        
        leaderboard.append({
            "barber_id": barber.id,
            "barber_name": barber.name,
            "customers": customers,
            "revenue": round(revenue, 2),
            "tips": round(tips, 2),
            "avg_tip_percent": round((tips / revenue * 100) if revenue > 0 else 0, 1)
        })
    
    # Sort by revenue
    leaderboard.sort(key=lambda x: x["revenue"], reverse=True)
    
    # Add ranking
    for i, entry in enumerate(leaderboard):
        entry["rank"] = i + 1
        if i == 0:
            entry["badge"] = "🥇"
        elif i == 1:
            entry["badge"] = "🥈"
        elif i == 2:
            entry["badge"] = "🥉"
        else:
            entry["badge"] = ""
    
    return {
        "period": period,
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "leaderboard": leaderboard
    }
