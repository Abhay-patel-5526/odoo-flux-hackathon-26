from datetime import date
from decimal import Decimal

from flask import (
    Blueprint,
    abort,
    render_template,
    request,
)
from flask_login import current_user, login_required
from sqlalchemy.orm import joinedload, selectinload

from models import Customer, Invoice, Subscription
from permissions import customer_required


portal_bp = Blueprint("portal", __name__)


def get_current_customer():
    """
    Return the customer profile belonging to the logged-in customer.

    A customer account without a linked profile cannot access the portal.
    """
    customer = current_user.customer_profile

    if not customer:
        abort(404)

    return customer


def get_customer_invoices(customer_id):
    """
    Return invoices belonging only to the specified customer.

    Draft invoices are excluded from the customer portal.
    """
    return (
        Invoice.query
        .options(
            joinedload(Invoice.customer).joinedload(Customer.user),
            joinedload(Invoice.subscription),
            selectinload(Invoice.lines),
            selectinload(Invoice.payments),
        )
        .filter(
            Invoice.customer_id == customer_id,
            Invoice.status != "draft",
        )
    )


@portal_bp.route("/", methods=["GET"])
@login_required
@customer_required
def dashboard():
    customer = get_current_customer()

    subscriptions_query = Subscription.query.filter_by(
        customer_id=customer.id
    )

    total_subscriptions = subscriptions_query.count()

    active_subscriptions = subscriptions_query.filter_by(
        status="active"
    ).count()

    recent_subscriptions = (
        subscriptions_query
        .options(
            joinedload(Subscription.plan),
        )
        .order_by(Subscription.created_at.desc())
        .limit(5)
        .all()
    )

    invoice_query = get_customer_invoices(customer.id)

    total_invoices = invoice_query.count()

    recent_invoices = (
        invoice_query
        .order_by(Invoice.issue_date.desc(), Invoice.id.desc())
        .limit(5)
        .all()
    )

    all_invoices = invoice_query.all()

    outstanding_balance = sum(
        (
            invoice.outstanding_amount
            for invoice in all_invoices
        ),
        Decimal("0.00"),
    )

    return render_template(
        "portal/dashboard.html",
        active_subscriptions=active_subscriptions,
        total_subscriptions=total_subscriptions,
        total_invoices=total_invoices,
        outstanding_balance=outstanding_balance,
        recent_subscriptions=recent_subscriptions,
        recent_invoices=recent_invoices,
    )


@portal_bp.route("/subscriptions/", methods=["GET"])
@login_required
@customer_required
def subscriptions():
    customer = get_current_customer()

    subscriptions = (
        Subscription.query
        .options(
            joinedload(Subscription.plan),
        )
        .filter_by(customer_id=customer.id)
        .order_by(Subscription.created_at.desc())
        .all()
    )

    return render_template(
        "portal/subscriptions.html",
        subscriptions=subscriptions,
    )


@portal_bp.route("/invoices/", methods=["GET"])
@login_required
@customer_required
def invoices():
    customer = get_current_customer()

    search = request.args.get("search", "").strip()
    status = request.args.get("status", "").strip().lower()

    query = get_customer_invoices(customer.id)

    if search:
        query = query.filter(
            Invoice.number.ilike(f"%{search}%")
        )

    if status == "overdue":
        today = date.today()

        query = query.filter(
            Invoice.status.notin_(["paid", "cancelled", "draft"]),
            Invoice.due_date < today,
            Invoice.paid_amount < Invoice.total,
        )

    elif status in ("confirmed", "paid", "cancelled"):
        query = query.filter(Invoice.status == status)

    invoices = (
        query
        .order_by(Invoice.issue_date.desc(), Invoice.id.desc())
        .all()
    )

    return render_template(
        "portal/invoices.html",
        invoices=invoices,
    )


@portal_bp.route("/invoices/<int:invoice_id>/", methods=["GET"])
@login_required
@customer_required
def invoice_detail(invoice_id):
    customer = get_current_customer()

    invoice = (
        get_customer_invoices(customer.id)
        .filter(Invoice.id == invoice_id)
        .first()
    )

    if not invoice:
        abort(404)

    return render_template(
        "portal/invoice_detail.html",
        invoice=invoice,
    )