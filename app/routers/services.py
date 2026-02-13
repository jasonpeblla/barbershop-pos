from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional
from pydantic import BaseModel

from app.database import get_db
from app.models import ServiceType

router = APIRouter(prefix="/services", tags=["services"])


class ServiceCreate(BaseModel):
    name: str
    category: str
    base_price: float
    duration_minutes: int = 30
    description: Optional[str] = None


class ServiceUpdate(BaseModel):
    name: Optional[str] = None
    category: Optional[str] = None
    base_price: Optional[float] = None
    duration_minutes: Optional[int] = None
    description: Optional[str] = None
    is_active: Optional[bool] = None


class ServiceResponse(BaseModel):
    id: int
    name: str
    category: str
    base_price: float
    duration_minutes: int
    description: Optional[str]
    is_active: bool

    class Config:
        from_attributes = True


@router.get("/", response_model=List[ServiceResponse])
def list_services(
    category: Optional[str] = None,
    active_only: bool = True,
    db: Session = Depends(get_db)
):
    query = db.query(ServiceType)
    if active_only:
        query = query.filter(ServiceType.is_active == True)
    if category:
        query = query.filter(ServiceType.category == category)
    return query.all()


@router.get("/categories")
def list_categories(db: Session = Depends(get_db)):
    categories = db.query(ServiceType.category).distinct().all()
    return [c[0] for c in categories]


@router.get("/{service_id}", response_model=ServiceResponse)
def get_service(service_id: int, db: Session = Depends(get_db)):
    service = db.query(ServiceType).filter(ServiceType.id == service_id).first()
    if not service:
        raise HTTPException(status_code=404, detail="Service not found")
    return service


@router.post("/", response_model=ServiceResponse)
def create_service(service: ServiceCreate, db: Session = Depends(get_db)):
    db_service = ServiceType(**service.model_dump())
    db.add(db_service)
    db.commit()
    db.refresh(db_service)
    return db_service


@router.patch("/{service_id}", response_model=ServiceResponse)
def update_service(service_id: int, service: ServiceUpdate, db: Session = Depends(get_db)):
    db_service = db.query(ServiceType).filter(ServiceType.id == service_id).first()
    if not db_service:
        raise HTTPException(status_code=404, detail="Service not found")
    
    update_data = service.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(db_service, field, value)
    
    db.commit()
    db.refresh(db_service)
    return db_service
