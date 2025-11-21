import os
from typing import List, Optional, Any, Dict
from fastapi import FastAPI, HTTPException, Depends, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr
from bson import ObjectId
from datetime import datetime, timezone
import hashlib

from database import db, create_document, get_documents
from schemas import (
    User, Address, Product, Order, OrderItem, DeliveryFee,
    Prescription, Doctor, Appointment,
)

app = FastAPI(title="Visual Health E-commerce Hub")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------- Helpers ----------
class ObjId(str):
    @classmethod
    def __get_validators__(cls):
        yield cls.validate

    @classmethod
    def validate(cls, v):
        if isinstance(v, ObjectId):
            return str(v)
        try:
            return str(ObjectId(v))
        except Exception:
            raise ValueError("Invalid ObjectId")

def oid(obj: Any) -> str:
    if isinstance(obj, ObjectId):
        return str(obj)
    try:
        return str(ObjectId(obj))
    except Exception:
        return str(obj)


def now_utc():
    return datetime.now(timezone.utc)


def hash_password(pw: str) -> str:
    return hashlib.sha256(pw.encode("utf-8")).hexdigest()


def user_projection() -> Dict[str, int]:
    return {"password_hash": 0}


# ---------- Root & Health ----------
@app.get("/")
def read_root():
    return {"message": "Visual Health E-commerce Backend running"}


@app.get("/test")
def test_database():
    response = {
        "backend": "✅ Running",
        "database": "❌ Not Available",
        "database_url": "✅ Set" if os.getenv("DATABASE_URL") else "❌ Not Set",
        "database_name": "✅ Set" if os.getenv("DATABASE_NAME") else "❌ Not Set",
        "connection_status": "Not Connected",
        "collections": []
    }
    try:
        if db is not None:
            response["database"] = "✅ Available"
            response["connection_status"] = "Connected"
            response["collections"] = db.list_collection_names()
            response["database"] = "✅ Connected & Working"
        else:
            response["database"] = "⚠️  Available but not initialized"
    except Exception as e:
        response["database"] = f"❌ Error: {str(e)[:100]}"
    return response


# ---------- Admin seed ----------
class SeedResponse(BaseModel):
    products: int
    delivery_fees: int
    doctors: int

@app.post("/admin/seed", response_model=SeedResponse)
def admin_seed():
    # Seed delivery fees for some Algerian wilayas (example subset)
    fees = [
        ("Alger", 400), ("Oran", 500), ("Blida", 450), ("Constantine", 600), ("Tizi Ouzou", 550),
        ("Annaba", 600), ("Sétif", 550), ("Béjaïa", 600), ("Tlemcen", 600), ("Mostaganem", 600),
    ]
    inserted_fees = 0
    for name, fee in fees:
        existing = db["deliveryfee"].find_one({"wilaya": name})
        if not existing:
            create_document("deliveryfee", DeliveryFee(wilaya=name, fee=fee))
            inserted_fees += 1

    # Seed a few products
    sample_products = [
        Product(title="Lentilles journalières FreshLook", description="Confort quotidien.", price=2500,
                brand="FreshLook", category="lentilles", images=["/images/lentilles1.jpg"], color="vert"),
        Product(title="Solution d'entretien MultiPlus 360ml", description="Nettoyage et confort.", price=1200,
                brand="Bausch & Lomb", category="solutions", images=["/images/solution1.jpg"]),
        Product(title="Lunettes médicales Classic Noir", description="Monture légère.", price=8000,
                brand="OptiCare", category="lunettes_medicales", images=["/images/med1.jpg"], frame_shape="rect"),
        Product(title="Lunettes de soleil Aviator", description="Protection UV400.", price=9000,
                brand="RayBest", category="lunettes_soleil", images=["/images/sun1.jpg"], frame_shape="pilot"),
    ]
    inserted_products = 0
    for p in sample_products:
        exists = db["product"].find_one({"title": p.title})
        if not exists:
            create_document("product", p)
            inserted_products += 1

    # Seed doctors
    sample_doctors = [
        Doctor(name="Dr. Amine B.", address="Alger Centre", phone="0550 00 00 01", hours="9:00-17:00", specialties=["Ophtalmologie"]),
        Doctor(name="Dr. Sara K.", address="Oran", phone="0550 00 00 02", hours="10:00-18:00", specialties=["Ophtalmologie", "Pédiatrie"]),
    ]
    inserted_doctors = 0
    for d in sample_doctors:
        exists = db["doctor"].find_one({"name": d.name})
        if not exists:
            create_document("doctor", d)
            inserted_doctors += 1

    return SeedResponse(products=inserted_products, delivery_fees=inserted_fees, doctors=inserted_doctors)


# ---------- Auth & User Profile ----------
class RegisterRequest(BaseModel):
    name: str
    email: EmailStr
    password: str

class LoginRequest(BaseModel):
    email: EmailStr
    password: str

class AuthResponse(BaseModel):
    user_id: str
    token: str

@app.post("/auth/register", response_model=AuthResponse)
def register(payload: RegisterRequest):
    existing = db["user"].find_one({"email": payload.email})
    if existing:
        raise HTTPException(status_code=400, detail="Cet email est déjà utilisé")
    user = User(name=payload.name, email=payload.email, password_hash=hash_password(payload.password))
    user_id = create_document("user", user)
    token = hash_password(payload.email + payload.password)
    return AuthResponse(user_id=user_id, token=token)

@app.post("/auth/login", response_model=AuthResponse)
def login(payload: LoginRequest):
    user = db["user"].find_one({"email": payload.email})
    if not user or user.get("password_hash") != hash_password(payload.password):
        raise HTTPException(status_code=401, detail="Identifiants invalides")
    token = hash_password(payload.email + payload.password)
    return AuthResponse(user_id=str(user["_id"]), token=token)

class PasswordResetRequest(BaseModel):
    email: EmailStr

@app.post("/auth/forgot")
def forgot_password(req: PasswordResetRequest):
    # In a real app, send email. Here we just acknowledge.
    if not db["user"].find_one({"email": req.email}):
        raise HTTPException(status_code=404, detail="Utilisateur introuvable")
    return {"message": "Lien de réinitialisation envoyé (simulation)"}


class UpdateProfile(BaseModel):
    name: Optional[str] = None
    phone: Optional[str] = None

@app.get("/users/{user_id}")
def get_user(user_id: str):
    doc = db["user"].find_one({"_id": ObjectId(user_id)}, user_projection())
    if not doc:
        raise HTTPException(status_code=404, detail="Utilisateur introuvable")
    doc["_id"] = str(doc["_id"])
    return doc

@app.put("/users/{user_id}")
def update_user(user_id: str, payload: UpdateProfile):
    updates = {k: v for k, v in payload.model_dump(exclude_none=True).items()}
    if not updates:
        return {"updated": False}
    updates["updated_at"] = now_utc()
    res = db["user"].update_one({"_id": ObjectId(user_id)}, {"$set": updates})
    return {"updated": res.modified_count == 1}

# Addresses
@app.get("/users/{user_id}/addresses")
def list_addresses(user_id: str):
    user = db["user"].find_one({"_id": ObjectId(user_id)}, {"addresses": 1})
    if not user:
        raise HTTPException(status_code=404, detail="Utilisateur introuvable")
    return user.get("addresses", [])

@app.post("/users/{user_id}/addresses")
def add_address(user_id: str, addr: Address):
    res = db["user"].update_one({"_id": ObjectId(user_id)}, {"$push": {"addresses": addr.model_dump()}})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Utilisateur introuvable")
    return {"added": True}

@app.delete("/users/{user_id}/addresses")
def delete_address(user_id: str, label: str = Query(..., description="Address label to remove")):
    res = db["user"].update_one({"_id": ObjectId(user_id)}, {"$pull": {"addresses": {"label": label}}})
    return {"deleted": res.modified_count > 0}


# ---------- Catalogue & Search ----------
@app.get("/products")
def list_products(
    q: Optional[str] = None,
    category: Optional[str] = None,
    brand: Optional[str] = None,
    color: Optional[str] = None,
    frame_shape: Optional[str] = None,
    type: Optional[str] = None,
    price_min: Optional[float] = None,
    price_max: Optional[float] = None,
    limit: int = 50,
):
    filt: Dict[str, Any] = {}
    if category:
        filt["category"] = category
    if brand:
        filt["brand"] = brand
    if color:
        filt["color"] = color
    if frame_shape:
        filt["frame_shape"] = frame_shape
    if type:
        filt["type"] = type
    if price_min is not None or price_max is not None:
        price_q = {}
        if price_min is not None:
            price_q["$gte"] = price_min
        if price_max is not None:
            price_q["$lte"] = price_max
        filt["price"] = price_q
    if q:
        filt["$or"] = [
            {"title": {"$regex": q, "$options": "i"}},
            {"description": {"$regex": q, "$options": "i"}},
            {"brand": {"$regex": q, "$options": "i"}},
        ]
    items = db["product"].find(filt).limit(limit)
    out = []
    for it in items:
        it["_id"] = str(it["_id"])
        out.append(it)
    return out

class CreateProduct(Product):
    pass

@app.post("/products")
def create_product(p: CreateProduct):
    new_id = create_document("product", p)
    return {"_id": new_id}

@app.get("/products/{product_id}")
def get_product(product_id: str):
    doc = db["product"].find_one({"_id": ObjectId(product_id)})
    if not doc:
        raise HTTPException(status_code=404, detail="Produit introuvable")
    doc["_id"] = str(doc["_id"])
    return doc


# ---------- Delivery Fees ----------
@app.get("/delivery/fees")
def list_delivery_fees():
    fees = get_documents("deliveryfee")
    for f in fees:
        f["_id"] = str(f["_id"])
    return fees

@app.get("/delivery/fee")
def get_delivery_fee(wilaya: str):
    fee = db["deliveryfee"].find_one({"wilaya": {"$regex": f"^{wilaya}$", "$options": "i"}})
    if not fee:
        raise HTTPException(status_code=404, detail="Tarif non défini pour cette wilaya")
    return {"wilaya": fee["wilaya"], "fee": fee["fee"]}


# ---------- Checkout & Orders ----------
class CheckoutRequest(BaseModel):
    user_id: str
    items: List[OrderItem]
    address: Address
    wilaya: str

@app.post("/orders/checkout")
def checkout(payload: CheckoutRequest):
    # Calculate subtotal
    subtotal = sum([it.price * it.quantity for it in payload.items])
    fee_doc = db["deliveryfee"].find_one({"wilaya": {"$regex": f"^{payload.wilaya}$", "$options": "i"}})
    if not fee_doc:
        raise HTTPException(status_code=400, detail="Impossible de calculer les frais de livraison pour cette wilaya")
    delivery_fee = float(fee_doc["fee"])
    total = float(subtotal + delivery_fee)

    order = Order(
        user_id=payload.user_id,
        items=payload.items,
        address=payload.address,
        wilaya=payload.wilaya,
        subtotal=float(subtotal),
        delivery_fee=delivery_fee,
        total=total,
    )
    new_id = create_document("order", order)
    return {"order_id": new_id, "total": total, "delivery_fee": delivery_fee}

@app.get("/orders")
def list_orders(user_id: str):
    orders = db["order"].find({"user_id": user_id}).sort("created_at", -1)
    out = []
    for o in orders:
        o["_id"] = str(o["_id"])
        out.append(o)
    return out

class UpdateOrderStatus(BaseModel):
    status: str

@app.patch("/orders/{order_id}/status")
def update_order_status(order_id: str, payload: UpdateOrderStatus):
    allowed = {"en_preparation", "expediee", "en_cours_de_livraison", "livree"}
    if payload.status not in allowed:
        raise HTTPException(status_code=400, detail="Statut invalide")
    res = db["order"].update_one({"_id": ObjectId(order_id)}, {"$set": {"status": payload.status, "updated_at": now_utc()}})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Commande introuvable")
    return {"updated": True}

@app.get("/orders/{order_id}")
def get_order(order_id: str):
    doc = db["order"].find_one({"_id": ObjectId(order_id)})
    if not doc:
        raise HTTPException(status_code=404, detail="Commande introuvable")
    doc["_id"] = str(doc["_id"])
    return doc


# ---------- Prescriptions ----------
@app.post("/prescriptions")
def add_prescription(payload: Prescription):
    new_id = create_document("prescription", payload)
    return {"_id": new_id}

@app.get("/prescriptions")
def list_prescriptions(user_id: str):
    docs = db["prescription"].find({"user_id": user_id}).sort("created_at", -1)
    out = []
    for d in docs:
        d["_id"] = str(d["_id"])
        out.append(d)
    return out


# ---------- Doctors & Appointments ----------
@app.get("/doctors")
def list_doctors(q: Optional[str] = None):
    filt: Dict[str, Any] = {}
    if q:
        filt["$or"] = [
            {"name": {"$regex": q, "$options": "i"}},
            {"address": {"$regex": q, "$options": "i"}},
            {"specialties": {"$elemMatch": {"$regex": q, "$options": "i"}}},
        ]
    cur = db["doctor"].find(filt)
    out = []
    for d in cur:
        d["_id"] = str(d["_id"])
        out.append(d)
    return out

@app.post("/doctors")
def create_doctor(doc: Doctor):
    new_id = create_document("doctor", doc)
    return {"_id": new_id}

@app.get("/doctors/{doctor_id}")
def get_doctor(doctor_id: str):
    d = db["doctor"].find_one({"_id": ObjectId(doctor_id)})
    if not d:
        raise HTTPException(status_code=404, detail="Médecin introuvable")
    d["_id"] = str(d["_id"])
    return d

@app.post("/appointments")
def request_appointment(app_req: Appointment):
    new_id = create_document("appointment", app_req)
    return {"_id": new_id, "status": app_req.status}

@app.get("/appointments")
def list_appointments(user_id: str):
    cur = db["appointment"].find({"user_id": user_id}).sort("created_at", -1)
    out = []
    for a in cur:
        a["_id"] = str(a["_id"])
        out.append(a)
    return out


# ---------- Notifications (stubs) ----------
class NotificationRequest(BaseModel):
    user_id: Optional[str] = None
    title: str
    body: str

@app.post("/notifications/send")
def send_notification(req: NotificationRequest):
    # Stub: In real implementation, integrate FCM/APNs. Here we persist for history.
    payload = req.model_dump()
    payload["sent_at"] = now_utc()
    new_id = db["notification"].insert_one(payload).inserted_id
    return {"_id": str(new_id), "sent": True}


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
