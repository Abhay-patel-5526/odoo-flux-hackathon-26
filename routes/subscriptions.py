from datetime import date, datetime
from uuid import uuid4

from flask import (
    Blueprint,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)
from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError

from extensions import db
from models import (
    Customer,
    Plan,
    Subscription,
    SubscriptionLine,
    User,
)
from permissions import admin_required, staff_or_admin_required


subscriptions_bp = Blueprint("subscriptions", __name__)


# --------------------------------------------------
# Constants
# --------------------------------------------------

SUBSCRIPTION_STATUSES = {
    "draft",
    "quotation",
    "confirmed",
    "active",
    "paused",
    "closed",
    "cancelled",
}

CURRENCIES = {"INR", "USD", "EUR", "GBP"}

STATUS_TRANSITIONS = {
    "draft": {"quotation", "cancelled"},
    "quotation": {"draft", "confirmed", "cancelled"},
    "confirmed": {"active", "cancelled"},
    "active": {"paused", "closed", "cancelled"},
    "paused": {"active", "closed", "cancelled"},
    "closed": set(),
    "cancelled": set(),
}


# --------------------------------------------------
# Helper functions
# --------------------------------------------------

def get_subscription_or_404(subscription_id):
    return db.get_or_404(Subscription, subscription_id)


def parse_date(value, field_name, required=False):
    value = (value or "").strip()

    if not value:
        if required:
            raise ValueError(f"{field_name} is required.")
        return None

    try:
        return date.fromisoformat(value)
    except ValueError:
        raise ValueError(f"Enter a valid {field_name.lower()}.")


def parse_non_negative_integer(value, field_name, default=0):
    value = (value or "").strip()

    if not value:
        return default

    try:
        number = int(value)
    except ValueError:
        raise ValueError(f"{field_name} must be a whole number.")

    if number < 0:
        raise ValueError(f"{field_name} cannot be negative.")

    return number


def generate_subscription_number():
    return f"SUB-{date.today():%Y%m%d}-{uuid4().hex[:6].upper()}"


def validate_subscription_dates(start_date, expiry_date, next_billing_date):
    if expiry_date and start_date and expiry_date < start_date:
        raise ValueError("Expiry date cannot be before the start date.")

    if next_billing_date and start_date and next_billing_date < start_date:
        raise ValueError("Next billing date cannot be before the start date.")

    if next_billing_date and expiry_date and next_billing_date > expiry_date:
        raise ValueError("Next billing date cannot be after the expiry date.")


def validate_plan_for_subscription(plan, start_date):
    if not plan.is_active:
        raise ValueError("This plan is inactive.")

    if not plan.product.is_active:
        raise ValueError("The product linked to this plan is inactive.")

    if plan.available_from and start_date < plan.available_from:
        raise ValueError("This plan is not available yet.")

    if plan.available_until and start_date > plan.available_until:
        raise ValueError("This plan is no longer available.")


def validate_status_transition(subscription, new_status):
    old_status = subscription.status

    if new_status not in SUBSCRIPTION_STATUSES:
        raise ValueError("Invalid subscription status.")

    if new_status == old_status:
        return

    allowed = STATUS_TRANSITIONS.get(old_status, set())

    if new_status not in allowed:
        raise ValueError(
            f"Cannot change subscription from {old_status.title()} "
            f"to {new_status.title()}."
        )

    if old_status == "active" and new_status == "paused":
        if not subscription.plan.allow_pause:
            raise ValueError("This plan does not allow pausing.")

    if new_status == "closed":
        if (
            subscription.expiry_date
            and subscription.expiry_date > date.today()
            and not subscription.plan.allow_early_close
        ):
            raise ValueError("This plan does not allow early closure.")

    if new_status in {"closed", "cancelled"}:
        subscription.closed_at = datetime.utcnow()

    elif old_status == "paused" and new_status == "active":
        subscription.closed_at = None

    subscription.status = new_status


def get_form_choices():
    customers = (
        Customer.query
        .join(User)
        .filter(
            User.role == "customer",
            User.is_active.is_(True),
        )
        .order_by(User.name.asc())
        .all()
    )

    plans = (
        Plan.query
        .join(Plan.product)
        .filter(
            Plan.is_active.is_(True),
        )
        .order_by(Plan.name.asc())
        .all()
    )

    return customers, plans


def get_form_values():
    customer_id = request.form.get("customer_id", type=int)
    plan_id = request.form.get("plan_id", type=int)

    if not customer_id:
        raise ValueError("Please select a customer.")

    if not plan_id:
        raise ValueError("Please select a plan.")

    customer = Customer.query.get(customer_id)
    plan = Plan.query.get(plan_id)

    if not customer or not customer.user:
        raise ValueError("Selected customer was not found.")

    if customer.user.role != "customer" or not customer.user.is_active:
        raise ValueError("Selected customer account is inactive.")

    if not plan:
        raise ValueError("Selected plan was not found.")

    start_date = parse_date(
        request.form.get("start_date"),
        "Start date",
        required=True,
    )

    expiry_date = parse_date(
        request.form.get("expiry_date"),
        "Expiry date",
    )

    next_billing_date = parse_date(
        request.form.get("next_billing_date"),
        "Next billing date",
    )

    validate_subscription_dates(
        start_date,
        expiry_date,
        next_billing_date,
    )

    validate_plan_for_subscription(plan, start_date)

    payment_terms_days = parse_non_negative_integer(
        request.form.get("payment_terms_days"),
        "Payment terms",
    )

    currency = request.form.get("currency", "INR").strip().upper()

    if currency not in CURRENCIES:
        raise ValueError("Select a supported currency.")

    notes = request.form.get("notes", "").strip()

    return {
        "customer": customer,
        "plan": plan,
        "start_date": start_date,
        "expiry_date": expiry_date,
        "next_billing_date": next_billing_date,
        "payment_terms_days": payment_terms_days,
        "currency": currency,
        "notes": notes or None,
    }


# --------------------------------------------------
# Subscription list
# --------------------------------------------------

@subscriptions_bp.get("/")
@staff_or_admin_required
def list_subscriptions():
    search = request.args.get("q", "").strip()
    status = request.args.get("status", "all").lower()

    query = Subscription.query.join(Customer).join(User)

    if status != "all":
        if status in SUBSCRIPTION_STATUSES:
            query = query.filter(Subscription.status == status)
        else:
            status = "all"

    if search:
        query = query.join(Subscription.plan).filter(
            or_(
                Subscription.number.ilike(f"%{search}%"),
                User.name.ilike(f"%{search}%"),
                Plan.name.ilike(f"%{search}%"),
            )
        )

    subscriptions = (
        query
        .order_by(Subscription.created_at.desc())
        .all()
    )

    return render_template(
        "subscriptions/list.html",
        subscriptions=subscriptions,
        search=search,
        status=status,
    )


# --------------------------------------------------
# Create subscription
# --------------------------------------------------

@subscriptions_bp.route("/new", methods=["GET", "POST"])
@admin_required
def create_subscription():
    customers, plans = get_form_choices()

    if request.method == "POST":
        try:
            values = get_form_values()

            subscription = Subscription(
                number=generate_subscription_number(),
                customer=values["customer"],
                plan=values["plan"],
                status="draft",
                start_date=values["start_date"],
                expiry_date=values["expiry_date"],
                next_billing_date=(
                    values["next_billing_date"] or values["start_date"]
                ),
                payment_terms_days=values["payment_terms_days"],
                currency=values["currency"],
                notes=values["notes"],
            )

            db.session.add(subscription)
            db.session.flush()

            # Create the first subscription line from the selected plan.
            line = SubscriptionLine(
                subscription=subscription,
                product=values["plan"].product,
                quantity=values["plan"].minimum_quantity,
                unit_price=values["plan"].price,
                description=values["plan"].name,
            )

            db.session.add(line)
            db.session.commit()

            flash("Subscription created successfully.", "success")

            return redirect(
                url_for(
                    "subscriptions.subscription_detail",
                    subscription_id=subscription.id,
                )
            )

        except ValueError as error:
            db.session.rollback()
            flash(str(error), "danger")

        except IntegrityError:
            db.session.rollback()
            flash("Could not create subscription. Please try again.", "danger")

    return render_template(
        "subscriptions/form.html",
        subscription=None,
        customers=customers,
        plans=plans,
        is_edit=False,
    )


# --------------------------------------------------
# Subscription details
# --------------------------------------------------

@subscriptions_bp.get("/<int:subscription_id>")
@staff_or_admin_required
def subscription_detail(subscription_id):
    subscription = get_subscription_or_404(subscription_id)

    return render_template(
        "subscriptions/detail.html",
        subscription=subscription,
    )


# --------------------------------------------------
# Edit subscription
# --------------------------------------------------

@subscriptions_bp.route("/<int:subscription_id>/edit", methods=["GET", "POST"])
@admin_required
def edit_subscription(subscription_id):
    subscription = get_subscription_or_404(subscription_id)
    customers, plans = get_form_choices()

    if request.method == "POST":
        try:
            values = get_form_values()

            # Do not change customer or plan after invoices exist.
            if subscription.invoices and (
                subscription.customer_id != values["customer"].id
                or subscription.plan_id != values["plan"].id
            ):
                raise ValueError(
                    "Customer and plan cannot be changed after invoices exist."
                )

            subscription.customer = values["customer"]
            subscription.plan = values["plan"]
            subscription.start_date = values["start_date"]
            subscription.expiry_date = values["expiry_date"]
            subscription.next_billing_date = (
                values["next_billing_date"] or values["start_date"]
            )
            subscription.payment_terms_days = values["payment_terms_days"]
            subscription.currency = values["currency"]
            subscription.notes = values["notes"]

            new_status = request.form.get("status", subscription.status).lower()

            validate_status_transition(subscription, new_status)

            # Keep the first line aligned with the selected plan.
            if not subscription.invoices and subscription.lines:
                first_line = subscription.lines[0]
                first_line.product = values["plan"].product
                first_line.quantity = values["plan"].minimum_quantity
                first_line.unit_price = values["plan"].price
                first_line.description = values["plan"].name

            db.session.commit()

            flash("Subscription updated successfully.", "success")

            return redirect(
                url_for(
                    "subscriptions.subscription_detail",
                    subscription_id=subscription.id,
                )
            )

        except ValueError as error:
            db.session.rollback()
            flash(str(error), "danger")

        except IntegrityError:
            db.session.rollback()
            flash("Could not update subscription. Please try again.", "danger")

    return render_template(
        "subscriptions/form.html",
        subscription=subscription,
        customers=customers,
        plans=plans,
        is_edit=True,
    )


# --------------------------------------------------
# Update subscription status
# --------------------------------------------------

@subscriptions_bp.post("/<int:subscription_id>/status")
@admin_required
def update_subscription_status(subscription_id):
    subscription = get_subscription_or_404(subscription_id)
    new_status = request.form.get("status", "").strip().lower()

    try:
        validate_status_transition(subscription, new_status)
        db.session.commit()

        flash(
            f"Subscription status updated to {new_status.title()}.",
            "success",
        )

    except ValueError as error:
        db.session.rollback()
        flash(str(error), "danger")

    return redirect(
        url_for(
            "subscriptions.subscription_detail",
            subscription_id=subscription.id,
        )
    )