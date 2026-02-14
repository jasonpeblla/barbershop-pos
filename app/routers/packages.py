from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional
from pydantic import BaseModel
from datetime import datetime

from app.database import get_db
from app.models import ServicePackage, PackageService, ServiceType, Customer

router = APIRouter(prefix="/packages", tags=["packages"])


class PackageServiceInput(BaseModel):
    service_type_id: int
    quantity: int = 1


class PackageCreate(BaseModel):
    name: str
    description: Optional[str] = None
    price: float
    services: List[PackageServiceInput]
    valid_days: int = 365  # Package valid for 1 year by default
    max_uses: int = 1  # Number of times the package can be used


class PackageResponse(BaseModel):
    id: int
    name: str
    description: Optional[str]
    price: float
    original_value: float
    savings: float
    savings_percent: float
    services: List[dict]
    valid_days: int
    max_uses: int
    is_active: bool

    class Config:
        from_attributes = True


@router.get("/")
def list_packages(active_only: bool = True, db: Session = Depends(get_db)):
    """List all available packages"""
    query = db.query(ServicePackage)
    if active_only:
        query = query.filter(ServicePackage.is_active == True)
    
    packages = query.all()
    
    result = []
    for pkg in packages:
        services = []
        original_value = 0
        for ps in pkg.services:
            service = db.query(ServiceType).filter(ServiceType.id == ps.service_type_id).first()
            if service:
                services.append({
                    "service_id": service.id,
                    "service_name": service.name,
                    "quantity": ps.quantity,
                    "unit_price": service.base_price
                })
                original_value += service.base_price * ps.quantity
        
        savings = original_value - pkg.price
        
        result.append({
            "id": pkg.id,
            "name": pkg.name,
            "description": pkg.description,
            "price": pkg.price,
            "original_value": round(original_value, 2),
            "savings": round(savings, 2),
            "savings_percent": round((savings / original_value * 100) if original_value > 0 else 0, 1),
            "services": services,
            "valid_days": pkg.valid_days,
            "max_uses": pkg.max_uses,
            "is_active": pkg.is_active
        })
    
    return result


@router.post("/")
def create_package(package: PackageCreate, db: Session = Depends(get_db)):
    """Create a new service package"""
    # Calculate original value
    original_value = 0
    for svc in package.services:
        service = db.query(ServiceType).filter(ServiceType.id == svc.service_type_id).first()
        if not service:
            raise HTTPException(status_code=404, detail=f"Service {svc.service_type_id} not found")
        original_value += service.base_price * svc.quantity
    
    if package.price >= original_value:
        raise HTTPException(status_code=400, detail="Package price must be less than original value")
    
    # Create package
    pkg = ServicePackage(
        name=package.name,
        description=package.description,
        price=package.price,
        valid_days=package.valid_days,
        max_uses=package.max_uses
    )
    db.add(pkg)
    db.flush()
    
    # Add services to package
    for svc in package.services:
        ps = PackageService(
            package_id=pkg.id,
            service_type_id=svc.service_type_id,
            quantity=svc.quantity
        )
        db.add(ps)
    
    db.commit()
    db.refresh(pkg)
    
    savings = original_value - package.price
    
    return {
        "id": pkg.id,
        "name": pkg.name,
        "price": pkg.price,
        "original_value": round(original_value, 2),
        "savings": round(savings, 2),
        "savings_percent": round(savings / original_value * 100, 1),
        "message": "Package created"
    }


@router.post("/{package_id}/purchase")
def purchase_package(
    package_id: int,
    customer_id: int,
    db: Session = Depends(get_db)
):
    """Customer purchases a package"""
    package = db.query(ServicePackage).filter(ServicePackage.id == package_id).first()
    if not package:
        raise HTTPException(status_code=404, detail="Package not found")
    
    customer = db.query(Customer).filter(Customer.id == customer_id).first()
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    
    # Create customer package record
    from app.models import CustomerPackage
    
    customer_pkg = CustomerPackage(
        customer_id=customer_id,
        package_id=package_id,
        remaining_uses=package.max_uses,
        purchase_price=package.price
    )
    db.add(customer_pkg)
    db.commit()
    db.refresh(customer_pkg)
    
    return {
        "id": customer_pkg.id,
        "customer": customer.name,
        "package": package.name,
        "remaining_uses": customer_pkg.remaining_uses,
        "expires_at": customer_pkg.expires_at.isoformat() if customer_pkg.expires_at else None,
        "message": f"Package '{package.name}' purchased"
    }


@router.get("/customer/{customer_id}")
def get_customer_packages(customer_id: int, db: Session = Depends(get_db)):
    """Get all packages owned by a customer"""
    from app.models import CustomerPackage
    
    packages = db.query(CustomerPackage).filter(
        CustomerPackage.customer_id == customer_id,
        CustomerPackage.remaining_uses > 0
    ).all()
    
    result = []
    for cp in packages:
        package = db.query(ServicePackage).filter(ServicePackage.id == cp.package_id).first()
        if package:
            services = []
            for ps in package.services:
                service = db.query(ServiceType).filter(ServiceType.id == ps.service_type_id).first()
                if service:
                    services.append({
                        "service_name": service.name,
                        "quantity": ps.quantity
                    })
            
            result.append({
                "id": cp.id,
                "package_name": package.name,
                "remaining_uses": cp.remaining_uses,
                "purchased_at": cp.purchased_at,
                "expires_at": cp.expires_at,
                "services": services
            })
    
    return result


@router.post("/redeem/{customer_package_id}")
def redeem_package(customer_package_id: int, db: Session = Depends(get_db)):
    """Redeem one use of a customer's package"""
    from app.models import CustomerPackage
    
    customer_pkg = db.query(CustomerPackage).filter(CustomerPackage.id == customer_package_id).first()
    if not customer_pkg:
        raise HTTPException(status_code=404, detail="Customer package not found")
    
    if customer_pkg.remaining_uses <= 0:
        raise HTTPException(status_code=400, detail="No remaining uses")
    
    if customer_pkg.expires_at and customer_pkg.expires_at < datetime.utcnow():
        raise HTTPException(status_code=400, detail="Package has expired")
    
    customer_pkg.remaining_uses -= 1
    db.commit()
    
    package = db.query(ServicePackage).filter(ServicePackage.id == customer_pkg.package_id).first()
    
    return {
        "message": "Package redeemed",
        "package_name": package.name if package else "Unknown",
        "remaining_uses": customer_pkg.remaining_uses
    }


# Seed some popular packages
SEED_PACKAGES = [
    {
        "name": "Fresh Cut Club (5 Pack)",
        "description": "5 Regular Haircuts - Save $25!",
        "price": 100.00,
        "services": [{"service_type_id": 1, "quantity": 5}],  # Regular Haircut
        "max_uses": 5
    },
    {
        "name": "Fade Master (3 Pack)",
        "description": "3 Fade Haircuts at a discount",
        "price": 75.00,
        "services": [{"service_type_id": 2, "quantity": 3}],  # Fade Haircut
        "max_uses": 3
    },
    {
        "name": "The Grooming Bundle",
        "description": "Haircut + Beard Trim + Hot Towel",
        "price": 55.00,
        "services": [
            {"service_type_id": 1, "quantity": 1},  # Regular Haircut
            {"service_type_id": 8, "quantity": 1},  # Beard Trim
            {"service_type_id": 18, "quantity": 1}  # Hair Wash
        ],
        "max_uses": 1
    }
]
