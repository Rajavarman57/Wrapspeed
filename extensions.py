"""
extensions.py – Shared Flask extensions.
WHAT IT DOES:
  Initializes SQLAlchemy and LoginManager without attaching them to a specific
  Flask app right away.
WHY IT EXISTS:
  Using an extensions file avoids circular import errors. Models and routes can
  import `db` and `login_manager` from here, while the main app connects to them
  later during app creation (Application Factory pattern).
"""

from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager

# WHAT: Database management object (ORM)
# WHY: Allows Python classes in models.py to map directly to SQLite tables
db = SQLAlchemy()

# WHAT: User session and login manager
# WHY: Handles tracking logged-in users, session cookies, and authentication
login_manager = LoginManager()
login_manager.login_view = "auth.login"
login_manager.login_message = "Please log in to access this page."
