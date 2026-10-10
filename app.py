"""
app.py – Flask application factory for Warpspeed ERP.
WHAT IT DOES:
  Constructs and configures the Flask application, initializes the database,
  registers WAL (Write-Ahead Logging) pragmas for SQLite, and provides the
  main entry point.
WHY IT EXISTS:
  Using the Application Factory pattern (`create_app`) allows running the app
  in development mode, testing environments, or background jobs cleanly without
  global state conflicts.
"""

from flask import Flask, jsonify, render_template_string
from sqlalchemy import event
from extensions import db, login_manager
import config


def create_app(test_config=None) -> Flask:
    """
    WHAT: Creates and configures an instance of the Flask application.
    WHY: Encapsulates app creation so tests can pass isolated configs while
         normal execution uses config.py.
    """
    app = Flask(__name__)

    # ── Load Configuration ─────────────────────────────────────────────
    # Load defaults from config.py
    app.config.from_object(config)

    # Override with test configuration if provided
    if test_config:
        app.config.update(test_config)

    # ── Initialize Extensions ──────────────────────────────────────────
    db.init_app(app)
    login_manager.init_app(app)

    # ── Configure SQLite for Concurrency & Integrity ───────────────────
    # With SQLite, WAL mode allows multiple readers and one writer concurrently.
    with app.app_context():
        # Import models so SQLAlchemy knows all tables before db.create_all()
        import models  # noqa: F401

        @event.listens_for(db.engine, "connect")
        def set_sqlite_pragmas(dbapi_connection, connection_record):
            """
            WHAT: Runs SQLite PRAGMA settings whenever a connection is opened.
            WHY: Enables WAL (Write-Ahead Logging) for safe concurrent reads/writes
                 and turns ON foreign key enforcement.
            """
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

        # Ensure all tables exist in the database
        db.create_all()

    # ── Simple Home / Health Check Route ───────────────────────────────
    @app.route("/")
    def index():
        """
        WHAT: Default landing page for the prototype.
        WHY: Confirms the server is running and displays mill summary counts.
        """
        from models import User, Material, Order, Machine, FabricRoll

        user_count = User.query.count()
        mat_count = Material.query.count()
        order_count = Order.query.count()
        machine_count = Machine.query.count()
        roll_count = FabricRoll.query.count()

        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Warpspeed Mini-ERP</title>
            <style>
                body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                        max-width: 800px; margin: 40px auto; padding: 20px; line-height: 1.6; color: #222; }}
                h1 {{ color: #1e3a8a; border-bottom: 2px solid #e2e8f0; padding-bottom: 10px; }}
                .card {{ background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; padding: 18px; margin-bottom: 16px; }}
                .stat-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(130px, 1fr)); gap: 12px; margin-top: 15px; }}
                .stat-box {{ background: white; border: 1px solid #cbd5e1; border-radius: 6px; padding: 12px; text-align: center; }}
                .stat-val {{ font-size: 24px; font-weight: bold; color: #0284c7; }}
                .stat-label {{ font-size: 12px; color: #64748b; text-transform: uppercase; }}
                .badge {{ display: inline-block; padding: 4px 10px; border-radius: 999px; background: #dcfce7; color: #166534; font-weight: 600; font-size: 13px; }}
                code {{ background: #f1f5f9; padding: 2px 6px; border-radius: 4px; font-size: 13px; }}
            </style>
        </head>
        <body>
            <h1>🏭 Everest Textile Mills &mdash; Warpspeed ERP</h1>
            <p><span class="badge">● Prototype Online (SQLite WAL mode)</span></p>
            <div class="card">
                <h3>Live System Counts</h3>
                <div class="stat-grid">
                    <div class="stat-box"><div class="stat-val">{user_count}</div><div class="stat-label">Users</div></div>
                    <div class="stat-box"><div class="stat-val">{mat_count}</div><div class="stat-label">Materials</div></div>
                    <div class="stat-box"><div class="stat-val">{machine_count}</div><div class="stat-label">Machines</div></div>
                    <div class="stat-box"><div class="stat-val">{order_count}</div><div class="stat-label">Orders</div></div>
                    <div class="stat-box"><div class="stat-val">{roll_count}</div><div class="stat-label">Fabric Rolls</div></div>
                </div>
            </div>
            <div class="card">
                <h3>Demo Credentials</h3>
                <p>All users share password: <code>demo123</code></p>
                <ul>
                    <li><strong>Owner:</strong> <code>owner</code> (Full factory oversight)</li>
                    <li><strong>Store Manager:</strong> <code>store</code> (Raw material inventory & dispatch)</li>
                    <li><strong>Supervisor:</strong> <code>supervisor</code> (Shop floor production)</li>
                    <li><strong>QC Inspector:</strong> <code>qc</code> (Roll grading & defects)</li>
                    <li><strong>Buyer Client:</strong> <code>buyer</code> (Order tracking)</li>
                </ul>
            </div>
        </body>
        </html>
        """
        return render_template_string(html)

    return app


# ── Direct Execution ───────────────────────────────────────────────────────
if __name__ == "__main__":
    # WHAT: Starts the local development server when run as a script.
    # WHY: Provides an instant web server at http://127.0.0.1:5000 for local testing.
    application = create_app()
    application.run(debug=True, port=5000)
