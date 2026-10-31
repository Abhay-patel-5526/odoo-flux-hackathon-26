
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from uuid import uuid4

from flask import (
    Blueprint,
    abort,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)
from flask_login import login_required
from sqlalchemy import or_
from sqlalchemy.orm import joinedload, selectinload

from extensions import db
from models import (
    Customer,
    Invoice,
    InvoiceLine,
    Payment,
    Product,
    Subscription,
    TaxRule,
)
from permissions import staff_or_admin_required

from services.invoice_number import generate_invoice_number
from services.invoice_service import (
    apply_invoice_lines,
    calculate_invoice_totals,
    record_invoice_payment,
)


invoices_bp = Blueprint("invoices", __name__)


# =========================================
# HELPERS
# =========================================

def parse_decimal(value, field_name, default=None):
    try:
        if value is None or str(value).strip() == "":
            if default is not None:
                return Decimal(str(default))
            raise ValueError(f"{field_name} is required.")

        result = Decimal(str(value))

        if not result.is_finite():
            raise ValueError(f"{field_name} is invalid.")

        return result

    except InvalidOperation:
        raise ValueError(f"{field_name} must be a valid number.")


def parse_integer(value, field_name, minimum=1):
    try:
        result = int(value)
    except (TypeError, ValueError):
        raise ValueError(f"{field_name} must be a whole number.")

    if result < minimum:
        raise ValueError(f"{field_name} must be at least {minimum}.")

    return result


def parse_date(value, field_name):
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except (TypeError, ValueError):
        raise ValueError(f"{field_name} must be a valid date.")


def get_invoice_or_404(invoice_id):
    invoice = (
        Invoice.query
        .options(
            joinedload(Invoice.customer).joinedload(Customer.user),
            joinedload(Invoice.subscription),
            selectinload(Invoice.lines),
            selectinload(Invoice.payments),
        )
        .filter(Invoice.id == invoice_id)
        .first()
    )

    if invoice is None:
        abort(404)

    return invoice


def get_form_choices():
    customers = (
        Customer.query
        .join(Customer.user)
        .filter(Customer.user.has(is_active=True))
        .order_by(Customer.id.desc())
        .all()
    )

    products = (
        Product.query
        .filter_by(is_active=True)
        .order_by(Product.name)
        .all()
    )

    subscriptions = (
        Subscription.query
        .filter(Subscription.status.notin_(["closed", "cancelled"]))
        .order_by(Subscription.id.desc())
        .all()
    )

    tax_rules = (
        TaxRule.query
        .filter_by(is_active=True)
        .order_by(TaxRule.percentage)
        .all()
    )

    return customers, products, subscriptions, tax_rules


def get_invoice_lines_from_form():
    product_ids = request.form.getlist("product_id[]")
    descriptions = request.form.getlist("description[]")
    quantities = request.form.getlist("quantity[]")
    prices = request.form.getlist("unit_price[]")
    tax_percentages = request.form.getlist("tax_percentage[]")

    count = len(descriptions)

    if count == 0:
        raise ValueError("Add at least one invoice item.")

    if not (
        len(product_ids) == count
        and len(quantities) == count
        and len(prices) == count
        and len(tax_percentages) == count
    ):
        raise ValueError("Invoice item data is incomplete.")

    lines = []

    for index in range(count):
        description = descriptions[index].strip()

        if not description:
            raise ValueError("Every invoice item needs a description.")

        if len(description) > 255:
            raise ValueError("Item descriptions must be 255 characters or fewer.")

        quantity = parse_integer(quantities[index], "Quantity")
        unit_price = parse_decimal(prices[index], "Unit price")
        tax_percentage = parse_decimal(
            tax_percentages[index],
            "Tax percentage",
            default=0,
        )

        if unit_price < 0:
            raise ValueError("Unit price cannot be negative.")

        if tax_percentage < 0 or tax_percentage > 100:
            raise ValueError("Tax percentage must be between 0 and 100.")

        product = None
        product_id = product_ids[index].strip()

        if product_id:
            try:
                product_id = int(product_id)
            except ValueError:
                raise ValueError("Invalid product selected.")

            product = db.session.get(Product, product_id)

            if product is None:
                raise ValueError("Selected product does not exist.")

        line_subtotal = (
            Decimal(quantity) * unit_price
        ).quantize(Decimal("0.01"))

        line_tax = (
            line_subtotal * tax_percentage / Decimal("100")
        ).quantize(Decimal("0.01"))

        lines.append({
            "product": product,
            "description": description,
            "quantity": quantity,
            "unit_price": unit_price,
            "tax_percentage": tax_percentage,
            "line_subtotal": line_subtotal,
            "line_tax": line_tax,
        })

    return lines


def get_invoice_form_data():
    customer_id = request.form.get("customer_id", type=int)

    customer = db.session.get(Customer, customer_id) if customer_id else None

    if customer is None:
        raise ValueError("Select a valid customer.")

    subscription_id = request.form.get("subscription_id", type=int)
    subscription = None

    if subscription_id:
        subscription = db.session.get(Subscription, subscription_id)

        if subscription is None:
            raise ValueError("Selected subscription does not exist.")

        if subscription.customer_id != customer.id:
            raise ValueError("The subscription belongs to another customer.")

    issue_date = parse_date(
        request.form.get("issue_date"),
        "Issue date",
    )

    due_date = parse_date(
        request.form.get("due_date"),
        "Due date",
    )

    if due_date < issue_date:
        raise ValueError("Due date cannot be before issue date.")

    currency = request.form.get("currency", "INR").strip().upper()

    if currency not in ("INR", "USD", "EUR", "GBP"):
        raise ValueError("Unsupported currency.")

    notes = request.form.get("notes", "").strip()

    discount_amount = parse_decimal(
        request.form.get("discount_amount"),
        "Discount",
        default=0,
    )

    lines = get_invoice_lines_from_form()

    totals = calculate_invoice_totals(
        lines,
        discount_amount,
    )

    return {
        "customer": customer,
        "subscription": subscription,
        "issue_date": issue_date,
        "due_date": due_date,
        "currency": currency,
        "notes": notes,
        "lines": lines,
        **totals,
    }


def apply_invoice_data(invoice, data):
    invoice.customer = data["customer"]
    invoice.subscription = data["subscription"]
    invoice.issue_date = data["issue_date"]
    invoice.due_date = data["due_date"]
    invoice.subtotal = data["subtotal"]
    invoice.discount_amount = data["discount_amount"]
    invoice.tax_amount = data["tax_amount"]
    invoice.total = data["total"]
    invoice.notes = data["notes"]

    apply_invoice_lines(invoice, data["lines"])


def get_invoice_status(invoice):
    if invoice.status == "confirmed" and invoice.is_overdue:
        return "overdue"

    return invoice.status


# =========================================
# INVOICE LIST
# =========================================

@invoices_bp.get("/")
@login_required
@staff_or_admin_required
def list_invoices():
    search = request.args.get("q", "").strip()
    status = request.args.get("status", "all").strip()

    query = (
        Invoice.query
        .join(Invoice.customer)
        .join(Customer.user)
        .options(
            joinedload(Invoice.customer).joinedload(Customer.user),
            selectinload(Invoice.payments),
        )
    )

    if search:
        query = query.filter(
            or_(
                Invoice.number.ilike(f"%{search}%"),
                Customer.company_name.ilike(f"%{search}%"),
                Customer.user.has(
                    Customer.user.property.mapper.class_.name.ilike(
                        f"%{search}%"
                    )
                ),
            )
        )

    invoices = query.order_by(Invoice.created_at.desc()).all()

    if status == "overdue":
        invoices = [
            invoice for invoice in invoices
            if invoice.is_overdue
        ]
    elif status != "all":
        invoices = [
            invoice for invoice in invoices
            if invoice.status == status
        ]

    return render_template(
        "invoices/list.html",
        invoices=invoices,
        search=search,
        status=status,
    )


# =========================================
# CREATE INVOICE
# =========================================

@invoices_bp.route("/new", methods=["GET", "POST"])
@login_required
@staff_or_admin_required
def create_invoice():
    customers, products, subscriptions, tax_rules = get_form_choices()

    if request.method == "POST":
        try:
            data = get_invoice_form_data()

            invoice = Invoice(
                number=generate_invoice_number(),
                status="draft",
            )

            apply_invoice_data(invoice, data)

            db.session.add(invoice)
            db.session.commit()

            flash("Invoice created successfully.", "success")

            return redirect(
                url_for(
                    "invoices.invoice_detail",
                    invoice_id=invoice.id,
                )
            )

        except ValueError as error:
            db.session.rollback()
            flash(str(error), "danger")

        except Exception:
            db.session.rollback()
            raise

    return render_template(
        "invoices/form.html",
        invoice=None,
        is_edit=False,
        customers=customers,
        products=products,
        subscriptions=subscriptions,
        tax_rules=tax_rules,
        today=date.today(),
        default_due_date=date.today() + timedelta(days=15),
        selected_customer_id=request.args.get("customer_id", type=int),
    )


# =========================================
# INVOICE DETAIL
# =========================================

@invoices_bp.get("/<int:invoice_id>")
@login_required
@staff_or_admin_required
def invoice_detail(invoice_id):
    invoice = get_invoice_or_404(invoice_id)

    return render_template(
        "invoices/detail.html",
        invoice=invoice,
        today=date.today(),
        display_status=get_invoice_status(invoice),
    )


# =========================================
# EDIT DRAFT INVOICE
# =========================================

@invoices_bp.route("/<int:invoice_id>/edit", methods=["GET", "POST"])
@login_required
@staff_or_admin_required
def edit_invoice(invoice_id):
    invoice = get_invoice_or_404(invoice_id)

    if invoice.status != "draft":
        flash("Only draft invoices can be edited.", "warning")
        return redirect(
            url_for("invoices.invoice_detail", invoice_id=invoice.id)
        )

    customers, products, subscriptions, tax_rules = get_form_choices()

    if request.method == "POST":
        try:
            data = get_invoice_form_data()

            apply_invoice_data(invoice, data)

            db.session.commit()

            flash("Invoice updated successfully.", "success")

            return redirect(
                url_for("invoices.invoice_detail", invoice_id=invoice.id)
            )

        except ValueError as error:
            db.session.rollback()
            flash(str(error), "danger")

            invoice = get_invoice_or_404(invoice_id)

        except Exception:
            db.session.rollback()
            raise

    return render_template(
        "invoices/form.html",
        invoice=invoice,
        is_edit=True,
        customers=customers,
        products=products,
        subscriptions=subscriptions,
        tax_rules=tax_rules,
        today=date.today(),
        default_due_date=invoice.due_date,
        selected_customer_id=invoice.customer_id,
    )


# =========================================
# ISSUE / CONFIRM INVOICE
# =========================================

@invoices_bp.post("/<int:invoice_id>/issue")
@login_required
@staff_or_admin_required
def issue_invoice(invoice_id):
    invoice = get_invoice_or_404(invoice_id)

    if invoice.status != "draft":
        flash("Only draft invoices can be issued.", "warning")
        return redirect(
            url_for("invoices.invoice_detail", invoice_id=invoice.id)
        )

    if not invoice.lines:
        flash("An invoice must contain at least one item.", "danger")
        return redirect(
            url_for("invoices.invoice_detail", invoice_id=invoice.id)
        )

    if invoice.total <= 0:
        flash("Invoice total must be greater than zero.", "danger")
        return redirect(
            url_for("invoices.invoice_detail", invoice_id=invoice.id)
        )

    invoice.status = "confirmed"

    db.session.commit()

    flash("Invoice issued successfully.", "success")

    return redirect(
        url_for("invoices.invoice_detail", invoice_id=invoice.id)
    )


# =========================================
# RECORD PAYMENT
# =========================================

@invoices_bp.post("/<int:invoice_id>/payments")
@login_required
@staff_or_admin_required
def record_payment(invoice_id):
    invoice = get_invoice_or_404(invoice_id)

    try:
        amount = parse_decimal(
            request.form.get("amount"),
            "Payment amount",
        )

        payment_date = parse_date(
            request.form.get("payment_date"),
            "Payment date",
        )

        method = request.form.get("method", "").strip()

        allowed_methods = {
            "cash",
            "bank_transfer",
            "upi",
            "card",
            "cheque",
            "other",
        }

        if method not in allowed_methods:
            raise ValueError("Select a valid payment method.")

        reference = request.form.get("reference", "").strip()

        if not reference:
            reference = f"PAY-{uuid4().hex[:10].upper()}"

        note = request.form.get("note", "").strip()

        record_invoice_payment(
            invoice=invoice,
            reference=reference,
            amount=amount,
            method=method,
            payment_date=payment_date,
            note=note or None,
        )

        db.session.commit()

        flash("Payment recorded successfully.", "success")

    except ValueError as error:
        db.session.rollback()
        flash(str(error), "danger")

    except Exception:
        db.session.rollback()
        raise

    return redirect(
        url_for("invoices.invoice_detail", invoice_id=invoice.id)
    )
