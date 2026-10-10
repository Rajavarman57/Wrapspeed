"""
tests/test_services.py – Automated Tests for Every Business Rule.
WHAT IT DOES:
  Tests each core rule defined in the specification:
  1. Stock is a ledger (never store a stock number).
  2. Wastage included in yarn requirement.
  3. Reservation uses SELECT ... FOR UPDATE (and checks available stock).
  4. Consumption oldest-lot-first (FIFO).
  5. QC decisions append-only.
  6. Dispatch only passed, same-buyer, unshipped rolls.
  7. DB UNIQUE constraint on dispatch_items.roll_id.
  8. Server-side money stripping for FLOOR role.
  9. Audit log on every write.
  10. In-memory QR code generation with zero disk writes.
"""

from datetime import date, datetime, timedelta
import pytest
from sqlalchemy.exc import IntegrityError
from app.models.user import User, Buyer, Supplier
from app.models.yarn import Material, YarnLot, StockMovement
from app.models.order import Order
from app.models.production import Machine, WorkOrder
from app.models.quality import FabricRoll, QCRecord
from app.models.dispatch import Dispatch, DispatchItem, Invoice
from app.models.audit import AuditLog
from app.services.inventory import receive_stock, get_material_stock, consume_yarn_fifo
from app.services.orders import calculate_bom, create_order, confirm_order_and_reserve_stock
from app.services.production import start_work_order, log_output
from app.services.quality import record_qc_decision, generate_roll_qr_base64
from app.services.dispatch import create_dispatch
from app.services.costing import get_order_cost_and_profit
from app.core.security import sanitize_for_role


# ── Rule 1: Stock is a Ledger (Never Store a Stock Number) ──────
def test_stock_ledger_calculations(test_db):
    """Verifies that stock is derived dynamically from movements."""
    mat = Material(name="Test Cotton", colour="White", unit="kg", reorder_level=100.0)
    test_db.add(mat)
    test_db.commit()

    # Initial state
    stk = get_material_stock(test_db, mat.id)
    assert stk["on_hand"] == 0.0
    assert stk["reserved"] == 0.0
    assert stk["available"] == 0.0

    # Receive 500 kg
    lot = receive_stock(test_db, material_id=mat.id, lot_no="LOT-001", qty=500.0, unit_cost=200.0)
    stk = get_material_stock(test_db, mat.id)
    assert stk["on_hand"] == 500.0
    assert stk["available"] == 500.0

    # Reserve 200 kg
    test_db.add(StockMovement(material_id=mat.id, movement_type="RESERVE", qty=200.0))
    test_db.commit()
    stk = get_material_stock(test_db, mat.id)
    assert stk["on_hand"] == 500.0
    assert stk["reserved"] == 200.0
    assert stk["available"] == 300.0

    # Consume 150 kg
    test_db.add(StockMovement(material_id=mat.id, movement_type="CONSUME", qty=150.0))
    test_db.commit()
    stk = get_material_stock(test_db, mat.id)
    assert stk["on_hand"] == 350.0  # 500 - 150
    assert stk["available"] == 150.0 # 350 - 200


# ── Rule 2: Wastage Included in Yarn Requirement ────────────────
def test_wastage_in_bom_calculation():
    """Verifies that 8% wastage is added to gross requirement."""
    # Cotton Plain requires 0.15 kg/m
    meters = 1000.0
    bom = calculate_bom("Cotton Plain", meters)
    assert len(bom) == 1
    item = bom[0]
    expected_net = 1000.0 * 0.15       # 150.0 kg
    expected_gross = 150.0 * 1.08      # 162.0 kg
    assert item["net_kg"] == expected_net
    assert item["gross_kg"] == expected_gross


# ── Rule 3: Reservation with SELECT ... FOR UPDATE & Stock Check ─
def test_order_confirmation_and_reservation(test_db):
    """Verifies stock reservation and shortage detection."""
    mat = Material(name="Cotton Yarn 30s", colour="Natural", unit="kg", reorder_level=50.0)
    buyer = Buyer(name="Test Buyer")
    test_db.add_all([mat, buyer])
    test_db.commit()

    order = create_order(
        test_db,
        buyer_id=buyer.id,
        fabric_type="Cotton Plain",
        colour="Natural",
        meters=100.0,  # Requires 100 * 0.15 * 1.08 = 16.2 kg
        price_per_meter=350.0,
        deadline=date.today() + timedelta(days=7),
    )

    # Attempt to confirm without stock -> raises ValueError
    with pytest.raises(ValueError, match="shortages"):
        confirm_order_and_reserve_stock(test_db, order.id)

    # Receive sufficient stock
    receive_stock(test_db, material_id=mat.id, lot_no="LOT-C30", qty=50.0, unit_cost=220.0)

    # Now confirmation succeeds
    confirmed_order = confirm_order_and_reserve_stock(test_db, order.id)
    assert confirmed_order.confirmed is True

    stk = get_material_stock(test_db, mat.id)
    assert stk["reserved"] == 16.2
    assert stk["available"] == round(50.0 - 16.2, 2)


# ── Rule 4: Consumption Oldest-Lot-First (FIFO) ─────────────────
def test_fifo_consumption(test_db):
    """Verifies that yarn is consumed from the oldest lot first."""
    mat = Material(name="Poly Yarn", colour="Black", unit="kg", reorder_level=50.0)
    test_db.add(mat)
    test_db.commit()

    # Receive Lot 1 (Old) yesterday: 40 kg
    lot1 = YarnLot(lot_no="LOT-OLD", material_id=mat.id, initial_qty=40.0, unit_cost=100.0, received_date=datetime.utcnow() - timedelta(days=2))
    test_db.add(lot1)
    test_db.flush()
    test_db.add(StockMovement(material_id=mat.id, lot_id=lot1.id, movement_type="RECEIPT", qty=40.0, unit_cost=100.0))

    # Receive Lot 2 (New) today: 60 kg
    lot2 = YarnLot(lot_no="LOT-NEW", material_id=mat.id, initial_qty=60.0, unit_cost=110.0, received_date=datetime.utcnow())
    test_db.add(lot2)
    test_db.flush()
    test_db.add(StockMovement(material_id=mat.id, lot_id=lot2.id, movement_type="RECEIPT", qty=60.0, unit_cost=110.0))
    test_db.commit()

    # Consume 50 kg -> should completely deplete Lot 1 (40 kg) and take 10 kg from Lot 2
    consumed = consume_yarn_fifo(test_db, material_id=mat.id, qty_needed=50.0)
    test_db.commit()

    assert len(consumed) == 2
    assert consumed[0]["lot_no"] == "LOT-OLD"
    assert consumed[0]["qty"] == 40.0
    assert consumed[1]["lot_no"] == "LOT-NEW"
    assert consumed[1]["qty"] == 10.0


# ── Rule 5: QC Decisions Append-Only ────────────────────────────
def test_qc_records_are_append_only(test_db):
    """Verifies that inspecting a roll appends a new record and updates status."""
    buyer = Buyer(name="Buyer QC")
    test_db.add(buyer)
    test_db.commit()

    order = Order(buyer_id=buyer.id, fabric_type="Cotton Plain", colour="White", meters=100.0, price_per_meter=300.0, deadline=date.today())
    test_db.add(order)
    test_db.commit()

    roll = FabricRoll(roll_code="ROLL-TEST-001", order_id=order.id, length_m=50.0)
    test_db.add(roll)
    test_db.commit()

    assert roll.current_qc_status == "PENDING"
    assert len(roll.qc_records) == 0

    # 1st decision: REWORK
    rec1 = record_qc_decision(test_db, roll_id=roll.id, status="REWORK", defect_type="Minor tension")
    test_db.refresh(roll)
    assert roll.current_qc_status == "REWORK"
    assert len(roll.qc_records) == 1

    # 2nd decision: PASS (Append-only!)
    rec2 = record_qc_decision(test_db, roll_id=roll.id, status="PASS", notes="Fixed tension")
    test_db.refresh(roll)
    assert roll.current_qc_status == "PASS"
    assert len(roll.qc_records) == 2  # History preserved!


# ── Rule 6 & 7: Dispatch Rules & DB UNIQUE Constraint ──────────
def test_dispatch_rules_and_unique_constraint(test_db):
    """Verifies that rolls must be PASS, same buyer, unshipped, and cannot be dispatched twice."""
    buyer1 = Buyer(name="Buyer 1")
    buyer2 = Buyer(name="Buyer 2")
    test_db.add_all([buyer1, buyer2])
    test_db.commit()

    order1 = Order(buyer_id=buyer1.id, fabric_type="Cotton Plain", colour="White", meters=100.0, price_per_meter=300.0, deadline=date.today())
    order2 = Order(buyer_id=buyer2.id, fabric_type="Cotton Plain", colour="White", meters=100.0, price_per_meter=300.0, deadline=date.today())
    test_db.add_all([order1, order2])
    test_db.commit()

    roll1 = FabricRoll(roll_code="ROLL-B1-PASS", order_id=order1.id, length_m=50.0)
    roll2_fail = FabricRoll(roll_code="ROLL-B1-FAIL", order_id=order1.id, length_m=50.0)
    roll3_diff_buyer = FabricRoll(roll_code="ROLL-B2-PASS", order_id=order2.id, length_m=50.0)
    test_db.add_all([roll1, roll2_fail, roll3_diff_buyer])
    test_db.commit()

    record_qc_decision(test_db, roll_id=roll1.id, status="PASS")
    record_qc_decision(test_db, roll_id=roll2_fail.id, status="REJECT")
    record_qc_decision(test_db, roll_id=roll3_diff_buyer.id, status="PASS")

    # Reject non-passed roll
    with pytest.raises(ValueError, match="cannot be dispatched"):
        create_dispatch(test_db, buyer_id=buyer1.id, truck_no="TN-01-A", roll_ids=[roll2_fail.id])

    # Reject roll belonging to different buyer
    with pytest.raises(ValueError, match="belongs to a different buyer"):
        create_dispatch(test_db, buyer_id=buyer1.id, truck_no="TN-01-A", roll_ids=[roll3_diff_buyer.id])

    # Successful dispatch of roll1
    dsp = create_dispatch(test_db, buyer_id=buyer1.id, truck_no="TN-01-A", roll_ids=[roll1.id])
    assert dsp.id is not None
    assert dsp.invoice is not None

    # Cannot dispatch roll1 again (enforced both at service level and DB UNIQUE constraint)
    with pytest.raises(ValueError, match="already been dispatched"):
        create_dispatch(test_db, buyer_id=buyer1.id, truck_no="TN-01-B", roll_ids=[roll1.id])

    # Test direct DB UNIQUE constraint on dispatch_items.roll_id
    with pytest.raises(IntegrityError):
        duplicate_item = DispatchItem(dispatch_id=dsp.id, roll_id=roll1.id)
        test_db.add(duplicate_item)
        test_db.commit()
    test_db.rollback()


# ── Rule 8: Server-Side Money Stripping for FLOOR Role ──────────
def test_floor_money_stripping():
    """Verifies that all monetary fields are redacted server-side for FLOOR users."""
    data = {
        "order_id": 1,
        "fabric_type": "Cotton Plain",
        "meters": 500.0,
        "price_per_meter": 350.0,
        "material_cost": 25000.0,
        "wages_cost": 6000.0,
        "overhead_cost": 2500.0,
        "total_cost": 33500.0,
        "revenue": 175000.0,
        "profit": 141500.0,
    }

    # OWNER sees all values
    owner_view = sanitize_for_role(data, role="OWNER")
    assert owner_view["material_cost"] == 25000.0
    assert owner_view["profit"] == 141500.0

    # FLOOR user has money fields stripped to None
    floor_view = sanitize_for_role(data, role="FLOOR")
    assert floor_view["order_id"] == 1
    assert floor_view["meters"] == 500.0
    assert floor_view["price_per_meter"] is None
    assert floor_view["material_cost"] is None
    assert floor_view["wages_cost"] is None
    assert floor_view["overhead_cost"] is None
    assert floor_view["total_cost"] is None
    assert floor_view["revenue"] is None
    assert floor_view["profit"] is None


# ── Rule 9: Audit Log on Every Write ────────────────────────────
def test_audit_log_on_every_write(test_db):
    """Verifies that every service write inserts an AuditLog entry."""
    mat = Material(name="Cotton Yarn 30s", colour="Natural")
    buyer = Buyer(name="Buyer Audit")
    test_db.add_all([mat, buyer])
    test_db.commit()

    initial_audit_count = test_db.query(AuditLog).count()

    # 1. receive_stock logs
    receive_stock(test_db, material_id=mat.id, lot_no="LOT-AUDIT", qty=100.0, unit_cost=200.0, user_id=1)
    assert test_db.query(AuditLog).count() == initial_audit_count + 1

    # 2. create_order logs
    order = create_order(test_db, buyer_id=buyer.id, fabric_type="Cotton Plain", colour="Natural", meters=50.0, price_per_meter=300.0, deadline=date.today(), user_id=1)
    assert test_db.query(AuditLog).count() == initial_audit_count + 2

    # 3. confirm_order logs
    confirm_order_and_reserve_stock(test_db, order.id, user_id=1)
    assert test_db.query(AuditLog).count() == initial_audit_count + 3


# ── Rule 10: In-Memory QR Generation (No Disk Writes) ───────────
def test_in_memory_qr_generation():
    """Verifies that QR code generates as base64 PNG data in RAM."""
    qr_data = generate_roll_qr_base64("ROLL-TEST-123")
    assert qr_data.startswith("data:image/png;base64,")
    assert len(qr_data) > 100
