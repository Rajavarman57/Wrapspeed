"""
app/seed.py – Seed Data for Everest Textile Mills.
WHAT IT DOES:
  Populates realistic starter data:
  - Users across OWNER, FLOOR, and BUYER roles
  - Suppliers, Buyers, Materials, and Yarn Lots
  - Stock movements
  - Machines across spinning, weaving, and dyeing
  - Orders across all lifecycle stages
  - Fabric rolls, append-only QCRecords, Dispatches, and Invoices.
WHY IT EXISTS:
  Implements the rule: "Seed realistic data on first run".
"""

from datetime import datetime, date, timedelta
from sqlalchemy.orm import Session
from app.core.security import hash_password
from app.models.user import User, Supplier, Buyer
from app.models.yarn import Material, YarnLot, StockMovement
from app.models.production import Machine, WorkOrder
from app.models.order import Order
from app.models.quality import FabricRoll, QCRecord
from app.models.dispatch import Dispatch, DispatchItem, Invoice
from app.models.audit import AuditLog


def seed_database_if_empty(db: Session):
    """
    Checks if the database already has users; if empty, populates all sample data.
    """
    if db.query(User).first():
        return  # Already seeded

    print("[*] Empty database detected. Seeding realistic textile mill data...")

    # ── 1. Create Buyers First (so buyers can be linked to users) ──
    buyers = [
        Buyer(name="Raymond Apparel Ltd", contact="procurement@raymond.in"),
        Buyer(name="FabIndia Retail", contact="sourcing@fabindia.net"),
        Buyer(name="Zara India Sourcing", contact="supply@zara.com"),
        Buyer(name="Arvind Fashion Mills", contact="merchandise@arvind.com"),
    ]
    db.add_all(buyers)
    db.flush()

    # ── 2. Create Users (OWNER, FLOOR, BUYER) ──────────────────────
    users = [
        User(
            username="owner",
            name="Rajesh Singhania (Mill Owner)",
            role="OWNER",
            hashed_password=hash_password("demo123"),
        ),
        User(
            username="floor",
            name="Suresh Patil (Floor Supervisor / Store)",
            role="FLOOR",
            hashed_password=hash_password("demo123"),
        ),
        User(
            username="buyer1",
            name="Vikram Mehta (Raymond Buyer)",
            role="BUYER",
            buyer_id=buyers[0].id,
            hashed_password=hash_password("demo123"),
        ),
        User(
            username="buyer2",
            name="Pooja Verma (FabIndia Buyer)",
            role="BUYER",
            buyer_id=buyers[1].id,
            hashed_password=hash_password("demo123"),
        ),
    ]
    db.add_all(users)
    db.flush()

    # ── 3. Create Suppliers ────────────────────────────────────────
    suppliers = [
        Supplier(name="Vardhman Textiles Ltd", contact="supply@vardhman.com"),
        Supplier(name="Coimbatore Cotton Mills", contact="sales@coimbatorecotton.in"),
        Supplier(name="Surat Polyfils & Fibers", contact="orders@suratpolyfils.com"),
    ]
    db.add_all(suppliers)
    db.flush()

    # ── 4. Create Materials ────────────────────────────────────────
    materials = [
        Material(name="Cotton Yarn 30s", colour="Natural", unit="kg", reorder_level=200.0),
        Material(name="Cotton Yarn 40s", colour="White", unit="kg", reorder_level=150.0),
        Material(name="Polyester Yarn 150D", colour="Black", unit="kg", reorder_level=100.0),
        Material(name="Blended Yarn 20s", colour="Grey", unit="kg", reorder_level=120.0),
        Material(name="Combed Cotton Yarn 60s", colour="Bleached", unit="kg", reorder_level=180.0),
        Material(name="Organic Cotton Yarn 24s", colour="Raw", unit="kg", reorder_level=250.0),
    ]
    db.add_all(materials)
    db.flush()

    # ── 5. Create Yarn Lots & Stock Receipts ────────────────────────
    lots = [
        YarnLot(lot_no="LOT-CY30-01", material_id=materials[0].id, supplier_id=suppliers[0].id, initial_qty=1000.0, unit_cost=220.0),
        YarnLot(lot_no="LOT-CY40-01", material_id=materials[1].id, supplier_id=suppliers[1].id, initial_qty=800.0, unit_cost=240.0),
        YarnLot(lot_no="LOT-PY150-01", material_id=materials[2].id, supplier_id=suppliers[2].id, initial_qty=600.0, unit_cost=180.0),
        YarnLot(lot_no="LOT-BY20-01", material_id=materials[3].id, supplier_id=suppliers[0].id, initial_qty=700.0, unit_cost=210.0),
        YarnLot(lot_no="LOT-CC60-01", material_id=materials[4].id, supplier_id=suppliers[1].id, initial_qty=500.0, unit_cost=290.0),
        # Material 6 with low stock:
        YarnLot(lot_no="LOT-ORG24-01", material_id=materials[5].id, supplier_id=suppliers[0].id, initial_qty=150.0, unit_cost=310.0),
    ]
    db.add_all(lots)
    db.flush()

    movements = []
    for lot in lots:
        movements.append(
            StockMovement(
                material_id=lot.material_id,
                lot_id=lot.id,
                movement_type="RECEIPT",
                qty=lot.initial_qty,
                unit_cost=lot.unit_cost,
                notes=f"Initial stock receipt {lot.lot_no}",
            )
        )
    # Organic cotton consume 50kg -> 100kg available (< 250kg reorder level)
    movements.append(
        StockMovement(
            material_id=materials[5].id,
            lot_id=lots[5].id,
            movement_type="CONSUME",
            qty=50.0,
            unit_cost=310.0,
            notes="Sample trial run consumption",
        )
    )
    db.add_all(movements)
    db.flush()

    # ── 6. Create Machines ─────────────────────────────────────────
    machines = [
        Machine(name="SPIN-01", type="SPINNING", status="RUNNING"),
        Machine(name="SPIN-02", type="SPINNING", status="IDLE"),
        Machine(name="WEAV-01", type="WEAVING", status="RUNNING"),
        Machine(name="WEAV-02", type="WEAVING", status="BREAKDOWN"),
        Machine(name="DYE-01", type="DYEING", status="RUNNING"),
        Machine(name="DYE-02", type="DYEING", status="IDLE"),
    ]
    db.add_all(machines)
    db.flush()

    # ── 7. Create Orders across stages ─────────────────────────────
    today = date.today()
    orders = [
        # Order 1: NEW
        Order(buyer_id=buyers[0].id, fabric_type="Cotton Plain", colour="Natural", meters=200.0, price_per_meter=350.0, deadline=today + timedelta(days=14), confirmed=True),
        # Order 2: WEAVING
        Order(buyer_id=buyers[1].id, fabric_type="Cotton Twill", colour="White", meters=300.0, price_per_meter=420.0, deadline=today + timedelta(days=10), confirmed=True),
        # Order 3: DYEING
        Order(buyer_id=buyers[2].id, fabric_type="Polyester Satin", colour="Black", meters=250.0, price_per_meter=380.0, deadline=today + timedelta(days=8), confirmed=True),
        # Order 4: QC
        Order(buyer_id=buyers[3].id, fabric_type="Blended Drill", colour="Grey", meters=200.0, price_per_meter=390.0, deadline=today + timedelta(days=5), confirmed=True),
        # Order 5: READY
        Order(buyer_id=buyers[0].id, fabric_type="Cotton Plain", colour="Natural", meters=200.0, price_per_meter=350.0, deadline=today + timedelta(days=3), confirmed=True),
        # Order 6: DISPATCHED
        Order(buyer_id=buyers[1].id, fabric_type="Cotton Twill", colour="White", meters=200.0, price_per_meter=420.0, deadline=today - timedelta(days=1), confirmed=True),
    ]
    db.add_all(orders)
    db.flush()

    # ── 8. Work Orders ─────────────────────────────────────────────
    wos = [
        WorkOrder(order_id=orders[1].id, machine_id=machines[2].id, stage="WEAVING", status="RUNNING", target_meters=300.0, completed_meters=150.0, start_time=datetime.utcnow() - timedelta(hours=4)),
        WorkOrder(order_id=orders[2].id, machine_id=machines[2].id, stage="WEAVING", status="DONE", target_meters=250.0, completed_meters=250.0, start_time=datetime.utcnow() - timedelta(days=2), end_time=datetime.utcnow() - timedelta(days=1)),
        WorkOrder(order_id=orders[2].id, machine_id=machines[4].id, stage="DYEING", status="RUNNING", target_meters=250.0, completed_meters=100.0, start_time=datetime.utcnow() - timedelta(hours=3)),
        WorkOrder(order_id=orders[3].id, machine_id=machines[2].id, stage="WEAVING", status="DONE", target_meters=200.0, completed_meters=200.0),
        WorkOrder(order_id=orders[3].id, machine_id=machines[4].id, stage="DYEING", status="DONE", target_meters=200.0, completed_meters=200.0),
        WorkOrder(order_id=orders[4].id, machine_id=machines[2].id, stage="WEAVING", status="DONE", target_meters=200.0, completed_meters=200.0),
        WorkOrder(order_id=orders[4].id, machine_id=machines[4].id, stage="DYEING", status="DONE", target_meters=200.0, completed_meters=200.0),
        WorkOrder(order_id=orders[5].id, machine_id=machines[2].id, stage="WEAVING", status="DONE", target_meters=200.0, completed_meters=200.0),
        WorkOrder(order_id=orders[5].id, machine_id=machines[4].id, stage="DYEING", status="DONE", target_meters=200.0, completed_meters=200.0),
    ]
    db.add_all(wos)
    db.flush()

    # ── 9. Fabric Rolls & QC Records ───────────────────────────────
    rolls = []
    # Order 4 rolls (PENDING QC)
    for i in range(1, 5):
        rolls.append(FabricRoll(roll_code=f"ROLL-4-QC-{i:03d}", order_id=orders[3].id, work_order_id=wos[4].id, machine_id=machines[4].id, length_m=50.0))
    # Order 5 rolls (PASS QC - READY for dispatch)
    for i in range(1, 5):
        r = FabricRoll(roll_code=f"ROLL-5-READY-{i:03d}", order_id=orders[4].id, work_order_id=wos[6].id, machine_id=machines[4].id, length_m=50.0)
        rolls.append(r)
    # Order 6 rolls (PASS QC & DISPATCHED)
    for i in range(1, 5):
        r = FabricRoll(roll_code=f"ROLL-6-DISP-{i:03d}", order_id=orders[5].id, work_order_id=wos[8].id, machine_id=machines[4].id, length_m=50.0)
        rolls.append(r)
    # Defective rolls for quality queue testing
    rolls.append(FabricRoll(roll_code="ROLL-DEF-REWORK-01", order_id=orders[3].id, length_m=50.0))
    rolls.append(FabricRoll(roll_code="ROLL-DEF-REJECT-01", order_id=orders[3].id, length_m=50.0))

    db.add_all(rolls)
    db.flush()

    # Add append-only QC records for Order 5 & 6 rolls and defects
    for r in rolls[4:8]:  # Order 5
        db.add(QCRecord(roll_id=r.id, status="PASS", inspector_id=users[1].id, notes="Clean weave & shade match"))
    for r in rolls[8:12]: # Order 6
        db.add(QCRecord(roll_id=r.id, status="PASS", inspector_id=users[1].id, notes="Passed final inspection"))
    # Defect records
    db.add(QCRecord(roll_id=rolls[12].id, status="REWORK", defect_type="Uneven Tension", inspector_id=users[1].id, notes="Rewind selvedge"))
    db.add(QCRecord(roll_id=rolls[13].id, status="REJECT", defect_type="Severe Oil Stain", inspector_id=users[1].id, notes="Chemical staining"))
    db.flush()

    # ── 10. Dispatch & Invoice for Order 6 ──────────────────────────
    dispatch = Dispatch(buyer_id=buyers[1].id, truck_no="KA-04-E-9912", created_by_id=users[0].id)
    db.add(dispatch)
    db.flush()

    for r in rolls[8:12]:
        db.add(DispatchItem(dispatch_id=dispatch.id, roll_id=r.id))
    db.flush()

    invoice = Invoice(
        dispatch_id=dispatch.id,
        buyer_id=buyers[1].id,
        invoice_number=f"INV-{today.strftime('%Y%m')}-0001",
        total_meters=200.0,
        subtotal=84000.0,
        tax_amount=4200.0,
        total_amount=88200.0,
    )
    db.add(invoice)

    # ── 11. Initial Audit Log Entry ────────────────────────────────
    db.add(
        AuditLog(
            action="SYSTEM_INITIALIZATION_SEED",
            entity_type="System",
            entity_id=1,
            user_id=users[0].id,
            details="Seeded initial demo mill records",
        )
    )

    db.commit()
    print("[+] Database successfully seeded!")


if __name__ == "__main__":
    from app.core.db import Base, engine, SessionLocal
    Base.metadata.create_all(bind=engine)
    session = SessionLocal()
    try:
        seed_database_if_empty(session)
    finally:
        session.close()
