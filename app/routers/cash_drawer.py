from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, date

from app.database import get_db

router = APIRouter(prefix="/cash-drawer", tags=["cash_drawer"])

# In-memory cash drawer state (would be DB in production)
drawer_state = {
    "is_open": False,
    "opened_at": None,
    "starting_cash": 0.0,
    "cash_sales": 0.0,
    "cash_added": 0.0,
    "cash_removed": 0.0,
    "transactions": []
}


class CashTransaction(BaseModel):
    amount: float
    type: str  # "sale", "add", "remove"
    note: Optional[str] = None


class DrawerOpen(BaseModel):
    starting_cash: float = 200.0


@router.get("/status")
def get_drawer_status():
    """Get current drawer status"""
    current_cash = (
        drawer_state["starting_cash"] + 
        drawer_state["cash_sales"] + 
        drawer_state["cash_added"] - 
        drawer_state["cash_removed"]
    )
    
    return {
        "is_open": drawer_state["is_open"],
        "opened_at": drawer_state["opened_at"],
        "starting_cash": drawer_state["starting_cash"],
        "cash_sales": drawer_state["cash_sales"],
        "cash_added": drawer_state["cash_added"],
        "cash_removed": drawer_state["cash_removed"],
        "current_cash": round(current_cash, 2),
        "transactions_count": len(drawer_state["transactions"])
    }


@router.post("/open")
def open_drawer(data: DrawerOpen):
    """Open cash drawer for the day"""
    if drawer_state["is_open"]:
        return {"error": "Drawer already open"}
    
    drawer_state["is_open"] = True
    drawer_state["opened_at"] = datetime.utcnow().isoformat()
    drawer_state["starting_cash"] = data.starting_cash
    drawer_state["cash_sales"] = 0.0
    drawer_state["cash_added"] = 0.0
    drawer_state["cash_removed"] = 0.0
    drawer_state["transactions"] = []
    
    return {
        "message": "Drawer opened",
        "starting_cash": data.starting_cash
    }


@router.post("/close")
def close_drawer():
    """Close and reconcile cash drawer"""
    if not drawer_state["is_open"]:
        return {"error": "Drawer not open"}
    
    current_cash = (
        drawer_state["starting_cash"] + 
        drawer_state["cash_sales"] + 
        drawer_state["cash_added"] - 
        drawer_state["cash_removed"]
    )
    
    summary = {
        "opened_at": drawer_state["opened_at"],
        "closed_at": datetime.utcnow().isoformat(),
        "starting_cash": drawer_state["starting_cash"],
        "cash_sales": round(drawer_state["cash_sales"], 2),
        "cash_added": round(drawer_state["cash_added"], 2),
        "cash_removed": round(drawer_state["cash_removed"], 2),
        "expected_cash": round(current_cash, 2),
        "transactions_count": len(drawer_state["transactions"])
    }
    
    drawer_state["is_open"] = False
    
    return {"message": "Drawer closed", "summary": summary}


@router.post("/sale")
def record_sale(transaction: CashTransaction):
    """Record a cash sale"""
    if not drawer_state["is_open"]:
        return {"error": "Drawer not open"}
    
    drawer_state["cash_sales"] += transaction.amount
    drawer_state["transactions"].append({
        "type": "sale",
        "amount": transaction.amount,
        "note": transaction.note,
        "time": datetime.utcnow().isoformat()
    })
    
    return {"message": "Sale recorded", "amount": transaction.amount}


@router.post("/add")
def add_cash(transaction: CashTransaction):
    """Add cash to drawer (e.g., making change)"""
    if not drawer_state["is_open"]:
        return {"error": "Drawer not open"}
    
    drawer_state["cash_added"] += transaction.amount
    drawer_state["transactions"].append({
        "type": "add",
        "amount": transaction.amount,
        "note": transaction.note,
        "time": datetime.utcnow().isoformat()
    })
    
    return {"message": "Cash added", "amount": transaction.amount}


@router.post("/remove")
def remove_cash(transaction: CashTransaction):
    """Remove cash from drawer (e.g., safe drop)"""
    if not drawer_state["is_open"]:
        return {"error": "Drawer not open"}
    
    drawer_state["cash_removed"] += transaction.amount
    drawer_state["transactions"].append({
        "type": "remove",
        "amount": transaction.amount,
        "note": transaction.note,
        "time": datetime.utcnow().isoformat()
    })
    
    return {"message": "Cash removed", "amount": transaction.amount}


@router.get("/transactions")
def get_transactions():
    """Get all transactions for current session"""
    return drawer_state["transactions"]
