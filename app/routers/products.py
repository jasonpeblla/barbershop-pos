from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional
from pydantic import BaseModel
from datetime import datetime

from app.database import get_db

router = APIRouter(prefix="/products", tags=["products"])

# In-memory products (would be DB in production)
PRODUCTS = [
    {"id": 1, "name": "Pomade - Matte", "category": "styling", "price": 18.00, "stock": 20, "sku": "POM-001"},
    {"id": 2, "name": "Pomade - High Shine", "category": "styling", "price": 20.00, "stock": 15, "sku": "POM-002"},
    {"id": 3, "name": "Hair Clay", "category": "styling", "price": 22.00, "stock": 12, "sku": "CLY-001"},
    {"id": 4, "name": "Hair Gel - Strong Hold", "category": "styling", "price": 12.00, "stock": 25, "sku": "GEL-001"},
    {"id": 5, "name": "Hair Spray", "category": "styling", "price": 15.00, "stock": 18, "sku": "SPR-001"},
    {"id": 6, "name": "Beard Oil", "category": "beard", "price": 25.00, "stock": 30, "sku": "BOI-001"},
    {"id": 7, "name": "Beard Balm", "category": "beard", "price": 22.00, "stock": 20, "sku": "BBM-001"},
    {"id": 8, "name": "Beard Wash", "category": "beard", "price": 16.00, "stock": 15, "sku": "BWS-001"},
    {"id": 9, "name": "Shampoo - Daily", "category": "haircare", "price": 14.00, "stock": 40, "sku": "SHP-001"},
    {"id": 10, "name": "Conditioner", "category": "haircare", "price": 14.00, "stock": 35, "sku": "CND-001"},
    {"id": 11, "name": "Anti-Dandruff Shampoo", "category": "haircare", "price": 18.00, "stock": 20, "sku": "SHP-002"},
    {"id": 12, "name": "Aftershave Balm", "category": "shaving", "price": 20.00, "stock": 25, "sku": "ASH-001"},
    {"id": 13, "name": "Pre-Shave Oil", "category": "shaving", "price": 18.00, "stock": 15, "sku": "PSO-001"},
    {"id": 14, "name": "Straight Razor", "category": "tools", "price": 45.00, "stock": 8, "sku": "TLS-001"},
    {"id": 15, "name": "Comb Set", "category": "tools", "price": 12.00, "stock": 30, "sku": "TLS-002"},
]


class ProductCreate(BaseModel):
    name: str
    category: str
    price: float
    stock: int = 0
    sku: Optional[str] = None


class ProductSale(BaseModel):
    product_id: int
    quantity: int = 1


@router.get("/")
def list_products(category: Optional[str] = None):
    """Get all products"""
    if category:
        return [p for p in PRODUCTS if p["category"] == category]
    return PRODUCTS


@router.get("/categories")
def list_categories():
    """Get product categories"""
    return list(set(p["category"] for p in PRODUCTS))


@router.get("/{product_id}")
def get_product(product_id: int):
    """Get a specific product"""
    product = next((p for p in PRODUCTS if p["id"] == product_id), None)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    return product


@router.post("/")
def create_product(product: ProductCreate):
    """Create a new product"""
    new_id = max(p["id"] for p in PRODUCTS) + 1
    new_product = {
        "id": new_id,
        **product.model_dump()
    }
    PRODUCTS.append(new_product)
    return new_product


@router.patch("/{product_id}/stock")
def update_stock(product_id: int, adjustment: int):
    """Adjust product stock"""
    product = next((p for p in PRODUCTS if p["id"] == product_id), None)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    
    product["stock"] += adjustment
    if product["stock"] < 0:
        product["stock"] = 0
    
    return product


@router.post("/sell")
def sell_products(sales: List[ProductSale]):
    """Record product sales and adjust stock"""
    results = []
    total = 0
    
    for sale in sales:
        product = next((p for p in PRODUCTS if p["id"] == sale.product_id), None)
        if not product:
            continue
        
        if product["stock"] < sale.quantity:
            results.append({
                "product_id": sale.product_id,
                "error": "Insufficient stock"
            })
            continue
        
        product["stock"] -= sale.quantity
        subtotal = product["price"] * sale.quantity
        total += subtotal
        
        results.append({
            "product_id": sale.product_id,
            "product_name": product["name"],
            "quantity": sale.quantity,
            "unit_price": product["price"],
            "subtotal": subtotal
        })
    
    return {
        "items": results,
        "total": round(total, 2)
    }


@router.get("/low-stock")
def get_low_stock(threshold: int = 10):
    """Get products with low stock"""
    return [p for p in PRODUCTS if p["stock"] <= threshold]
