from datetime import date

from flask import (
    Blueprint,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)
from flask_login import login_required
from sqlalchemy import or_
from sqlalchemy.orm import joinedload

from models import BillingRecord, Customer, Invoice, Subscription
from permissions import staff_or_admin_required
from services.billing_service import generate_due_invoices


billing_bp = Blueprint("billing", __name__)


@billing_bp.route("/", methods=["GET"])
@login_required
@staff_or_admin_required
def dashboard():
    today = date.today()

    due_subscriptions = (
        Subscription.query
        .options(
            joinedload(Subscription.customer),
            joinedload(Subscription.plan),
        )
        .filter(
            Subscription.status == "active",
            Subscription.next_billing_date.isnot(None),
            Subscription.next_billing_date <= today,
        )
        .order_by(Subscription.next_billing_date.asc())
        .all()
    )

    generated_count = (
        Invoice.query
        .filter(
            Invoice.subscription_id.isnot(None),
            Invoice.issue_date == today,
        )
        .count()
    )

    total_records = BillingRecord.query.count()

    return render_template(
        "billing/dashboard.html",
        due_subscriptions=due_subscriptions,
        due_count=len(due_subscriptions),
        generated_count=generated_count,
        total_records=total_records,
    )


@billing_bp.route("/generate/", methods=["POST"])
@login_required
@staff_or_admin_required
def generate_invoices():
    try:
        result = generate_due_invoices()

        if result["generated_count"]:
            flash(
                f'{result["generated_count"]} invoice(s) generated successfully.',
                "success",
            )
        else:
            flash("No invoices were generated.", "info")

        if result["skipped_count"]:
            flash(
                f'{result["skipped_count"]} subscription(s) were skipped. '
                "Check their billing details.",
                "warning",
            )

    except Exception:
        flash(
            "Billing generation failed. No changes were committed. "
            "Please check the application logs.",
            "danger",
        )

    return redirect(url_for("billing.dashboard"))



@billing_bp.route("/history/", methods=["GET"])
@login_required
@staff_or_admin_required
def history():
    search = request.args.get("search", "").strip()

    query = (
        BillingRecord.query
        .join(BillingRecord.subscription)
        .options(
            joinedload(BillingRecord.subscription)
            .joinedload(Subscription.customer)
            .joinedload(Customer.user),
            joinedload(BillingRecord.invoice),
        )
    )

    if search:
        pattern = f"%{search}%"

        query = (
            query
            .join(Subscription.customer)
            .filter(
                or_(
                    Subscription.number.ilike(pattern),
                    Customer.company_name.ilike(pattern),
                )
            )
        )

    records = (
        query
        .order_by(BillingRecord.created_at.desc())
        .all()
    )

    return render_template(
        "billing/history.html",
        records=records,
    )
