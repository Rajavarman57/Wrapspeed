"""
seed.py – Database seeder for Warpspeed ERP prototype.
WHAT IT DOES:
  Populates the database with realistic sample records:
  - 5 Users (one per role, password demo123)
  - 3 Suppliers
  - 4 Buyers
  - 6 Yarn Materials (with one falling below its safety reorder level)
  - 6 Machines (covering SPINNING, WEAVING, DYEING with mixed statuses)
  - 6 Orders representing all derived statuses (NEW, WEAVING, DYEING, QC, READY, DISPATCHED)
  - 20 FabricRolls with mixed QC statuses (PENDING, PASS, REWORK, REJECT)
  - Realistic StockMovements
WHY IT EXISTS:
  Allows immediate, out-of-the-box local testing and visual verification of
  the ERP prototype. Safe to execute multiple times idempotently.
"""

from datetime import datetime, date, timedelta
from app import create_app
from extensions import db
from models import (
    User,
    Supplier,
    Buyer,
    Material,
    StockMovement,
    Order,
    Machine,
    WorkOrder,
    FabricRoll,
)


def seed_database():
    """
    WHAT: Drops existing tables, creates fresh tables, and inserts seed records.
    WHY: Ensures running this script always leaves the database in a known,
         clean, predictable state without duplicate key errors.
    """
    app = create_app()
    with app.app_context():
        print("[*] Rebuilding database schema...")
        db.drop_all()
        db.create_all()

        print("[*] Creating 5 users (one per role)...")
        # ── 1. Create 5 Users (one per role, password demo123) ────────
        users = [
            User(username="owner", name="Rajesh Singhania (Owner)", role="owner"),
            User(username="store", name="Ramesh Kumar (Store Head)", role="store"),
            User(username="supervisor", name="Suresh Patil (Floor Supervisor)", role="supervisor"),
            User(username="qc", name="Anita Sharma (QC Inspector)", role="qc"),
            User(username="buyer", name="Vikram Mehta (Buyer Agent)", role="buyer"),
        ]
        for u in users:
            u.set_password("demo123")
            db.session.add(u)
        db.session.commit()

        print("[*] Creating 3 suppliers...")
        # ── 2. Create 3 Suppliers ──────────────────────────────────────
        suppliers = [
            Supplier(name="Vardhman Textiles Ltd", contact="supply@vardhman.com / +91-9876543210"),
            Supplier(name="Coimbatore Cotton Mills", contact="sales@coimbatorecotton.in / +91-9876543211"),
            Supplier(name="Surat Polyfils & Fibers", contact="orders@suratpolyfils.com / +91-9876543212"),
        ]
        db.session.add_all(suppliers)
        db.session.commit()

        print("[*] Creating 4 buyers...")
        # ── 3. Create 4 Buyers ─────────────────────────────────────────
        buyers = [
            Buyer(name="Raymond Apparel Ltd", contact="procurement@raymond.in"),
            Buyer(name="FabIndia Overseas", contact="orders@fabindia.net"),
            Buyer(name="Zara India Sourcing", contact="supply@zara.com"),
            Buyer(name="Arvind Fashion Mills", contact="merchandise@arvind.com"),
        ]
        db.session.add_all(buyers)
        db.session.commit()

        print("[*] Creating 6 yarn materials...")
        # ── 4. Create 6 Yarn Materials ─────────────────────────────────
        # Note: Material #6 has a reorder_level of 250.0 kg and will have
        # stock movements that leave available stock below 250.0 kg.
        materials = [
            Material(name="Cotton Yarn 30s", colour="Natural", unit="kg", reorder_level=200.0),
            Material(name="Cotton Yarn 40s", colour="White", unit="kg", reorder_level=150.0),
            Material(name="Polyester Yarn 150D", colour="Black", unit="kg", reorder_level=100.0),
            Material(name="Blended Yarn 20s", colour="Grey", unit="kg", reorder_level=120.0),
            Material(name="Combed Cotton Yarn 60s", colour="Bleached", unit="kg", reorder_level=180.0),
            Material(name="Organic Cotton Yarn 24s", colour="Raw", unit="kg", reorder_level=250.0),
        ]
        db.session.add_all(materials)
        db.session.commit()

        print("[*] Creating stock movements (including low-stock material)...")
        # ── 5. Create Stock Movements ──────────────────────────────────
        # Normal materials get healthy receipts:
        movements = [
            # Material 1: 800 received, 100 reserved -> 700 available (> 200)
            StockMovement(material_id=materials[0].id, movement_type="RECEIPT", qty=800.0,
                          lot_no="LOT-CY30-01", supplier_id=suppliers[0].id, unit_cost=220.0),
            StockMovement(material_id=materials[0].id, movement_type="RESERVE", qty=100.0,
                          lot_no="LOT-CY30-01", unit_cost=220.0),

            # Material 2: 500 received -> 500 available (> 150)
            StockMovement(material_id=materials[1].id, movement_type="RECEIPT", qty=500.0,
                          lot_no="LOT-CY40-01", supplier_id=suppliers[1].id, unit_cost=240.0),

            # Material 3: 400 received -> 400 available (> 100)
            StockMovement(material_id=materials[2].id, movement_type="RECEIPT", qty=400.0,
                          lot_no="LOT-PY150-01", supplier_id=suppliers[2].id, unit_cost=180.0),

            # Material 4: 600 received -> 600 available (> 120)
            StockMovement(material_id=materials[3].id, movement_type="RECEIPT", qty=600.0,
                          lot_no="LOT-BY20-01", supplier_id=suppliers[0].id, unit_cost=210.0),

            # Material 5: 350 received -> 350 available (> 180)
            StockMovement(material_id=materials[4].id, movement_type="RECEIPT", qty=350.0,
                          lot_no="LOT-CC60-01", supplier_id=suppliers[1].id, unit_cost=290.0),

            # Material 6 (LOW STOCK CASE):
            # Reorder level is 250 kg.
            # Received 150 kg, consumed 50 kg -> 100 kg on hand and available (< 250 kg reorder level)!
            StockMovement(material_id=materials[5].id, movement_type="RECEIPT", qty=150.0,
                          lot_no="LOT-ORG24-01", supplier_id=suppliers[0].id, unit_cost=310.0),
            StockMovement(material_id=materials[5].id, movement_type="CONSUME", qty=50.0,
                          lot_no="LOT-ORG24-01", unit_cost=310.0),
        ]
        db.session.add_all(movements)
        db.session.commit()

        print("[*] Creating 6 machines...")
        # ── 6. Create 6 Machines ───────────────────────────────────────
        machines = [
            Machine(name="SPIN-01", type="SPINNING", status="RUNNING"),
            Machine(name="SPIN-02", type="SPINNING", status="IDLE"),
            Machine(name="WEAV-01", type="WEAVING", status="RUNNING"),
            Machine(name="WEAV-02", type="WEAVING", status="BREAKDOWN"),
            Machine(name="DYE-01", type="DYEING", status="RUNNING"),
            Machine(name="DYE-02", type="DYEING", status="IDLE"),
        ]
        db.session.add_all(machines)
        db.session.commit()

        print("[*] Creating 6 orders at different lifecycle stages...")
        # ── 7. Create 6 Orders (one for each derived status) ───────────
        today = date.today()
        orders = [
            # Order 1: Will derive to "NEW"
            Order(buyer_id=buyers[0].id, fabric_type="Cotton Plain", colour="Natural",
                  meters=200.0, price_per_meter=350.0, deadline=today + timedelta(days=14),
                  confirmed=True),

            # Order 2: Will derive to "WEAVING"
            Order(buyer_id=buyers[1].id, fabric_type="Cotton Twill", colour="White",
                  meters=300.0, price_per_meter=420.0, deadline=today + timedelta(days=10),
                  confirmed=True),

            # Order 3: Will derive to "DYEING"
            Order(buyer_id=buyers[2].id, fabric_type="Polyester Satin", colour="Black",
                  meters=250.0, price_per_meter=380.0, deadline=today + timedelta(days=8),
                  confirmed=True),

            # Order 4: Will derive to "QC"
            Order(buyer_id=buyers[3].id, fabric_type="Blended Drill", colour="Grey",
                  meters=200.0, price_per_meter=390.0, deadline=today + timedelta(days=5),
                  confirmed=True),

            # Order 5: Will derive to "READY"
            Order(buyer_id=buyers[0].id, fabric_type="Cotton Plain", colour="Natural",
                  meters=200.0, price_per_meter=350.0, deadline=today + timedelta(days=3),
                  confirmed=True),

            # Order 6: Will derive to "DISPATCHED"
            Order(buyer_id=buyers[1].id, fabric_type="Cotton Twill", colour="White",
                  meters=200.0, price_per_meter=420.0, deadline=today - timedelta(days=1),
                  confirmed=True),
        ]
        db.session.add_all(orders)
        db.session.commit()

        print("[*] Creating Work Orders to drive order status transitions...")
        # ── 8. Create Work Orders to advance orders appropriately ──────
        # Order 1 (NEW): Has no running work orders
        wo_order1 = WorkOrder(order_id=orders[0].id, machine_id=machines[2].id,
                              stage="WEAVING", status="PENDING", target_meters=200.0, completed_meters=0.0)

        # Order 2 (WEAVING): Weaving is actively running
        wo_order2 = WorkOrder(order_id=orders[1].id, machine_id=machines[2].id,
                              stage="WEAVING", status="RUNNING", target_meters=300.0, completed_meters=150.0,
                              start_time=datetime.utcnow() - timedelta(hours=4))

        # Order 3 (DYEING): Weaving done, Dyeing running
        wo_order3_w = WorkOrder(order_id=orders[2].id, machine_id=machines[2].id,
                                stage="WEAVING", status="DONE", target_meters=250.0, completed_meters=250.0,
                                start_time=datetime.utcnow() - timedelta(days=2),
                                end_time=datetime.utcnow() - timedelta(days=1))
        wo_order3_d = WorkOrder(order_id=orders[2].id, machine_id=machines[4].id,
                                stage="DYEING", status="RUNNING", target_meters=250.0, completed_meters=100.0,
                                start_time=datetime.utcnow() - timedelta(hours=3))

        # Order 4 (QC): Both stages DONE, fabric rolls exist with PENDING QC
        wo_order4_w = WorkOrder(order_id=orders[3].id, machine_id=machines[2].id,
                                stage="WEAVING", status="DONE", target_meters=200.0, completed_meters=200.0,
                                start_time=datetime.utcnow() - timedelta(days=3),
                                end_time=datetime.utcnow() - timedelta(days=2))
        wo_order4_d = WorkOrder(order_id=orders[3].id, machine_id=machines[4].id,
                                stage="DYEING", status="DONE", target_meters=200.0, completed_meters=200.0,
                                start_time=datetime.utcnow() - timedelta(days=2),
                                end_time=datetime.utcnow() - timedelta(days=1))

        # Order 5 (READY): Both stages DONE, rolls passed QC, not yet dispatched
        wo_order5_w = WorkOrder(order_id=orders[4].id, machine_id=machines[2].id,
                                stage="WEAVING", status="DONE", target_meters=200.0, completed_meters=200.0,
                                start_time=datetime.utcnow() - timedelta(days=4),
                                end_time=datetime.utcnow() - timedelta(days=3))
        wo_order5_d = WorkOrder(order_id=orders[4].id, machine_id=machines[4].id,
                                stage="DYEING", status="DONE", target_meters=200.0, completed_meters=200.0,
                                start_time=datetime.utcnow() - timedelta(days=3),
                                end_time=datetime.utcnow() - timedelta(days=2))

        # Order 6 (DISPATCHED): Both stages DONE, rolls passed QC and dispatched
        wo_order6_w = WorkOrder(order_id=orders[5].id, machine_id=machines[2].id,
                                stage="WEAVING", status="DONE", target_meters=200.0, completed_meters=200.0,
                                start_time=datetime.utcnow() - timedelta(days=6),
                                end_time=datetime.utcnow() - timedelta(days=5))
        wo_order6_d = WorkOrder(order_id=orders[5].id, machine_id=machines[4].id,
                                stage="DYEING", status="DONE", target_meters=200.0, completed_meters=200.0,
                                start_time=datetime.utcnow() - timedelta(days=5),
                                end_time=datetime.utcnow() - timedelta(days=4))

        db.session.add_all([
            wo_order1, wo_order2,
            wo_order3_w, wo_order3_d,
            wo_order4_w, wo_order4_d,
            wo_order5_w, wo_order5_d,
            wo_order6_w, wo_order6_d,
        ])
        db.session.commit()

        print("[*] Creating 20 fabric rolls with mixed QC statuses...")
        # ── 9. Create 20 Fabric Rolls (Mixed QC statuses) ──────────────
        # Standard length is 50 meters per roll.
        # Distribution:
        # - 4 PENDING  (under Order 4 - waiting for QC inspection)
        # - 8 PASS     (4 under Order 5 awaiting dispatch, 4 under Order 6 already dispatched)
        # - 4 REWORK   (flagged with minor defects)
        # - 4 REJECT   (flagged with major defects)
        rolls = [
            # 4 PENDING Rolls (Order 4)
            FabricRoll(roll_code="ROLL-1001", order_id=orders[3].id, work_order_id=wo_order4_d.id,
                       machine_id=machines[4].id, yarn_lot="LOT-BY20-01", meters=50.0, qc_status="PENDING"),
            FabricRoll(roll_code="ROLL-1002", order_id=orders[3].id, work_order_id=wo_order4_d.id,
                       machine_id=machines[4].id, yarn_lot="LOT-BY20-01", meters=50.0, qc_status="PENDING"),
            FabricRoll(roll_code="ROLL-1003", order_id=orders[3].id, work_order_id=wo_order4_d.id,
                       machine_id=machines[4].id, yarn_lot="LOT-BY20-01", meters=50.0, qc_status="PENDING"),
            FabricRoll(roll_code="ROLL-1004", order_id=orders[3].id, work_order_id=wo_order4_d.id,
                       machine_id=machines[4].id, yarn_lot="LOT-BY20-01", meters=50.0, qc_status="PENDING"),

            # 4 PASS Rolls for Order 5 (Ready for dispatch)
            FabricRoll(roll_code="ROLL-1005", order_id=orders[4].id, work_order_id=wo_order5_d.id,
                       machine_id=machines[4].id, yarn_lot="LOT-CY30-01", meters=50.0, qc_status="PASS"),
            FabricRoll(roll_code="ROLL-1006", order_id=orders[4].id, work_order_id=wo_order5_d.id,
                       machine_id=machines[4].id, yarn_lot="LOT-CY30-01", meters=50.0, qc_status="PASS"),
            FabricRoll(roll_code="ROLL-1007", order_id=orders[4].id, work_order_id=wo_order5_d.id,
                       machine_id=machines[4].id, yarn_lot="LOT-CY30-01", meters=50.0, qc_status="PASS"),
            FabricRoll(roll_code="ROLL-1008", order_id=orders[4].id, work_order_id=wo_order5_d.id,
                       machine_id=machines[4].id, yarn_lot="LOT-CY30-01", meters=50.0, qc_status="PASS"),

            # 4 PASS Rolls for Order 6 (Already dispatched, dispatch_id=101)
            FabricRoll(roll_code="ROLL-1009", order_id=orders[5].id, work_order_id=wo_order6_d.id,
                       machine_id=machines[4].id, yarn_lot="LOT-CY40-01", meters=50.0, qc_status="PASS", dispatch_id=101),
            FabricRoll(roll_code="ROLL-1010", order_id=orders[5].id, work_order_id=wo_order6_d.id,
                       machine_id=machines[4].id, yarn_lot="LOT-CY40-01", meters=50.0, qc_status="PASS", dispatch_id=101),
            FabricRoll(roll_code="ROLL-1011", order_id=orders[5].id, work_order_id=wo_order6_d.id,
                       machine_id=machines[4].id, yarn_lot="LOT-CY40-01", meters=50.0, qc_status="PASS", dispatch_id=101),
            FabricRoll(roll_code="ROLL-1012", order_id=orders[5].id, work_order_id=wo_order6_d.id,
                       machine_id=machines[4].id, yarn_lot="LOT-CY40-01", meters=50.0, qc_status="PASS", dispatch_id=101),

            # 4 REWORK Rolls (with defect descriptions)
            FabricRoll(roll_code="ROLL-1013", order_id=orders[3].id, work_order_id=wo_order4_d.id,
                       machine_id=machines[4].id, yarn_lot="LOT-BY20-01", meters=50.0, qc_status="REWORK",
                       defect_type="Uneven Weft Tension"),
            FabricRoll(roll_code="ROLL-1014", order_id=orders[3].id, work_order_id=wo_order4_d.id,
                       machine_id=machines[4].id, yarn_lot="LOT-BY20-01", meters=50.0, qc_status="REWORK",
                       defect_type="Selvedge Curl"),
            FabricRoll(roll_code="ROLL-1015", order_id=orders[4].id, work_order_id=wo_order5_d.id,
                       machine_id=machines[4].id, yarn_lot="LOT-CY30-01", meters=50.0, qc_status="REWORK",
                       defect_type="Minor Shade Variation"),
            FabricRoll(roll_code="ROLL-1016", order_id=orders[4].id, work_order_id=wo_order5_d.id,
                       machine_id=machines[4].id, yarn_lot="LOT-CY30-01", meters=50.0, qc_status="REWORK",
                       defect_type="Loose Ends"),

            # 4 REJECT Rolls (with critical defect reasons)
            FabricRoll(roll_code="ROLL-1017", order_id=orders[3].id, work_order_id=wo_order4_d.id,
                       machine_id=machines[4].id, yarn_lot="LOT-BY20-01", meters=50.0, qc_status="REJECT",
                       defect_type="Severe Oil Stain"),
            FabricRoll(roll_code="ROLL-1018", order_id=orders[3].id, work_order_id=wo_order4_d.id,
                       machine_id=machines[4].id, yarn_lot="LOT-BY20-01", meters=50.0, qc_status="REJECT",
                       defect_type="Warp Break Hole"),
            FabricRoll(roll_code="ROLL-1019", order_id=orders[4].id, work_order_id=wo_order5_d.id,
                       machine_id=machines[4].id, yarn_lot="LOT-CY30-01", meters=50.0, qc_status="REJECT",
                       defect_type="Chemical Dye Burn"),
            FabricRoll(roll_code="ROLL-1020", order_id=orders[4].id, work_order_id=wo_order5_d.id,
                       machine_id=machines[4].id, yarn_lot="LOT-CY30-01", meters=50.0, qc_status="REJECT",
                       defect_type="Yarn Count Contamination"),
        ]
        db.session.add_all(rolls)
        db.session.commit()

        print("\n[+] SEEDING COMPLETE!")
        print("-" * 65)
        print("Verification Summary:")
        print(f" * Users created:       {User.query.count()} (owner, store, supervisor, qc, buyer)")
        print(f" * Suppliers created:   {Supplier.query.count()}")
        print(f" * Buyers created:      {Buyer.query.count()}")
        print(f" * Materials created:   {Material.query.count()}")
        low_mat = Material.query.filter_by(name="Organic Cotton Yarn 24s").first()
        print(f"   -> Low-stock test:   {low_mat.name} available={low_mat.get_available()}kg, reorder={low_mat.reorder_level}kg (is_low={low_mat.is_low_stock()})")
        print(f" * Machines created:    {Machine.query.count()}")
        print(f" * Orders created:      {Order.query.count()}")
        for o in Order.query.all():
            print(f"   -> Order #{o.id}: {o.fabric_type:16} => Derived Status: [{o.status}]")
        print(f" * Fabric rolls:        {FabricRoll.query.count()} (20 total, mixed QC)")
        qc_counts = {status: FabricRoll.query.filter_by(qc_status=status).count() for status in ["PENDING", "PASS", "REWORK", "REJECT"]}
        print(f"   -> QC breakdown:     {qc_counts}")
        print("-" * 65 + "\n")


if __name__ == "__main__":
    # WHAT: Calls the seeder function when run directly from command line.
    # WHY: Allows populating or resetting the database with `python seed.py`.
    seed_database()
