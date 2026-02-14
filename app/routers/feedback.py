from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime

from app.database import get_db
from app.models import Feedback

router = APIRouter(prefix="/feedback", tags=["feedback"])


class FeedbackCreate(BaseModel):
    type: str  # "bug" or "feature"
    title: str
    description: str
    email: Optional[str] = None
    page_url: Optional[str] = None
    user_agent: Optional[str] = None


class FeedbackResponse(BaseModel):
    id: int
    type: str
    title: str
    description: str
    email: Optional[str]
    status: str
    created_at: datetime

    class Config:
        from_attributes = True


@router.post("/", response_model=FeedbackResponse)
def submit_feedback(feedback: FeedbackCreate, db: Session = Depends(get_db)):
    """Submit bug report or feature request"""
    db_feedback = Feedback(
        type=feedback.type,
        title=feedback.title,
        description=feedback.description,
        email=feedback.email,
        page_url=feedback.page_url,
        user_agent=feedback.user_agent,
        status="pending"
    )
    db.add(db_feedback)
    db.commit()
    db.refresh(db_feedback)
    return db_feedback


@router.get("/", response_model=List[FeedbackResponse])
def list_feedback(
    type: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 50,
    db: Session = Depends(get_db)
):
    """List all feedback"""
    query = db.query(Feedback)
    if type:
        query = query.filter(Feedback.type == type)
    if status:
        query = query.filter(Feedback.status == status)
    return query.order_by(Feedback.created_at.desc()).limit(limit).all()


@router.patch("/{feedback_id}/status")
def update_feedback_status(feedback_id: int, status: str, db: Session = Depends(get_db)):
    """Update feedback status"""
    feedback = db.query(Feedback).filter(Feedback.id == feedback_id).first()
    if not feedback:
        raise HTTPException(status_code=404, detail="Feedback not found")
    
    valid_statuses = ["pending", "reviewing", "planned", "in_progress", "completed", "wont_fix"]
    if status not in valid_statuses:
        raise HTTPException(status_code=400, detail=f"Invalid status. Must be one of: {valid_statuses}")
    
    feedback.status = status
    db.commit()
    return {"ok": True, "status": status}
