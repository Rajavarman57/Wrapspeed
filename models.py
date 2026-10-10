"""
models.py – Database schema for Warpspeed ERP.
WHAT IT DOES:
  Defines the 9 core database tables (User, Supplier, Buyer, Material,
  StockMovement, Order, Machine, WorkOrder, FabricRoll) using SQLAlchemy ORM.
WHY IT EXISTS:
  Provides structured, type-safe data models representing Everest Textile Mills'
  factory floor, inventory ledger, customer orders, and machinery.

DESIGN DECISION: WHY STOCK IS NEVER A STORED NUMBER
  In this ERP, `Material` has NO `quantity_in_stock` column.
  Stock is ALWAYS dynamically calculated from the `StockMovement` ledger table.
  WHY:
    1. Single Source of Truth: An append-only ledger eliminates discrepancies
       where a stored count gets out of sync with actual purchase receipts or consumption.
    2. Complete Audit Trail: We can reconstruct the exact inventory level at any point
       in time, knowing which order reserved yarn, who received it, and what lot was used.
    3. Separation of Physical vs Allocated:
       - On-hand stock = Receipts minus Consumptions (physically in warehouse).
       - Reserved stock = Reservations minus Releases (held for orders).
       - Available stock = On-hand minus Reserved (free to sell).
"""

from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import UserMixin
from extensions import db, login_manager


# ── 1. User Model ──────────────────────────────────────────────────────────
class User(db.Model, UserMixin):
    """
    WHAT IT DOES:
      Stores credentials and permissions for mill employees and clients.
    WHY IT EXISTS:
      Secures the system and enforces role-based access control
      (owner, store, supervisor, qc, buyer).
    """
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False)  # owner, store, supervisor, qc, buyer
    name = db.Column(db.String(120), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def set_password(self, password: str):
        """
        WHAT: Encrypts the raw text password into a secure hash.
        WHY: Never store plaintext passwords in the database for security.
        """
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        """
        WHAT: Checks if an entered password matches the stored cryptographic hash.
        WHY: Authenticates users when logging into the system.
        """
        return check_password_hash(self.password_hash, password)

    def __repr__(self):
        return f"<User {self.username} ({self.role})>"


@login_manager.user_loader
def load_user(user_id):
    """
    WHAT: Retrieves a User instance by primary key for Flask-Login.
    WHY: Flask-Login needs to reload the current user object from the session ID.
    """
    return db.session.get(User, int(user_id))


# ── 2. Supplier Model ──────────────────────────────────────────────────────
class Supplier(db.Model):
    """
    WHAT IT DOES:
      Stores contact details of external yarn and raw material vendors.
    WHY IT EXISTS:
      Tracks where incoming yarn shipments originate for traceability and auditing.
    """
    __tablename__ = "suppliers"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False, unique=True)
    contact = db.Column(db.String(120), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    stock_movements = db.relationship("StockMovement", backref="supplier", lazy=True)

    def __repr__(self):
        return f"<Supplier {self.name}>"


# ── 3. Buyer Model ─────────────────────────────────────────────────────────
class Buyer(db.Model):
    """
    WHAT IT DOES:
      Stores client business details who place textile fabric orders.
    WHY IT EXISTS:
      Connects orders, dispatches, and invoices to specific customer accounts.
    """
    __tablename__ = "buyers"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False, unique=True)
    contact = db.Column(db.String(120), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    orders = db.relationship("Order", backref="buyer", lazy=True)

    def __repr__(self):
        return f"<Buyer {self.name}>"


# ── 4. Material Model ──────────────────────────────────────────────────────
class Material(db.Model):
    """
    WHAT IT DOES:
      Catalogs raw materials (e.g. Cotton Yarn 30s, Polyester Yarn, Dyes).
    WHY IT EXISTS:
      Defines item master data and the safety reorder threshold.
      NOTE: Stock quantity is deliberately NOT stored here. It is computed
      on demand from StockMovement rows.
    """
    __tablename__ = "materials"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    colour = db.Column(db.String(60), nullable=False, default="Natural")
    unit = db.Column(db.String(20), nullable=False, default="kg")
    reorder_level = db.Column(db.Float, nullable=False, default=100.0)

    # Relationships
    movements = db.relationship("StockMovement", backref="material", lazy=True)

    def get_on_hand(self) -> float:
        """
        WHAT: Calculates total physical stock in the mill warehouse.
        WHY: Receipts add physical stock, while consumption removes it.
        """
        receipts = sum(m.qty for m in self.movements if m.movement_type == "RECEIPT")
        consumed = sum(m.qty for m in self.movements if m.movement_type == "CONSUME")
        return max(0.0, receipts - consumed)

    def get_reserved(self) -> float:
        """
        WHAT: Calculates stock locked for confirmed orders.
        WHY: Prevents selling or using the same yarn batch for two different orders.
        """
        reserved = sum(m.qty for m in self.movements if m.movement_type == "RESERVE")
        released = sum(m.qty for m in self.movements if m.movement_type == "RELEASE")
        return max(0.0, reserved - released)

    def get_available(self) -> float:
        """
        WHAT: Calculates stock free to be allocated to new orders.
        WHY: Available = Physical on-hand stock minus already-reserved stock.
        """
        return max(0.0, self.get_on_hand() - self.get_reserved())

    def is_low_stock(self) -> bool:
        """
        WHAT: Checks if available stock has dropped below the reorder point.
        WHY: Alerts the store manager to reorder yarn before production halts.
        """
        return self.get_available() < self.reorder_level

    def __repr__(self):
        return f"<Material {self.name} ({self.colour})>"


# ── 5. StockMovement Model ─────────────────────────────────────────────────
class StockMovement(db.Model):
    """
    WHAT IT DOES:
      An immutable ledger entry recording every change in inventory.
    WHY IT EXISTS:
      Provides an unalterable audit log of receipts, reservations, releases,
      and production consumptions.
    """
    __tablename__ = "stock_movements"

    id = db.Column(db.Integer, primary_key=True)
    material_id = db.Column(db.Integer, db.ForeignKey("materials.id"), nullable=False)
    movement_type = db.Column(db.String(20), nullable=False)  # RECEIPT, RESERVE, RELEASE, CONSUME
    qty = db.Column(db.Float, nullable=False)
    lot_no = db.Column(db.String(60), nullable=True)
    supplier_id = db.Column(db.Integer, db.ForeignKey("suppliers.id"), nullable=True)
    order_id = db.Column(db.Integer, db.ForeignKey("orders.id"), nullable=True)
    unit_cost = db.Column(db.Float, nullable=False, default=0.0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<StockMovement {self.movement_type} {self.qty}kg lot={self.lot_no}>"


# ── 6. Order Model ─────────────────────────────────────────────────────────
class Order(db.Model):
    """
    WHAT IT DOES:
      Represents a customer fabric order.
    WHY IT EXISTS:
      Tracks requested fabric specifications, target meters, deadline,
      and whether the order has been confirmed by the store manager.
      NOTE: Order status is NEVER stored in a database column. It is DERIVED
      dynamically from child WorkOrders and FabricRolls.
    """
    __tablename__ = "orders"

    id = db.Column(db.Integer, primary_key=True)
    buyer_id = db.Column(db.Integer, db.ForeignKey("buyers.id"), nullable=False)
    fabric_type = db.Column(db.String(80), nullable=False)
    colour = db.Column(db.String(60), nullable=False)
    meters = db.Column(db.Float, nullable=False)
    price_per_meter = db.Column(db.Float, nullable=False)
    deadline = db.Column(db.Date, nullable=False)
    confirmed = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    work_orders = db.relationship("WorkOrder", backref="order", lazy=True, order_by="WorkOrder.id")
    fabric_rolls = db.relationship("FabricRoll", backref="order", lazy=True)
    stock_movements = db.relationship("StockMovement", backref="order", lazy=True)

    def derive_status(self) -> str:
        """
        WHAT: Dynamically determines the current order lifecycle status.
        WHY: Adheres to CONTRACT.md rule that status is never stored and advanced
             by arbitrary flags; it reflects real progress on the mill floor.
             Status transitions:
             1. NEW: Confirmed or unconfirmed, but no manufacturing work has begun.
             2. WEAVING: A weaving work order is running or awaiting execution.
             3. DYEING: Weaving completed, dyeing work order is in progress.
             4. QC: Dyeing done, fabric rolls cut and awaiting quality inspection.
             5. READY: Rolls passed QC and ready for dispatch.
             6. DISPATCHED: All rolls packed and shipped.
        """
        # If no work orders have been created or none started
        if not self.work_orders:
            return "NEW"

        # Check work orders by stage
        weaving_wos = [wo for wo in self.work_orders if wo.stage == "WEAVING"]
        dyeing_wos = [wo for wo in self.work_orders if wo.stage == "DYEING"]

        # If any weaving work order is still PENDING or RUNNING
        if any(wo.status in ["PENDING", "RUNNING"] for wo in weaving_wos):
            # If all are PENDING with zero meters output, it is still NEW
            if all(wo.status == "PENDING" and (wo.completed_meters or 0) == 0 for wo in weaving_wos):
                return "NEW"
            return "WEAVING"

        # If weaving is done, check dyeing stage
        if any(wo.status in ["PENDING", "RUNNING"] for wo in dyeing_wos):
            return "DYEING"

        # If all work orders are DONE, check finished fabric rolls
        if self.fabric_rolls:
            # If any roll is waiting for inspection
            if any(r.qc_status == "PENDING" for r in self.fabric_rolls):
                return "QC"
            # If all inspected rolls are dispatched
            if all(r.dispatch_id is not None for r in self.fabric_rolls):
                return "DISPATCHED"
            # Otherwise, rolls have passed and are ready for dispatch
            return "READY"

        # Fallback if work orders are pending
        return "NEW"

    @property
    def status(self) -> str:
        """
        WHAT: Convenience property to access derived status like an attribute.
        WHY: Allows templates and serializers to access `order.status`.
        """
        return self.derive_status()

    def __repr__(self):
        return f"<Order #{self.id} {self.fabric_type} {self.meters}m>"


# ── 7. Machine Model ───────────────────────────────────────────────────────
class Machine(db.Model):
    """
    WHAT IT DOES:
      Represents physical machinery (looms, dyeing vats, spinning frames).
    WHY IT EXISTS:
      Tracks machine availability, breakdowns, and live factory load.
    """
    __tablename__ = "machines"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), nullable=False, unique=True)
    type = db.Column(db.String(40), nullable=False)    # SPINNING, WEAVING, DYEING
    status = db.Column(db.String(40), nullable=False, default="IDLE")  # RUNNING, IDLE, BREAKDOWN

    # Relationships
    work_orders = db.relationship("WorkOrder", backref="machine", lazy=True)

    def __repr__(self):
        return f"<Machine {self.name} [{self.type} - {self.status}]>"


# ── 8. WorkOrder Model ─────────────────────────────────────────────────────
class WorkOrder(db.Model):
    """
    WHAT IT DOES:
      A manufacturing job dispatching an order's meters to a specific machine.
    WHY IT EXISTS:
      Coordinates production schedules and tracks how many meters have been woven or dyed.
    """
    __tablename__ = "work_orders"

    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey("orders.id"), nullable=False)
    machine_id = db.Column(db.Integer, db.ForeignKey("machines.id"), nullable=False)
    stage = db.Column(db.String(40), nullable=False)    # WEAVING, DYEING
    status = db.Column(db.String(40), nullable=False, default="PENDING")  # PENDING, RUNNING, DONE
    target_meters = db.Column(db.Float, nullable=False)
    completed_meters = db.Column(db.Float, nullable=False, default=0.0)
    start_time = db.Column(db.DateTime, nullable=True)
    end_time = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    fabric_rolls = db.relationship("FabricRoll", backref="work_order", lazy=True)

    def __repr__(self):
        return f"<WorkOrder #{self.id} {self.stage} [{self.status}]>"


# ── 9. FabricRoll Model ────────────────────────────────────────────────────
class FabricRoll(db.Model):
    """
    WHAT IT DOES:
      Represents an individual physical roll of fabric (standard 50 meters).
    WHY IT EXISTS:
      Quality control occurs per roll. Each roll gets an individual barcode/QR
      code and passes or fails inspection before being assigned to a truck dispatch.
    """
    __tablename__ = "fabric_rolls"

    id = db.Column(db.Integer, primary_key=True)
    roll_code = db.Column(db.String(60), unique=True, nullable=False)
    order_id = db.Column(db.Integer, db.ForeignKey("orders.id"), nullable=False)
    work_order_id = db.Column(db.Integer, db.ForeignKey("work_orders.id"), nullable=True)
    machine_id = db.Column(db.Integer, db.ForeignKey("machines.id"), nullable=True)
    yarn_lot = db.Column(db.String(60), nullable=True)
    meters = db.Column(db.Float, nullable=False, default=50.0)
    qc_status = db.Column(db.String(20), nullable=False, default="PENDING")  # PENDING, PASS, REWORK, REJECT
    defect_type = db.Column(db.String(120), nullable=True)
    dispatch_id = db.Column(db.Integer, nullable=True)  # Populated when assigned to a dispatch shipment
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<FabricRoll {self.roll_code} ({self.qc_status})>"
