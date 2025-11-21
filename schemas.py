"""
Database Schemas for Visual Health E-commerce Hub

Each Pydantic model corresponds to one MongoDB collection. Collection name is the lowercase of the class name.

Notes:
- Authentication uses email + password (hashed).
- Orders compute totals and store a snapshot of items and delivery cost.
- Delivery fees are looked up by wilaya (region) code or name.
"""
from typing import List, Optional, Literal
from pydantic import BaseModel, Field, EmailStr
from datetime import datetime

# --- Users & Auth ---
class Address(BaseModel):
    label: str = Field(..., description="Label for the address (Home, Office, etc.)")
    full_name: str = Field(..., description="Recipient full name")
    phone: str = Field(..., description="Recipient phone number")
    wilaya: str = Field(..., description="Wilaya (region)")
    commune: Optional[str] = Field(None, description="Commune / City")
    street: str = Field(..., description="Street address")
    notes: Optional[str] = Field(None, description="Delivery notes")

class User(BaseModel):
    name: str
    email: EmailStr
    password_hash: str
    phone: Optional[str] = None
    addresses: List[Address] = []
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

# --- Catalogue ---
ProductCategory = Literal[
    "lentilles",
    "solutions",
    "lunettes_medicales",
    "lunettes_soleil",
]

class Product(BaseModel):
    title: str
    description: Optional[str] = None
    price: float = Field(..., ge=0)
    brand: Optional[str] = None
    color: Optional[str] = None
    frame_shape: Optional[str] = None
    type: Optional[str] = None
    category: ProductCategory
    images: List[str] = []
    in_stock: bool = True
    sku: Optional[str] = None

# --- Prescriptions ---
class Prescription(BaseModel):
    user_id: str
    image_url: str
    notes: Optional[str] = None

# --- Orders ---
class OrderItem(BaseModel):
    product_id: str
    title: str
    price: float
    quantity: int = Field(..., ge=1)
    image: Optional[str] = None

OrderStatus = Literal[
    "en_preparation",
    "expediee",
    "en_cours_de_livraison",
    "livree",
]

class Order(BaseModel):
    user_id: str
    items: List[OrderItem]
    address: Address
    wilaya: str
    subtotal: float
    delivery_fee: float
    total: float
    status: OrderStatus = "en_preparation"
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

# --- Delivery Fees ---
class DeliveryFee(BaseModel):
    wilaya: str
    fee: float = Field(..., ge=0)

# --- Doctors & Appointments ---
class Doctor(BaseModel):
    name: str
    address: str
    phone: Optional[str] = None
    hours: Optional[str] = None
    specialties: List[str] = []

class Appointment(BaseModel):
    user_id: str
    doctor_id: str
    date: str  # ISO date string (YYYY-MM-DD)
    time: str  # HH:MM
    status: Literal["pending", "confirmed", "cancelled"] = "pending"
    notes: Optional[str] = None

