"""
routes/auth.py – Login and logout endpoints.
Also provides the role_required() decorator used by every other blueprint
to restrict access based on user role.
"""

from functools import wraps
from flask import Blueprint, render_template, redirect, url_for, request, flash
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import check_password_hash
from models import db, User

bp = Blueprint("auth", __name__)


# ── Decorator: restrict routes to certain roles ────────────
def role_required(*roles):
    """
    Decorator that checks the logged-in user has one of the allowed roles.
    Usage:  @role_required("owner", "store")
    """
    def decorator(f):
        @wraps(f)
        @login_required
        def wrapped(*args, **kwargs):
            if current_user.role not in roles:
                flash("You do not have permission to access this page.", "danger")
                return redirect(url_for("dashboard.index"))
            return f(*args, **kwargs)
        return wrapped
    return decorator


# ── Login ──────────────────────────────────────────────────
@bp.route("/login", methods=["GET", "POST"])
def login():
    """Show the login form and authenticate the user."""
    # If already logged in, go to dashboard
    if current_user.is_authenticated:
        return redirect(url_for("dashboard.index"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        if not username or not password:
            flash("Please enter both username and password.", "warning")
            return render_template("auth/login.html")

        user = User.query.filter_by(username=username).first()

        if user and check_password_hash(user.password_hash, password):
            login_user(user)
            flash(f"Welcome back, {user.name}!", "success")
            # Buyer goes to portal, everyone else to dashboard
            if user.role == "buyer":
                return redirect(url_for("buyer.index"))
            return redirect(url_for("dashboard.index"))
        else:
            flash("Invalid username or password.", "danger")

    return render_template("auth/login.html")


# ── Logout ─────────────────────────────────────────────────
@bp.route("/logout")
@login_required
def logout():
    """Log the user out and redirect to login page."""
    logout_user()
    flash("You have been logged out.", "info")
    return redirect(url_for("auth.login"))
