from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from app.database import engine, Base, SessionLocal
from app.models import ServiceType, Barber
from app.routers import (
    customers,
    barbers,
    services,
    orders,
    payments,
    queue,
    appointments,
    reports,
    cash_drawer,
    products,
    feedback,
    loyalty,
    gift_cards,
)

# Seed data for barbershop services
SEED_SERVICES = [
    # Haircuts
    {"name": "Regular Haircut", "category": "haircut", "base_price": 25.00, "duration_minutes": 25, "description": "Classic men's haircut"},
    {"name": "Fade Haircut", "category": "haircut", "base_price": 30.00, "duration_minutes": 30, "description": "Skin fade, low fade, mid fade, or high fade"},
    {"name": "Taper Haircut", "category": "haircut", "base_price": 28.00, "duration_minutes": 25, "description": "Classic taper cut"},
    {"name": "Buzz Cut", "category": "haircut", "base_price": 20.00, "duration_minutes": 15, "description": "All-over clipper cut"},
    {"name": "Kid's Haircut", "category": "haircut", "base_price": 18.00, "duration_minutes": 20, "description": "Ages 12 and under"},
    {"name": "Senior Haircut", "category": "haircut", "base_price": 20.00, "duration_minutes": 20, "description": "Ages 65+"},
    {"name": "Long Hair Cut", "category": "haircut", "base_price": 35.00, "duration_minutes": 35, "description": "Scissor cut for longer styles"},
    
    # Beard Services
    {"name": "Beard Trim", "category": "beard", "base_price": 15.00, "duration_minutes": 15, "description": "Shape and trim beard"},
    {"name": "Beard Lineup", "category": "beard", "base_price": 12.00, "duration_minutes": 10, "description": "Clean edges and neckline"},
    {"name": "Full Beard Design", "category": "beard", "base_price": 25.00, "duration_minutes": 25, "description": "Complete beard sculpting"},
    {"name": "Hot Towel Shave", "category": "beard", "base_price": 30.00, "duration_minutes": 30, "description": "Classic straight razor shave with hot towel"},
    
    # Combo Deals
    {"name": "Haircut + Beard Trim", "category": "combo", "base_price": 35.00, "duration_minutes": 40, "description": "Regular haircut with beard trim"},
    {"name": "Fade + Beard Design", "category": "combo", "base_price": 50.00, "duration_minutes": 50, "description": "Fade haircut with full beard design"},
    {"name": "The Works", "category": "combo", "base_price": 55.00, "duration_minutes": 60, "description": "Haircut, hot towel shave, and facial"},
    
    # Add-ons
    {"name": "Eyebrow Trim", "category": "addon", "base_price": 8.00, "duration_minutes": 5, "description": "Shape and clean eyebrows"},
    {"name": "Nose/Ear Trim", "category": "addon", "base_price": 5.00, "duration_minutes": 5, "description": "Quick trim of nose and ear hair"},
    {"name": "Hair Design", "category": "addon", "base_price": 15.00, "duration_minutes": 15, "description": "Lines, parts, or designs"},
    {"name": "Hair Wash", "category": "addon", "base_price": 10.00, "duration_minutes": 10, "description": "Shampoo and scalp massage"},
    {"name": "Color Camo", "category": "addon", "base_price": 25.00, "duration_minutes": 20, "description": "Gray blending treatment"},
    {"name": "Scalp Treatment", "category": "addon", "base_price": 20.00, "duration_minutes": 15, "description": "Deep conditioning scalp treatment"},
]

SEED_BARBERS = [
    {"name": "Mike", "commission_rate": 0.50, "specialties": "fades,beard design"},
    {"name": "Carlos", "commission_rate": 0.50, "specialties": "fades,hair design"},
    {"name": "James", "commission_rate": 0.45, "specialties": "classic cuts,hot shave"},
    {"name": "Tony", "commission_rate": 0.50, "specialties": "all styles"},
]


def seed_database():
    db = SessionLocal()
    try:
        # Seed services if empty
        if db.query(ServiceType).count() == 0:
            for service_data in SEED_SERVICES:
                service = ServiceType(**service_data)
                db.add(service)
            db.commit()
            print(f"Seeded {len(SEED_SERVICES)} service types")
        
        # Seed barbers if empty
        if db.query(Barber).count() == 0:
            for barber_data in SEED_BARBERS:
                barber = Barber(**barber_data)
                db.add(barber)
            db.commit()
            print(f"Seeded {len(SEED_BARBERS)} barbers")
    finally:
        db.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: create tables and seed data
    Base.metadata.create_all(bind=engine)
    seed_database()
    yield
    # Shutdown
    pass


app = FastAPI(
    title="Barbershop POS API",
    description="Point of Sale system for barbershops - Walk-ins, Appointments, Queue Management",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routers
app.include_router(customers.router)
app.include_router(barbers.router)
app.include_router(services.router)
app.include_router(orders.router)
app.include_router(payments.router)
app.include_router(queue.router)
app.include_router(appointments.router)
app.include_router(reports.router)
app.include_router(cash_drawer.router)
app.include_router(products.router)
app.include_router(feedback.router)
app.include_router(loyalty.router)
app.include_router(gift_cards.router)


@app.get("/health")
def health_check():
    return {"status": "healthy"}


@app.get("/")
def root():
    return {
        "name": "Barbershop POS",
        "version": "1.0.0",
        "docs": "/docs"
    }
