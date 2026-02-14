from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import datetime, date, timedelta

from app.database import get_db
from app.models import (
    Order, Customer, Barber, WalkInQueue, Appointment, 
    CustomerMembership, Product, ServiceType
)

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])


@router.get("/")
def get_dashboard(db: Session = Depends(get_db)):
    """Get complete dashboard overview"""
    today = date.today()
    now = datetime.now()
    
    # Today's orders
    today_orders = db.query(Order).filter(
        func.date(Order.created_at) == today
    ).all()
    
    completed_today = [o for o in today_orders if o.status == "completed"]
    in_progress = [o for o in today_orders if o.status == "in_progress"]
    
    # Revenue
    today_revenue = sum(o.subtotal for o in completed_today)
    today_tips = sum(o.tip or 0 for o in completed_today)
    
    # Queue status
    waiting = db.query(WalkInQueue).filter(WalkInQueue.status == "waiting").count()
    active_barbers = db.query(Barber).filter(Barber.is_available == True).count()
    
    # Appointments today
    appointments_today = db.query(Appointment).filter(
        func.date(Appointment.scheduled_time) == today,
        Appointment.status.in_(["scheduled", "confirmed"])
    ).count()
    
    # Weekly comparison
    week_ago = today - timedelta(days=7)
    last_week_same_day = db.query(Order).filter(
        func.date(Order.created_at) == week_ago,
        Order.status == "completed"
    ).all()
    last_week_revenue = sum(o.subtotal for o in last_week_same_day)
    
    revenue_change = ((today_revenue - last_week_revenue) / last_week_revenue * 100) if last_week_revenue > 0 else 0
    
    return {
        "timestamp": now.isoformat(),
        "today": {
            "date": today.isoformat(),
            "day_of_week": today.strftime("%A"),
            "services_completed": len(completed_today),
            "services_in_progress": len(in_progress),
            "revenue": round(today_revenue, 2),
            "tips": round(today_tips, 2),
            "total_collected": round(today_revenue + today_tips, 2),
            "vs_last_week": {
                "last_week_revenue": round(last_week_revenue, 2),
                "change_percent": round(revenue_change, 1),
                "trending": "up" if revenue_change > 0 else ("down" if revenue_change < 0 else "same")
            }
        },
        "queue": {
            "waiting": waiting,
            "estimated_wait_minutes": waiting * 25 // max(active_barbers, 1),
            "active_barbers": active_barbers
        },
        "appointments": {
            "remaining_today": appointments_today
        }
    }


@router.get("/insights")
def get_business_insights(db: Session = Depends(get_db)):
    """Get actionable business insights"""
    today = date.today()
    insights = []
    
    # Check for low-performing day
    yesterday = today - timedelta(days=1)
    yesterday_orders = db.query(Order).filter(
        func.date(Order.created_at) == yesterday,
        Order.status == "completed"
    ).all()
    
    avg_daily = db.query(func.count(Order.id)).filter(
        Order.status == "completed",
        func.date(Order.created_at) >= today - timedelta(days=30)
    ).scalar() / 30
    
    if len(yesterday_orders) < avg_daily * 0.7:
        insights.append({
            "type": "warning",
            "title": "Slow Day Yesterday",
            "message": f"Only {len(yesterday_orders)} services vs {avg_daily:.0f} daily average",
            "action": "Consider running a promo or reaching out to regular customers"
        })
    
    # Check for at-risk streaks
    cutoff = datetime.now() - timedelta(days=28)
    at_risk = db.query(Customer).filter(
        Customer.current_streak >= 5,
        Customer.last_visit_date <= cutoff
    ).count()
    
    if at_risk > 0:
        insights.append({
            "type": "alert",
            "title": f"{at_risk} Loyal Customers at Risk",
            "message": "Customers with 5+ visit streaks haven't visited in 4 weeks",
            "action": "Send reminder notifications"
        })
    
    # Check low inventory
    low_stock = db.query(Product).filter(
        Product.is_active == True,
        Product.stock_quantity <= Product.low_stock_threshold
    ).count()
    
    if low_stock > 0:
        insights.append({
            "type": "info",
            "title": f"{low_stock} Products Low on Stock",
            "message": "Some retail products need restocking",
            "action": "Review inventory and place orders"
        })
    
    # Check upcoming appointments
    upcoming = db.query(Appointment).filter(
        func.date(Appointment.scheduled_time) == today,
        Appointment.status == "scheduled"
    ).count()
    
    if upcoming > 0:
        insights.append({
            "type": "reminder",
            "title": f"{upcoming} Unconfirmed Appointments Today",
            "message": "Some appointments haven't been confirmed",
            "action": "Send confirmation reminders"
        })
    
    # Check top performer
    week_start = today - timedelta(days=7)
    barbers = db.query(Barber).filter(Barber.is_active == True).all()
    
    top_barber = None
    top_revenue = 0
    for barber in barbers:
        revenue = db.query(func.sum(Order.subtotal)).filter(
            Order.barber_id == barber.id,
            Order.status == "completed",
            func.date(Order.completed_at) >= week_start
        ).scalar() or 0
        
        if revenue > top_revenue:
            top_revenue = revenue
            top_barber = barber.name
    
    if top_barber:
        insights.append({
            "type": "success",
            "title": f"Top Performer: {top_barber}",
            "message": f"${top_revenue:.2f} in revenue this week",
            "action": "Recognize their performance"
        })
    
    return {
        "generated_at": datetime.now().isoformat(),
        "insights": insights,
        "insight_count": len(insights)
    }


@router.get("/kpis")
def get_kpis(db: Session = Depends(get_db)):
    """Get key performance indicators"""
    today = date.today()
    month_start = today.replace(day=1)
    last_month_start = (month_start - timedelta(days=1)).replace(day=1)
    
    # This month's data
    this_month_orders = db.query(Order).filter(
        func.date(Order.created_at) >= month_start,
        Order.status == "completed"
    ).all()
    
    this_month_revenue = sum(o.subtotal for o in this_month_orders)
    this_month_services = len(this_month_orders)
    
    # Last month's data
    last_month_orders = db.query(Order).filter(
        func.date(Order.created_at) >= last_month_start,
        func.date(Order.created_at) < month_start,
        Order.status == "completed"
    ).all()
    
    last_month_revenue = sum(o.subtotal for o in last_month_orders)
    last_month_services = len(last_month_orders)
    
    # Customers
    new_customers = db.query(Customer).filter(
        func.date(Customer.created_at) >= month_start
    ).count()
    
    total_customers = db.query(Customer).count()
    
    # Retention (customers who visited this month and last month)
    this_month_customer_ids = set(o.customer_id for o in this_month_orders if o.customer_id)
    last_month_customer_ids = set(o.customer_id for o in last_month_orders if o.customer_id)
    returning = len(this_month_customer_ids & last_month_customer_ids)
    retention_rate = (returning / len(last_month_customer_ids) * 100) if last_month_customer_ids else 0
    
    # Memberships
    active_memberships = db.query(CustomerMembership).filter(
        CustomerMembership.status == "active"
    ).count()
    
    return {
        "period": {
            "current_month": month_start.strftime("%B %Y"),
            "days_in_month": today.day
        },
        "revenue": {
            "this_month": round(this_month_revenue, 2),
            "last_month": round(last_month_revenue, 2),
            "change_percent": round((this_month_revenue - last_month_revenue) / last_month_revenue * 100, 1) if last_month_revenue > 0 else 0
        },
        "services": {
            "this_month": this_month_services,
            "last_month": last_month_services,
            "avg_per_day": round(this_month_services / today.day, 1)
        },
        "customers": {
            "total": total_customers,
            "new_this_month": new_customers,
            "retention_rate": round(retention_rate, 1),
            "active_memberships": active_memberships
        },
        "averages": {
            "ticket_size": round(this_month_revenue / this_month_services, 2) if this_month_services > 0 else 0,
            "daily_revenue": round(this_month_revenue / today.day, 2)
        }
    }


@router.get("/live")
def get_live_status(db: Session = Depends(get_db)):
    """Get real-time shop status"""
    now = datetime.now()
    
    # Current queue
    queue = db.query(WalkInQueue).filter(
        WalkInQueue.status.in_(["waiting", "called"])
    ).order_by(WalkInQueue.position).all()
    
    # Active services
    in_progress = db.query(Order).filter(
        Order.status == "in_progress"
    ).all()
    
    # Barber status
    barbers = db.query(Barber).filter(Barber.is_active == True).all()
    barber_status = []
    
    for barber in barbers:
        current_order = next((o for o in in_progress if o.barber_id == barber.id), None)
        
        status = "available"
        current_customer = None
        time_in_service = None
        
        if current_order:
            status = "busy"
            if current_order.customer_id:
                customer = db.query(Customer).filter(Customer.id == current_order.customer_id).first()
                current_customer = customer.name if customer else "Walk-in"
            if current_order.started_at:
                time_in_service = int((now - current_order.started_at).total_seconds() / 60)
        elif not barber.is_available:
            # Check if on break
            from app.models import BarberBreak
            active_break = db.query(BarberBreak).filter(
                BarberBreak.barber_id == barber.id,
                BarberBreak.end_time.is_(None)
            ).first()
            
            if active_break:
                status = "on_break"
            else:
                status = "unavailable"
        
        barber_status.append({
            "id": barber.id,
            "name": barber.name,
            "status": status,
            "current_customer": current_customer,
            "time_in_service_minutes": time_in_service
        })
    
    # Upcoming appointments (next 2 hours)
    upcoming = db.query(Appointment).filter(
        Appointment.scheduled_time >= now,
        Appointment.scheduled_time <= now + timedelta(hours=2),
        Appointment.status.in_(["scheduled", "confirmed"])
    ).order_by(Appointment.scheduled_time).all()
    
    return {
        "timestamp": now.isoformat(),
        "queue": {
            "count": len(queue),
            "next_up": queue[0].customer_name if queue else None,
            "customers": [
                {
                    "position": q.position,
                    "name": q.customer_name,
                    "wait_time": int((now - q.check_in_time).total_seconds() / 60),
                    "requested_barber": q.requested_barber.name if q.requested_barber_id else None
                }
                for q in queue[:5]
            ]
        },
        "barbers": barber_status,
        "services_in_progress": len(in_progress),
        "upcoming_appointments": [
            {
                "time": a.scheduled_time.strftime("%H:%M"),
                "customer": a.customer_name,
                "service": a.service_type.name if a.service_type else None,
                "barber": a.barber.name if a.barber else "Any"
            }
            for a in upcoming
        ]
    }
