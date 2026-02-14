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
    loyalty_points = Column(Integer, default=0)  # Current points balance
    lifetime_points = Column(Integer, default=0)  # Total points ever earned
    birthday = Column(DateTime, nullable=True)  # Customer birthday for rewards
    birthday_discount_used_year = Column(Integer, nullable=True)  # Year discount was used
    vip_tier = Column(String(20), default="bronze")  # bronze, silver, gold, platinum
    total_spent = Column(Float, default=0.0)  # Total amount spent for tier calculation
    visit_count = Column(Integer, default=0)  # Number of visits
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
    recurring_id = Column(Integer, ForeignKey("recurring_appointments.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    customer = relationship("Customer")
    barber = relationship("Barber")
    service_type = relationship("ServiceType")
    recurring = relationship("RecurringAppointment", back_populates="appointments")


class RecurringAppointment(Base):
    """Recurring appointment templates"""
    __tablename__ = "recurring_appointments"

    id = Column(Integer, primary_key=True, index=True)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=False)
    barber_id = Column(Integer, ForeignKey("barbers.id"), nullable=True)
    service_type_id = Column(Integer, ForeignKey("service_types.id"), nullable=False)
    frequency = Column(String(20), nullable=False)  # weekly, biweekly, monthly
    day_of_week = Column(Integer, nullable=True)  # 0=Monday, 6=Sunday (for weekly/biweekly)
    time_of_day = Column(String(10), nullable=False)  # "10:00"
    start_date = Column(DateTime, nullable=False)
    end_date = Column(DateTime, nullable=True)  # null = indefinite
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    customer = relationship("Customer")
    barber = relationship("Barber")
    service_type = relationship("ServiceType")
    appointments = relationship("Appointment", back_populates="recurring")


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


class LoyaltyTransaction(Base):
    """Track loyalty points earned and redeemed"""
    __tablename__ = "loyalty_transactions"

    id = Column(Integer, primary_key=True, index=True)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=False)
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=True)
    points = Column(Integer, nullable=False)  # positive = earned, negative = redeemed
    transaction_type = Column(String(50), nullable=False)  # earned, redeemed, bonus, adjustment
    description = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    customer = relationship("Customer")
    order = relationship("Order")


class GiftCard(Base):
    """Gift cards for the barbershop"""
    __tablename__ = "gift_cards"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String(20), unique=True, index=True, nullable=False)
    initial_balance = Column(Float, nullable=False)
    current_balance = Column(Float, nullable=False)
    purchaser_name = Column(String(100), nullable=True)
    purchaser_email = Column(String(255), nullable=True)
    recipient_name = Column(String(100), nullable=True)
    recipient_email = Column(String(255), nullable=True)
    message = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=True)


class GiftCardTransaction(Base):
    """Track gift card transactions"""
    __tablename__ = "gift_card_transactions"

    id = Column(Integer, primary_key=True, index=True)
    gift_card_id = Column(Integer, ForeignKey("gift_cards.id"), nullable=False)
    amount = Column(Float, nullable=False)  # positive = add, negative = redemption
    transaction_type = Column(String(50), nullable=False)  # purchase, redemption, reload
    description = Column(String(255), nullable=True)
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    gift_card = relationship("GiftCard")


class ServicePackage(Base):
    """Pre-paid service packages/bundles"""
    __tablename__ = "service_packages"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)
    price = Column(Float, nullable=False)
    valid_days = Column(Integer, default=365)
    max_uses = Column(Integer, default=1)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    services = relationship("PackageService", back_populates="package")


class PackageService(Base):
    """Services included in a package"""
    __tablename__ = "package_services"

    id = Column(Integer, primary_key=True, index=True)
    package_id = Column(Integer, ForeignKey("service_packages.id"), nullable=False)
    service_type_id = Column(Integer, ForeignKey("service_types.id"), nullable=False)
    quantity = Column(Integer, default=1)

    package = relationship("ServicePackage", back_populates="services")
    service_type = relationship("ServiceType")


class CustomerPackage(Base):
    """Packages purchased by customers"""
    __tablename__ = "customer_packages"

    id = Column(Integer, primary_key=True, index=True)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=False)
    package_id = Column(Integer, ForeignKey("service_packages.id"), nullable=False)
    remaining_uses = Column(Integer, nullable=False)
    purchase_price = Column(Float, nullable=False)
    purchased_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=True)

    customer = relationship("Customer")
    package = relationship("ServicePackage")


class Discount(Base):
    """Discount/Promo codes"""
    __tablename__ = "discounts"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String(50), unique=True, index=True, nullable=False)
    name = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)
    discount_type = Column(String(20), nullable=False)  # "percent" or "fixed"
    discount_value = Column(Float, nullable=False)
    min_purchase = Column(Float, default=0.0)
    max_discount = Column(Float, nullable=True)  # cap for percentage discounts
    max_uses = Column(Integer, nullable=True)  # total uses allowed
    max_uses_per_customer = Column(Integer, default=1)
    times_used = Column(Integer, default=0)
    valid_from = Column(DateTime, nullable=True)
    valid_until = Column(DateTime, nullable=True)
    first_visit_only = Column(Boolean, default=False)
    service_ids = Column(String, nullable=True)  # comma-separated service IDs
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class DiscountUsage(Base):
    """Track discount code usage"""
    __tablename__ = "discount_usages"

    id = Column(Integer, primary_key=True, index=True)
    discount_id = Column(Integer, ForeignKey("discounts.id"), nullable=False)
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=True)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=True)
    amount_saved = Column(Float, nullable=False)
    used_at = Column(DateTime, default=datetime.utcnow)

    discount = relationship("Discount")
    customer = relationship("Customer")


class BarberSchedule(Base):
    """Weekly schedule for barbers"""
    __tablename__ = "barber_schedules"

    id = Column(Integer, primary_key=True, index=True)
    barber_id = Column(Integer, ForeignKey("barbers.id"), nullable=False)
    day_of_week = Column(Integer, nullable=False)  # 0=Monday, 6=Sunday
    start_time = Column(String(10), nullable=False)  # "09:00"
    end_time = Column(String(10), nullable=False)    # "17:00"
    is_available = Column(Boolean, default=True)

    barber = relationship("Barber")


class BarberDayOff(Base):
    """Days off for barbers"""
    __tablename__ = "barber_days_off"

    id = Column(Integer, primary_key=True, index=True)
    barber_id = Column(Integer, ForeignKey("barbers.id"), nullable=False)
    date = Column(DateTime, nullable=False)
    reason = Column(String(255), nullable=True)

    barber = relationship("Barber")


class BarberBreak(Base):
    """Track barber breaks during the day"""
    __tablename__ = "barber_breaks"

    id = Column(Integer, primary_key=True, index=True)
    barber_id = Column(Integer, ForeignKey("barbers.id"), nullable=False)
    break_type = Column(String(50), nullable=False)  # lunch, short, personal
    start_time = Column(DateTime, default=datetime.utcnow)
    end_time = Column(DateTime, nullable=True)
    scheduled_end_time = Column(DateTime, nullable=True)  # When break should end
    notes = Column(String(255), nullable=True)

    barber = relationship("Barber")


class MembershipPlan(Base):
    """Monthly membership plans"""
    __tablename__ = "membership_plans"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)
    monthly_price = Column(Float, nullable=False)
    haircuts_included = Column(Integer, default=0)  # 0 = unlimited
    discount_percent = Column(Integer, default=0)  # Discount on additional services
    priority_booking = Column(Boolean, default=False)
    free_products_monthly = Column(Integer, default=0)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class CustomerMembership(Base):
    """Customer membership subscriptions"""
    __tablename__ = "customer_memberships"

    id = Column(Integer, primary_key=True, index=True)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=False)
    plan_id = Column(Integer, ForeignKey("membership_plans.id"), nullable=False)
    status = Column(String(20), default="active")  # active, paused, cancelled, expired
    start_date = Column(DateTime, default=datetime.utcnow)
    next_billing_date = Column(DateTime, nullable=True)
    cancelled_at = Column(DateTime, nullable=True)
    haircuts_used_this_month = Column(Integer, default=0)
    last_reset_date = Column(DateTime, nullable=True)

    customer = relationship("Customer")
    plan = relationship("MembershipPlan")


class Product(Base):
    """Retail products for sale"""
    __tablename__ = "products"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    category = Column(String(50), nullable=True)  # pomade, shampoo, beard oil, etc.
    sku = Column(String(50), unique=True, nullable=True)
    barcode = Column(String(50), nullable=True)
    price = Column(Float, nullable=False)
    cost = Column(Float, default=0.0)  # Cost to shop for profit tracking
    stock_quantity = Column(Integer, default=0)
    low_stock_threshold = Column(Integer, default=5)
    description = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class InventoryTransaction(Base):
    """Track inventory changes"""
    __tablename__ = "inventory_transactions"

    id = Column(Integer, primary_key=True, index=True)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    quantity_change = Column(Integer, nullable=False)  # positive = add, negative = remove
    transaction_type = Column(String(50), nullable=False)  # restock, sale, adjustment, damaged, returned
    notes = Column(Text, nullable=True)
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    product = relationship("Product")
