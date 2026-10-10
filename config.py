"""
config.py – Configuration and constants for the Warpspeed ERP.
WHAT IT DOES:
  Defines the fixed business rules, list of allowed statuses, recipes, and
  database path for the application.
WHY IT EXISTS:
  Centralizing constants prevents typos across different files and ensures
  all parts of the application adhere strictly to CONTRACT.md.
"""

import os

# Base directory of the project for locating local files
BASE_DIR = os.path.abspath(os.path.dirname(__file__))

# ── User Roles ─────────────────────────────────────────────────────────────
# Defines the access levels available in the textile mill
ROLES = ["owner", "store", "supervisor", "qc", "buyer"]

# ── Order Lifecycle Statuses ───────────────────────────────────────────────
# The stages a customer order moves through from creation to delivery
ORDER_STATUS = ["NEW", "WEAVING", "DYEING", "QC", "READY", "DISPATCHED"]

# ── Machine Constants ──────────────────────────────────────────────────────
# The three physical machine categories in the mill
MACHINE_TYPE = ["SPINNING", "WEAVING", "DYEING"]

# Operational state of any machine on the shop floor
MACHINE_STATUS = ["RUNNING", "IDLE", "BREAKDOWN"]

# ── Inventory Movement Types ───────────────────────────────────────────────
# Immutable ledger types for material inventory tracking:
# RECEIPT: Raw material arrived from supplier (adds to physical stock)
# RESERVE: Material allocated to a confirmed order (locks stock)
# RELEASE: Material reservation released (e.g., if order cancelled)
# CONSUME: Material physically used up in production (reduces stock)
MOVEMENT_TYPE = ["RECEIPT", "RESERVE", "RELEASE", "CONSUME"]

# ── Quality Control Statuses ───────────────────────────────────────────────
# Inspection outcomes for finished fabric rolls
QC_STATUS = ["PENDING", "PASS", "REWORK", "REJECT"]

# ── Work Order Statuses ────────────────────────────────────────────────────
# Progress of a production batch assigned to a specific machine
WORK_STATUS = ["PENDING", "RUNNING", "DONE"]

# ── Production Stages ──────────────────────────────────────────────────────
# The sequential manufacturing stages (DYEING is final where 50m rolls are cut)
STAGES = ["WEAVING", "DYEING"]

# ── Physical & Production Standards ────────────────────────────────────────
ROLL_LENGTH_M = 50          # Standard physical length of one roll in meters
WASTAGE = 0.08              # 8% standard material loss during spinning/weaving

# ── Fabric Recipes (Bill of Materials) ─────────────────────────────────────
# Maps fabric_type -> list of (material_name, kg_per_meter required)
FABRIC_RECIPES = {
    "Cotton Plain": [
        ("Cotton Yarn 30s", 0.15),
    ],
    "Cotton Twill": [
        ("Cotton Yarn 40s", 0.18),
    ],
    "Polyester Satin": [
        ("Polyester Yarn 150D", 0.14),
    ],
    "Blended Drill": [
        ("Blended Yarn 20s", 0.16),
    ],
}

# ── Factory Overhead and Wage Rates ────────────────────────────────────────
# Rate values are in INR per MACHINE-HOUR (not per meter)
DEFAULT_SETTINGS = {
    "wage_rate": 120,       # INR 120 per machine-hour for operator wages
    "overhead_rate": 50,    # INR 50 per machine-hour for factory electricity/rent
}

# ── Database & Flask Configuration ─────────────────────────────────────────
# Points to a local SQLite database file inside the repository for offline use
SQLALCHEMY_DATABASE_URI = f"sqlite:///{os.path.join(BASE_DIR, 'warpspeed.db')}"
SQLALCHEMY_TRACK_MODIFICATIONS = False
SECRET_KEY = "warpspeed-secret-key-2026"
