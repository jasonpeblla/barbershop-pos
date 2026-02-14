from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional
from pydantic import BaseModel
from datetime import datetime

from app.database import get_db
from app.models import Product, InventoryTransaction

router = APIRouter(prefix="/products", tags=["products"])


class ProductCreate(BaseModel):
    name: str
    category: Optional[str] = None
    sku: Optional[str] = None
    barcode: Optional[str] = None
    price: float
    cost: Optional[float] = 0.0
    stock_quantity: int = 0
    low_stock_threshold: int = 5
    description: Optional[str] = None


class ProductUpdate(BaseModel):
    name: Optional[str] = None
    category: Optional[str] = None
    sku: Optional[str] = None
    barcode: Optional[str] = None
    price: Optional[float] = None
    cost: Optional[float] = None
    low_stock_threshold: Optional[int] = None
    description: Optional[str] = None
    is_active: Optional[bool] = None


class StockAdjustment(BaseModel):
    quantity: int
    transaction_type: str = "adjustment"  # restock, adjustment, damaged, returned
    notes: Optional[str] = None


class ProductSale(BaseModel):
    product_id: int
    quantity: int = 1


@router.get("/")
def list_products(category: Optional[str] = None, include_inactive: bool = False, db: Session = Depends(get_db)):
    """Get all products"""
    query = db.query(Product)
    
    if not include_inactive:
        query = query.filter(Product.is_active == True)
    
    if category:
        query = query.filter(Product.category == category)
    
    products = query.order_by(Product.category, Product.name).all()
    
    return [
        {
            "id": p.id,
            "name": p.name,
            "category": p.category,
            "sku": p.sku,
            "barcode": p.barcode,
            "price": p.price,
            "cost": p.cost,
            "stock_quantity": p.stock_quantity,
            "low_stock_threshold": p.low_stock_threshold,
            "is_low_stock": p.stock_quantity <= p.low_stock_threshold,
            "description": p.description,
            "is_active": p.is_active
        }
        for p in products
    ]


@router.get("/categories")
def list_categories(db: Session = Depends(get_db)):
    """Get product categories"""
    categories = db.query(Product.category).filter(
        Product.is_active == True,
        Product.category.isnot(None)
    ).distinct().all()
    return [c[0] for c in categories if c[0]]


@router.get("/low-stock")
def get_low_stock(db: Session = Depends(get_db)):
    """Get products with low stock"""
    products = db.query(Product).filter(
        Product.is_active == True,
        Product.stock_quantity <= Product.low_stock_threshold
    ).order_by(Product.stock_quantity).all()
    
    return [
        {
            "id": p.id,
            "name": p.name,
            "category": p.category,
            "sku": p.sku,
            "stock_quantity": p.stock_quantity,
            "low_stock_threshold": p.low_stock_threshold,
            "needs_restock": p.low_stock_threshold - p.stock_quantity
        }
        for p in products
    ]


@router.get("/inventory-value")
def get_inventory_value(db: Session = Depends(get_db)):
    """Get total inventory value"""
    products = db.query(Product).filter(Product.is_active == True).all()
    
    retail_value = sum(p.price * p.stock_quantity for p in products)
    cost_value = sum(p.cost * p.stock_quantity for p in products)
    potential_profit = retail_value - cost_value
    
    return {
        "total_products": len(products),
        "total_units": sum(p.stock_quantity for p in products),
        "retail_value": round(retail_value, 2),
        "cost_value": round(cost_value, 2),
        "potential_profit": round(potential_profit, 2)
    }


@router.get("/{product_id}")
def get_product(product_id: int, db: Session = Depends(get_db)):
    """Get a specific product"""
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    
    return {
        "id": product.id,
        "name": product.name,
        "category": product.category,
        "sku": product.sku,
        "barcode": product.barcode,
        "price": product.price,
        "cost": product.cost,
        "stock_quantity": product.stock_quantity,
        "low_stock_threshold": product.low_stock_threshold,
        "description": product.description,
        "is_active": product.is_active
    }


@router.post("/")
def create_product(product: ProductCreate, db: Session = Depends(get_db)):
    """Create a new product"""
    db_product = Product(**product.model_dump())
    db.add(db_product)
    db.commit()
    db.refresh(db_product)
    
    # Log initial stock if any
    if product.stock_quantity > 0:
        transaction = InventoryTransaction(
            product_id=db_product.id,
            quantity_change=product.stock_quantity,
            transaction_type="initial",
            notes="Initial stock"
        )
        db.add(transaction)
        db.commit()
    
    return {"message": "Product created", "id": db_product.id}


@router.patch("/{product_id}")
def update_product(product_id: int, update: ProductUpdate, db: Session = Depends(get_db)):
    """Update a product"""
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    
    update_data = update.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(product, field, value)
    
    db.commit()
    return {"message": "Product updated"}


@router.post("/{product_id}/restock")
def restock_product(product_id: int, adjustment: StockAdjustment, db: Session = Depends(get_db)):
    """Add stock to a product"""
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    
    old_stock = product.stock_quantity
    product.stock_quantity += adjustment.quantity
    
    # Log transaction
    transaction = InventoryTransaction(
        product_id=product_id,
        quantity_change=adjustment.quantity,
        transaction_type=adjustment.transaction_type,
        notes=adjustment.notes
    )
    db.add(transaction)
    db.commit()
    
    return {
        "message": "Stock updated",
        "old_stock": old_stock,
        "new_stock": product.stock_quantity,
        "change": adjustment.quantity
    }


@router.post("/{product_id}/adjust")
def adjust_stock(product_id: int, adjustment: StockAdjustment, db: Session = Depends(get_db)):
    """Adjust stock (can be negative for damaged/lost items)"""
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    
    old_stock = product.stock_quantity
    product.stock_quantity += adjustment.quantity
    
    if product.stock_quantity < 0:
        product.stock_quantity = 0
    
    # Log transaction
    transaction = InventoryTransaction(
        product_id=product_id,
        quantity_change=adjustment.quantity,
        transaction_type=adjustment.transaction_type,
        notes=adjustment.notes
    )
    db.add(transaction)
    db.commit()
    
    return {
        "message": "Stock adjusted",
        "old_stock": old_stock,
        "new_stock": product.stock_quantity
    }


@router.post("/sell")
def sell_products(sales: List[ProductSale], order_id: Optional[int] = None, db: Session = Depends(get_db)):
    """Record product sales and adjust stock"""
    results = []
    total = 0
    
    for sale in sales:
        product = db.query(Product).filter(Product.id == sale.product_id).first()
        if not product:
            results.append({"product_id": sale.product_id, "error": "Product not found"})
            continue
        
        if product.stock_quantity < sale.quantity:
            results.append({
                "product_id": sale.product_id,
                "product_name": product.name,
                "error": f"Insufficient stock (available: {product.stock_quantity})"
            })
            continue
        
        # Deduct stock
        product.stock_quantity -= sale.quantity
        subtotal = product.price * sale.quantity
        total += subtotal
        
        # Log transaction
        transaction = InventoryTransaction(
            product_id=product.id,
            quantity_change=-sale.quantity,
            transaction_type="sale",
            order_id=order_id,
            notes=f"Sold {sale.quantity} unit(s)"
        )
        db.add(transaction)
        
        results.append({
            "product_id": product.id,
            "product_name": product.name,
            "quantity": sale.quantity,
            "unit_price": product.price,
            "subtotal": subtotal
        })
    
    db.commit()
    
    return {
        "items": results,
        "total": round(total, 2)
    }


@router.get("/{product_id}/history")
def get_product_history(product_id: int, limit: int = 50, db: Session = Depends(get_db)):
    """Get inventory transaction history for a product"""
    transactions = db.query(InventoryTransaction).filter(
        InventoryTransaction.product_id == product_id
    ).order_by(InventoryTransaction.created_at.desc()).limit(limit).all()
    
    return [
        {
            "id": t.id,
            "quantity_change": t.quantity_change,
            "transaction_type": t.transaction_type,
            "notes": t.notes,
            "order_id": t.order_id,
            "created_at": t.created_at.isoformat()
        }
        for t in transactions
    ]


@router.get("/scan/{barcode}")
def scan_barcode(barcode: str, db: Session = Depends(get_db)):
    """Look up product by barcode"""
    product = db.query(Product).filter(
        Product.barcode == barcode,
        Product.is_active == True
    ).first()
    
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    
    return {
        "id": product.id,
        "name": product.name,
        "category": product.category,
        "price": product.price,
        "stock_quantity": product.stock_quantity
    }


@router.delete("/{product_id}")
def deactivate_product(product_id: int, db: Session = Depends(get_db)):
    """Deactivate a product (soft delete)"""
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    
    product.is_active = False
    db.commit()
    
    return {"message": "Product deactivated"}
