from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import datetime, date, timedelta
from typing import Optional

from app.database import get_db
from app.models import Order, Payment, Barber, ServiceType, OrderService, Customer, RevenueTarget
from pydantic import BaseModel

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


# ===== REVENUE TARGETS =====

class TargetCreate(BaseModel):
    target_type: str = "daily"  # daily, weekly, monthly
    target_date: str  # YYYY-MM-DD
    target_amount: float
    barber_id: Optional[int] = None
    notes: Optional[str] = None


@router.post("/targets")
def create_target(target: TargetCreate, db: Session = Depends(get_db)):
    """Create a revenue target"""
    target_date = datetime.strptime(target.target_date, "%Y-%m-%d")
    
    # Check for existing target
    existing = db.query(RevenueTarget).filter(
        RevenueTarget.target_type == target.target_type,
        func.date(RevenueTarget.target_date) == target_date.date(),
        RevenueTarget.barber_id == target.barber_id
    ).first()
    
    if existing:
        # Update existing
        existing.target_amount = target.target_amount
        existing.notes = target.notes
        db.commit()
        return {"message": "Target updated", "id": existing.id}
    
    db_target = RevenueTarget(
        target_type=target.target_type,
        target_date=target_date,
        target_amount=target.target_amount,
        barber_id=target.barber_id,
        notes=target.notes
    )
    db.add(db_target)
    db.commit()
    db.refresh(db_target)
    
    return {"message": "Target created", "id": db_target.id}


@router.get("/targets/today")
def get_today_targets(db: Session = Depends(get_db)):
    """Get today's revenue targets and progress"""
    today = date.today()
    
    # Get shop-wide daily target
    shop_target = db.query(RevenueTarget).filter(
        RevenueTarget.target_type == "daily",
        func.date(RevenueTarget.target_date) == today,
        RevenueTarget.barber_id.is_(None)
    ).first()
    
    # Get barber-specific targets
    barber_targets = db.query(RevenueTarget).filter(
        RevenueTarget.target_type == "daily",
        func.date(RevenueTarget.target_date) == today,
        RevenueTarget.barber_id.isnot(None)
    ).all()
    
    # Calculate actual revenue
    orders = db.query(Order).filter(
        func.date(Order.created_at) == today,
        Order.status == "completed"
    ).all()
    
    total_revenue = sum(o.subtotal for o in orders)
    
    # Shop progress
    shop_progress = None
    if shop_target:
        progress_pct = (total_revenue / shop_target.target_amount * 100) if shop_target.target_amount > 0 else 0
        shop_progress = {
            "target": shop_target.target_amount,
            "actual": round(total_revenue, 2),
            "remaining": round(max(0, shop_target.target_amount - total_revenue), 2),
            "progress_percent": round(min(100, progress_pct), 1),
            "on_track": progress_pct >= 50 or datetime.now().hour < 14,  # Expect 50% by 2pm
            "status": get_target_status(progress_pct)
        }
    
    # Barber progress
    barber_progress = []
    for bt in barber_targets:
        barber = db.query(Barber).filter(Barber.id == bt.barber_id).first()
        barber_orders = [o for o in orders if o.barber_id == bt.barber_id]
        barber_revenue = sum(o.subtotal for o in barber_orders)
        progress_pct = (barber_revenue / bt.target_amount * 100) if bt.target_amount > 0 else 0
        
        barber_progress.append({
            "barber_id": bt.barber_id,
            "barber_name": barber.name if barber else "Unknown",
            "target": bt.target_amount,
            "actual": round(barber_revenue, 2),
            "progress_percent": round(min(100, progress_pct), 1),
            "status": get_target_status(progress_pct)
        })
    
    return {
        "date": today.isoformat(),
        "shop_target": shop_progress,
        "barber_targets": barber_progress,
        "total_revenue_today": round(total_revenue, 2)
    }


def get_target_status(progress_pct: float) -> dict:
    """Get status based on progress percentage"""
    current_hour = datetime.now().hour
    expected_by_now = (current_hour - 9) / 10 * 100  # Assuming 9am-7pm workday
    
    if progress_pct >= 100:
        return {"level": "achieved", "emoji": "🎯", "message": "Target achieved!"}
    elif progress_pct >= expected_by_now:
        return {"level": "on_track", "emoji": "✅", "message": "On track"}
    elif progress_pct >= expected_by_now * 0.7:
        return {"level": "slightly_behind", "emoji": "⚡", "message": "Slightly behind - push harder!"}
    else:
        return {"level": "behind", "emoji": "🔥", "message": "Need to pick up pace!"}


@router.get("/targets/week")
def get_week_targets(db: Session = Depends(get_db)):
    """Get this week's revenue targets and progress"""
    today = date.today()
    week_start = today - timedelta(days=today.weekday())
    week_end = week_start + timedelta(days=6)
    
    # Get weekly target
    weekly_target = db.query(RevenueTarget).filter(
        RevenueTarget.target_type == "weekly",
        func.date(RevenueTarget.target_date) >= week_start,
        func.date(RevenueTarget.target_date) <= week_end,
        RevenueTarget.barber_id.is_(None)
    ).first()
    
    # Calculate week's revenue
    orders = db.query(Order).filter(
        func.date(Order.created_at) >= week_start,
        func.date(Order.created_at) <= today,
        Order.status == "completed"
    ).all()
    
    total_revenue = sum(o.subtotal for o in orders)
    
    # Daily breakdown
    daily_revenue = {}
    for i in range(7):
        day = week_start + timedelta(days=i)
        day_orders = [o for o in orders if o.created_at.date() == day]
        daily_revenue[day.strftime("%a")] = round(sum(o.subtotal for o in day_orders), 2)
    
    result = {
        "week_start": week_start.isoformat(),
        "week_end": week_end.isoformat(),
        "total_revenue": round(total_revenue, 2),
        "daily_breakdown": daily_revenue,
        "days_remaining": (week_end - today).days
    }
    
    if weekly_target:
        progress_pct = (total_revenue / weekly_target.target_amount * 100) if weekly_target.target_amount > 0 else 0
        days_elapsed = (today - week_start).days + 1
        expected_pct = (days_elapsed / 7) * 100
        
        result["target"] = {
            "amount": weekly_target.target_amount,
            "remaining": round(max(0, weekly_target.target_amount - total_revenue), 2),
            "progress_percent": round(min(100, progress_pct), 1),
            "daily_target_remaining": round((weekly_target.target_amount - total_revenue) / max(1, (week_end - today).days + 1), 2),
            "on_track": progress_pct >= expected_pct * 0.9
        }
    
    return result


@router.get("/targets/history")
def get_target_history(days: int = 30, db: Session = Depends(get_db)):
    """Get historical target performance"""
    end_date = date.today()
    start_date = end_date - timedelta(days=days)
    
    targets = db.query(RevenueTarget).filter(
        RevenueTarget.target_type == "daily",
        func.date(RevenueTarget.target_date) >= start_date,
        func.date(RevenueTarget.target_date) < end_date,
        RevenueTarget.barber_id.is_(None)
    ).order_by(RevenueTarget.target_date.desc()).all()
    
    history = []
    achieved_count = 0
    
    for t in targets:
        # Get actual revenue for that day
        day_orders = db.query(Order).filter(
            func.date(Order.created_at) == t.target_date.date(),
            Order.status == "completed"
        ).all()
        
        actual = sum(o.subtotal for o in day_orders)
        achieved = actual >= t.target_amount
        if achieved:
            achieved_count += 1
        
        history.append({
            "date": t.target_date.date().isoformat(),
            "target": t.target_amount,
            "actual": round(actual, 2),
            "achieved": achieved,
            "variance": round(actual - t.target_amount, 2)
        })
    
    return {
        "period_start": start_date.isoformat(),
        "period_end": end_date.isoformat(),
        "total_targets": len(targets),
        "targets_achieved": achieved_count,
        "achievement_rate": round((achieved_count / len(targets) * 100) if targets else 0, 1),
        "history": history
    }


@router.post("/targets/set-default")
def set_default_daily_target(amount: float, db: Session = Depends(get_db)):
    """Set default daily target for the next 30 days"""
    today = date.today()
    created = 0
    
    for i in range(30):
        target_date = today + timedelta(days=i)
        
        # Skip if target already exists
        existing = db.query(RevenueTarget).filter(
            RevenueTarget.target_type == "daily",
            func.date(RevenueTarget.target_date) == target_date,
            RevenueTarget.barber_id.is_(None)
        ).first()
        
        if not existing:
            db_target = RevenueTarget(
                target_type="daily",
                target_date=datetime.combine(target_date, datetime.min.time()),
                target_amount=amount
            )
            db.add(db_target)
            created += 1
    
    db.commit()
    
    return {
        "message": f"Created {created} daily targets",
        "daily_amount": amount,
        "period": f"{today.isoformat()} to {(today + timedelta(days=29)).isoformat()}"
    }


# ===== STAFF PERFORMANCE METRICS =====

@router.get("/performance/{barber_id}/detailed")
def get_detailed_performance(barber_id: int, days: int = 30, db: Session = Depends(get_db)):
    """Get detailed performance metrics for a barber"""
    from app.models import WalkInQueue, TimeClock
    
    barber = db.query(Barber).filter(Barber.id == barber_id).first()
    if not barber:
        raise HTTPException(status_code=404, detail="Barber not found")
    
    end_date = date.today()
    start_date = end_date - timedelta(days=days)
    
    # Orders in period
    orders = db.query(Order).filter(
        Order.barber_id == barber_id,
        Order.status == "completed",
        func.date(Order.completed_at) >= start_date
    ).all()
    
    # Calculate metrics
    total_revenue = sum(o.subtotal for o in orders)
    total_tips = sum(o.tip or 0 for o in orders)
    num_services = len(orders)
    
    # Average service time
    service_times = []
    for o in orders:
        if o.started_at and o.completed_at:
            duration = (o.completed_at - o.started_at).total_seconds() / 60
            if duration > 0 and duration < 180:  # Reasonable range
                service_times.append(duration)
    
    avg_service_time = sum(service_times) / len(service_times) if service_times else 0
    
    # Tip percentage
    avg_tip_pct = (total_tips / total_revenue * 100) if total_revenue > 0 else 0
    
    # Hours worked
    timeclock_entries = db.query(TimeClock).filter(
        TimeClock.barber_id == barber_id,
        func.date(TimeClock.clock_in) >= start_date
    ).all()
    
    total_hours = sum(
        (e.clock_out - e.clock_in).total_seconds() / 3600
        for e in timeclock_entries
        if e.clock_out
    )
    
    # Revenue per hour
    revenue_per_hour = total_revenue / total_hours if total_hours > 0 else 0
    
    # Service breakdown
    service_counts = {}
    for o in orders:
        for os in o.services:
            service = db.query(ServiceType).filter(ServiceType.id == os.service_type_id).first()
            if service:
                if service.name not in service_counts:
                    service_counts[service.name] = {"count": 0, "revenue": 0}
                service_counts[service.name]["count"] += os.quantity
                service_counts[service.name]["revenue"] += os.unit_price * os.quantity
    
    # Daily breakdown
    daily_stats = {}
    for o in orders:
        day = o.completed_at.date().isoformat()
        if day not in daily_stats:
            daily_stats[day] = {"services": 0, "revenue": 0, "tips": 0}
        daily_stats[day]["services"] += 1
        daily_stats[day]["revenue"] += o.subtotal
        daily_stats[day]["tips"] += o.tip or 0
    
    return {
        "barber": {
            "id": barber.id,
            "name": barber.name,
            "commission_rate": barber.commission_rate
        },
        "period": {
            "start": start_date.isoformat(),
            "end": end_date.isoformat(),
            "days": days
        },
        "metrics": {
            "total_services": num_services,
            "total_revenue": round(total_revenue, 2),
            "total_tips": round(total_tips, 2),
            "total_earnings": round(total_revenue * barber.commission_rate + total_tips, 2),
            "avg_ticket": round(total_revenue / num_services, 2) if num_services > 0 else 0,
            "avg_tip_percent": round(avg_tip_pct, 1),
            "avg_service_time_minutes": round(avg_service_time, 1),
            "total_hours_worked": round(total_hours, 1),
            "revenue_per_hour": round(revenue_per_hour, 2),
            "services_per_day": round(num_services / days, 1)
        },
        "service_breakdown": dict(sorted(service_counts.items(), key=lambda x: x[1]["count"], reverse=True)),
        "daily_stats": dict(sorted(daily_stats.items(), reverse=True)[:7])
    }


@router.get("/performance/comparison")
def compare_barber_performance(days: int = 30, db: Session = Depends(get_db)):
    """Compare performance across all barbers"""
    end_date = date.today()
    start_date = end_date - timedelta(days=days)
    
    barbers = db.query(Barber).filter(Barber.is_active == True).all()
    
    comparison = []
    for barber in barbers:
        orders = db.query(Order).filter(
            Order.barber_id == barber.id,
            Order.status == "completed",
            func.date(Order.completed_at) >= start_date
        ).all()
        
        revenue = sum(o.subtotal for o in orders)
        tips = sum(o.tip or 0 for o in orders)
        services = len(orders)
        
        comparison.append({
            "barber_id": barber.id,
            "name": barber.name,
            "services": services,
            "revenue": round(revenue, 2),
            "tips": round(tips, 2),
            "avg_ticket": round(revenue / services, 2) if services > 0 else 0,
            "tip_percent": round(tips / revenue * 100, 1) if revenue > 0 else 0
        })
    
    # Calculate rankings
    revenue_rank = sorted(comparison, key=lambda x: x["revenue"], reverse=True)
    services_rank = sorted(comparison, key=lambda x: x["services"], reverse=True)
    tips_rank = sorted(comparison, key=lambda x: x["tip_percent"], reverse=True)
    
    for i, b in enumerate(revenue_rank):
        b["revenue_rank"] = i + 1
    for i, b in enumerate(services_rank):
        next((c for c in comparison if c["barber_id"] == b["barber_id"]), {})["services_rank"] = i + 1
    for i, b in enumerate(tips_rank):
        next((c for c in comparison if c["barber_id"] == b["barber_id"]), {})["tips_rank"] = i + 1
    
    return {
        "period_days": days,
        "barbers": sorted(comparison, key=lambda x: x["revenue"], reverse=True),
        "team_totals": {
            "total_services": sum(b["services"] for b in comparison),
            "total_revenue": round(sum(b["revenue"] for b in comparison), 2),
            "total_tips": round(sum(b["tips"] for b in comparison), 2)
        }
    }


@router.get("/performance/efficiency")
def get_efficiency_metrics(db: Session = Depends(get_db)):
    """Get shop efficiency metrics"""
    today = date.today()
    week_start = today - timedelta(days=today.weekday())
    
    # This week's orders
    orders = db.query(Order).filter(
        Order.status == "completed",
        func.date(Order.completed_at) >= week_start
    ).all()
    
    # Calculate service efficiency
    total_services = len(orders)
    total_service_time = 0
    total_wait_time = 0
    
    for o in orders:
        if o.started_at and o.completed_at:
            service_duration = (o.completed_at - o.started_at).total_seconds() / 60
            total_service_time += service_duration
        
        if o.created_at and o.started_at:
            wait_duration = (o.started_at - o.created_at).total_seconds() / 60
            if wait_duration > 0 and wait_duration < 120:  # Reasonable range
                total_wait_time += wait_duration
    
    avg_service_time = total_service_time / total_services if total_services > 0 else 0
    avg_wait_time = total_wait_time / total_services if total_services > 0 else 0
    
    # Active barber hours
    from app.models import TimeClock
    timeclock = db.query(TimeClock).filter(
        func.date(TimeClock.clock_in) >= week_start
    ).all()
    
    total_labor_hours = sum(
        (t.clock_out - t.clock_in).total_seconds() / 3600
        for t in timeclock
        if t.clock_out
    )
    
    # Revenue
    total_revenue = sum(o.subtotal for o in orders)
    
    return {
        "period": f"{week_start.isoformat()} to {today.isoformat()}",
        "efficiency": {
            "avg_service_time_minutes": round(avg_service_time, 1),
            "avg_wait_time_minutes": round(avg_wait_time, 1),
            "services_per_labor_hour": round(total_services / total_labor_hours, 2) if total_labor_hours > 0 else 0,
            "revenue_per_labor_hour": round(total_revenue / total_labor_hours, 2) if total_labor_hours > 0 else 0
        },
        "totals": {
            "services": total_services,
            "revenue": round(total_revenue, 2),
            "labor_hours": round(total_labor_hours, 1)
        }
    }
