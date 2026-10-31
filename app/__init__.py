from flask import Flask, jsonify, redirect, url_for
from flask_login import current_user
from config import DevelopmentConfig, ProductionConfig
from extensions import csrf, db, login_manager, migrate
from datetime import datetime
from routes.quotations import quotations_bp
from routes.auth import auth_bp
from routes.invoices import invoices_bp
from routes.billing import billing_bp
from routes.portal import portal_bp

def create_app(config_object=None):
    app = Flask(
    __name__,
    template_folder="../templates",
    static_folder="../static",
    instance_relative_config=True)

    if config_object is None:
        config_object = ProductionConfig if __import__("os").getenv("FLASK_DEBUG") == "0" else DevelopmentConfig
    app.config.from_object(config_object)

    # Ensure the instance folder exists before SQLite opens its database file.
    from pathlib import Path
    Path(app.instance_path).mkdir(parents=True, exist_ok=True)

    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    csrf.init_app(app)

    # Import models so SQLAlchemy knows every table before migrations/create_all.
    from models import (  # noqa: F401
        User, Customer, Product, ProductVariant, Plan, TaxRule,
        QuotationTemplate, QuotationTemplateLine, Subscription,
        SubscriptionLine, Invoice, InvoiceLine, BillingRecord,
        Discount, DiscountUsage, Payment, CompanySetting,
    )

    @app.get("/")
    def index():
        if current_user.is_authenticated:
            return redirect(url_for("dashboard.index"))

        return redirect(url_for("auth.login"))

    @app.get("/health")
    def health():
        return jsonify({"status": "ok"})

    from routes.dashboard import dashboard_bp
    app.register_blueprint(dashboard_bp, url_prefix="/dashboard")

    from routes.products import products_bp
    app.register_blueprint(products_bp, url_prefix="/products")

    from routes.plans import plans_bp
    app.register_blueprint(plans_bp, url_prefix="/plans")

    from routes.customers import customers_bp
    app.register_blueprint(customers_bp, url_prefix="/customers")

    from routes.subscriptions import subscriptions_bp
    app.register_blueprint(subscriptions_bp, url_prefix="/subscriptions")

    app.register_blueprint(
    billing_bp,
    url_prefix="/billing",)

    app.register_blueprint(
    portal_bp,
    url_prefix="/portal",)

    app.register_blueprint(
    invoices_bp,
    url_prefix="/invoices",)

    app.register_blueprint(
    quotations_bp,
    url_prefix="/quotations",)




    app.register_blueprint(auth_bp, url_prefix="/auth")

    app.add_template_global(datetime.now, "now")

    from cli import register_commands
    register_commands(app)

    return app
