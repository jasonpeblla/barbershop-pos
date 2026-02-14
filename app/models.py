from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime, ForeignKey, Text, Enum as SQLEnum
from sqlalchemy.orm import relationship
from datetime import datetime
import enum

from app.database import Base


class OrderStatus(str, enum.Enum):
    WAITING = "waiting"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class PaymentMethod(str, enum.Enum):
    CASH = "cash"
    CARD = "card"
    APPLE_PAY = "apple_pay"
    OTHER = "other"


class Customer(Base):
    __tablename__ = "customers"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    phone = Column(String, unique=True, index=True)
    email = Column(String, nullable=True)
    preferred_barber_id = Column(Integer, ForeignKey("barbers.id"), nullable=True)
    preferred_cut = Column(String, nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    orders = relationship("Order", back_populates="customer")
    preferred_barber = relationship("Barber", foreign_keys=[preferred_barber_id])


class Barber(Base):
    __tablename__ = "barbers"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    phone = Column(String, nullable=True)
    email = Column(String, nullable=True)
    commission_rate = Column(Float, default=0.5)  # 50% default
    specialties = Column(String, nullable=True)
    is_active = Column(Boolean, default=True)
    is_available = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    orders = relationship("Order", back_populates="barber")
    timeclock_entries = relationship("TimeClock", back_populates="barber")


class ServiceType(Base):
    __tablename__ = "service_types"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    category = Column(String, index=True)  # haircut, beard, combo, addon
    base_price = Column(Float)
    duration_minutes = Column(Integer, default=30)
    description = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True)


class Order(Base):
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True, index=True)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=True)
    barber_id = Column(Integer, ForeignKey("barbers.id"), nullable=True)
    status = Column(String, default=OrderStatus.WAITING)
    queue_position = Column(Integer, nullable=True)
    subtotal = Column(Float, default=0.0)
    tax = Column(Float, default=0.0)
    tip = Column(Float, default=0.0)
    total = Column(Float, default=0.0)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)

    customer = relationship("Customer", back_populates="orders")
    barber = relationship("Barber", back_populates="orders")
    services = relationship("OrderService", back_populates="order", cascade="all, delete-orphan")
    payment = relationship("Payment", back_populates="order", uselist=False)


class OrderService(Base):
    __tablename__ = "order_services"

    id = Column(Integer, primary_key=True, index=True)
    order_id = Column(Integer, ForeignKey("orders.id"))
    service_type_id = Column(Integer, ForeignKey("service_types.id"))
    quantity = Column(Integer, default=1)
    unit_price = Column(Float)
    notes = Column(Text, nullable=True)

    order = relationship("Order", back_populates="services")
    service_type = relationship("ServiceType")


class Payment(Base):
    __tablename__ = "payments"

    id = Column(Integer, primary_key=True, index=True)
    order_id = Column(Integer, ForeignKey("orders.id"))
    amount = Column(Float)
    tip_amount = Column(Float, default=0.0)
    method = Column(String, default=PaymentMethod.CASH)
    created_at = Column(DateTime, default=datetime.utcnow)

    order = relationship("Order", back_populates="payment")


class WalkInQueue(Base):
    __tablename__ = "walkin_queue"

    id = Column(Integer, primary_key=True, index=True)
    customer_name = Column(String)
    customer_phone = Column(String, nullable=True)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=True)
    requested_barber_id = Column(Integer, ForeignKey("barbers.id"), nullable=True)
    service_notes = Column(Text, nullable=True)
    position = Column(Integer)
    status = Column(String, default="waiting")  # waiting, called, in_service, completed, left
    estimated_wait = Column(Integer, nullable=True)  # minutes
    check_in_time = Column(DateTime, default=datetime.utcnow)
    called_time = Column(DateTime, nullable=True)
    completed_time = Column(DateTime, nullable=True)

    customer = relationship("Customer")
    requested_barber = relationship("Barber")


class TimeClock(Base):
    __tablename__ = "timeclock"

    id = Column(Integer, primary_key=True, index=True)
    barber_id = Column(Integer, ForeignKey("barbers.id"))
    clock_in = Column(DateTime, default=datetime.utcnow)
    clock_out = Column(DateTime, nullable=True)
    
    barber = relationship("Barber", back_populates="timeclock_entries")


class Appointment(Base):
    __tablename__ = "appointments"

    id = Column(Integer, primary_key=True, index=True)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=True)
    customer_name = Column(String)
    customer_phone = Column(String)
    barber_id = Column(Integer, ForeignKey("barbers.id"), nullable=True)
    service_type_id = Column(Integer, ForeignKey("service_types.id"))
    scheduled_time = Column(DateTime)
    duration_minutes = Column(Integer, default=30)
    status = Column(String, default="scheduled")  # scheduled, confirmed, in_progress, completed, cancelled, no_show
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    customer = relationship("Customer")
    barber = relationship("Barber")
    service_type = relationship("ServiceType")


class Feedback(Base):
    __tablename__ = "feedback"

    id = Column(Integer, primary_key=True, index=True)
    type = Column(String(50), nullable=False)  # "bug" or "feature"
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=False)
    email = Column(String(255), nullable=True)
    page_url = Column(String(500), nullable=True)
    user_agent = Column(String(500), nullable=True)
    status = Column(String(50), default="pending")  # pending, reviewing, planned, in_progress, completed, wont_fix
    created_at = Column(DateTime, default=datetime.utcnow)
