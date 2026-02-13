from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime

from app.database import get_db

router = APIRouter(prefix="/feedback", tags=["feedback"])

# In-memory feedback storage
FEEDBACK_STORE: List[dict] = []


class FeedbackCreate(BaseModel):
    type: str  # "bug" or "feature"
    title: str
    description: str
    page_url: Optional[str] = None
    user_agent: Optional[str] = None


class FeedbackResponse(BaseModel):
    id: int
    type: str
    title: str
    description: str
    status: str
    created_at: str


@router.post("/", response_model=FeedbackResponse)
def submit_feedback(feedback: FeedbackCreate):
    """Submit bug report or feature request"""
    new_id = len(FEEDBACK_STORE) + 1
    entry = {
        "id": new_id,
        "type": feedback.type,
        "title": feedback.title,
        "description": feedback.description,
        "page_url": feedback.page_url,
        "user_agent": feedback.user_agent,
        "status": "pending",
        "created_at": datetime.utcnow().isoformat()
    }
    FEEDBACK_STORE.append(entry)
    return entry


@router.get("/", response_model=List[FeedbackResponse])
def list_feedback(type: Optional[str] = None, status: Optional[str] = None):
    """List all feedback"""
    results = FEEDBACK_STORE
    if type:
        results = [f for f in results if f["type"] == type]
    if status:
        results = [f for f in results if f["status"] == status]
    return results


@router.patch("/{feedback_id}/status")
def update_feedback_status(feedback_id: int, status: str):
    """Update feedback status"""
    feedback = next((f for f in FEEDBACK_STORE if f["id"] == feedback_id), None)
    if not feedback:
        return {"error": "Feedback not found"}
    
    valid_statuses = ["pending", "reviewing", "planned", "in_progress", "completed", "wont_fix"]
    if status not in valid_statuses:
        return {"error": f"Invalid status. Must be one of: {valid_statuses}"}
    
    feedback["status"] = status
    return feedback
