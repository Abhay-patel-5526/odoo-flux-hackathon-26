
from datetime import date

from flask import Blueprint, jsonify, redirect, render_template, url_for
from flask_login import current_user, login_required
from sqlalchemy import func

from extensions import db
from models import (
    Customer,
    Invoice,
    Payment,
    Plan,
    Product,
    Subscription,
    User,
)

dashboard_bp = Blueprint("dashboard", __name__)


def get_business_stats():
    """Statistics shared by admin and staff dashboards."""

    today = date.today()
    month_start = today.replace(day=1)

    total_customers = Customer.query.count()

    active_subscriptions = Subscription.query.filter_by(
        status="active"
    ).count()

    total_products = Product.query.filter_by(
        is_active=True
    ).count()

    total_plans = Plan.query.filter_by(
        is_active=True
    ).count()

    pending_invoices = Invoice.query.filter(
        Invoice.status.in_(["draft", "confirmed"]),
        Invoice.total > Invoice.paid_amount,
    ).count()

    overdue_invoices = Invoice.query.filter(
        Invoice.status.notin_(["paid", "cancelled"]),
        Invoice.due_date < today,
        Invoice.total > Invoice.paid_amount,
    ).count()

    monthly_revenue = (
        db.session.query(func.coalesce(func.sum(Payment.amount), 0))
        .filter(
            Payment.status == "completed",
            Payment.payment_date >= month_start,
            Payment.payment_date <= today,
        )
        .scalar()
    )

    recent_subscriptions = (
        Subscription.query
        .join(Customer)
        .order_by(Subscription.created_at.desc())
        .limit(5)
        .all()
    )

    return {
        "total_customers": total_customers,
        "active_subscriptions": active_subscriptions,
        "total_products": total_products,
        "total_plans": total_plans,
        "pending_invoices": pending_invoices,
        "overdue_invoices": overdue_invoices,
        "monthly_revenue": monthly_revenue,
        "recent_subscriptions": recent_subscriptions,
    }


# -----------------------------------------
# Common dashboard entry point
# -----------------------------------------

@dashboard_bp.get("/")
@login_required
def index():

    if current_user.role == "admin":
        return redirect(url_for("dashboard.admin"))

    if current_user.role == "staff":
        return redirect(url_for("dashboard.staff"))

    if current_user.role == "customer":
        return redirect(url_for("dashboard.customer"))

    return "Invalid user role", 403


# -----------------------------------------
# Admin dashboard
# -----------------------------------------

@dashboard_bp.get("/admin")
@login_required
def admin():

    if current_user.role != "admin":
        return "Access denied", 403

    stats = get_business_stats()

    return render_template(
        "dashboard/admin.html",
        stats=stats,
    )


# -----------------------------------------
# Staff dashboard
# -----------------------------------------

@dashboard_bp.get("/staff")
@login_required
def staff():

    if current_user.role not in ("admin", "staff"):
        return "Access denied", 403

    stats = get_business_stats()

    return render_template(
        "dashboard/staff.html",
        stats=stats,
    )


# -----------------------------------------
# Customer dashboard
# -----------------------------------------

@dashboard_bp.get("/customer")
@login_required
def customer():

    if current_user.role != "customer":
        return "Access denied", 403

    customer_profile = current_user.customer_profile

    if customer_profile:
        subscriptions = customer_profile.subscriptions
        invoices = customer_profile.invoices

        active_subscriptions = [
            subscription
            for subscription in subscriptions
            if subscription.status == "active"
        ]

        pending_invoices = [
            invoice
            for invoice in invoices
            if invoice.status not in ("paid", "cancelled")
            and invoice.outstanding_amount > 0
        ]

        recent_invoices = sorted(
            invoices,
            key=lambda invoice: invoice.issue_date,
            reverse=True,
        )[:5]

    else:
        active_subscriptions = []
        pending_invoices = []
        recent_invoices = []

    return render_template(
        "dashboard/customer.html",
        active_subscriptions=active_subscriptions,
        pending_invoices=pending_invoices,
        recent_invoices=recent_invoices,
    )


# -----------------------------------------
# Dashboard JSON summary
# -----------------------------------------

@dashboard_bp.get("/summary")
@login_required
def summary():

    if current_user.role not in ("admin", "staff"):
        return jsonify({"error": "Access denied"}), 403

    stats = get_business_stats()

    return jsonify({
        "total_customers": stats["total_customers"],
        "active_subscriptions": stats["active_subscriptions"],
        "total_products": stats["total_products"],
        "total_plans": stats["total_plans"],
        "pending_invoices": stats["pending_invoices"],
        "overdue_invoices": stats["overdue_invoices"],
        "monthly_revenue": str(stats["monthly_revenue"]),
    })
