from datetime import date, timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from uuid import uuid4
from flask import abort

from flask import (
    Blueprint,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)
from flask_login import current_user
from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import joinedload

from extensions import db
from models import (
    Customer,
    User,
    Product,
    Plan,
    TaxRule,
    Quotation,
    QuotationLine,
    QuotationTemplate,
    QuotationTemplateLine,
)
from permissions import admin_required, staff_or_admin_required


quotations_bp = Blueprint("quotations", __name__)


# =========================================
# CONSTANTS
# =========================================

QUOTATION_STATUSES = {
    "draft",
    "sent",
    "accepted",
    "rejected",
    "expired",
    "cancelled",
}

CURRENCIES = {"INR", "USD", "EUR", "GBP"}

MONEY_ZERO = Decimal("0.00")
MONEY_CENT = Decimal("0.01")

STATUS_TRANSITIONS = {
    "draft": {"sent", "cancelled"},
    "sent": {"accepted", "rejected", "cancelled", "expired"},
    "accepted": set(),
    "rejected": set(),
    "expired": set(),
    "cancelled": set(),
}







def get_quotation(quotation_id):
    quotation = db.session.get(Quotation, quotation_id)

    if quotation is None:
        abort(404)

    return quotation


# =========================================
# GENERAL HELPERS
# =========================================

def money(value):
    """Convert a value into a two-decimal Decimal."""
    return Decimal(str(value)).quantize(
        MONEY_CENT,
        rounding=ROUND_HALF_UP,
    )


def parse_decimal(value, field_name, minimum=None, maximum=None):
    value = (value or "").strip()

    if not value:
        raise ValueError(f"{field_name} is required.")

    try:
        number = Decimal(value)
    except InvalidOperation:
        raise ValueError(f"Enter a valid {field_name.lower()}.")

    if not number.is_finite():
        raise ValueError(f"Enter a valid {field_name.lower()}.")

    if minimum is not None and number < minimum:
        raise ValueError(f"{field_name} cannot be negative.")

    if maximum is not None and number > maximum:
        raise ValueError(f"{field_name} cannot exceed {maximum}.")

    return number


def parse_integer(value, field_name, minimum=1):
    value = (value or "").strip()

    try:
        number = int(value)
    except (TypeError, ValueError):
        raise ValueError(f"{field_name} must be a whole number.")

    if number < minimum:
        raise ValueError(f"{field_name} must be at least {minimum}.")

    return number


def parse_date(value, field_name):
    value = (value or "").strip()

    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError):
        raise ValueError(f"Enter a valid {field_name.lower()}.")


def generate_quotation_number():
    return (
        f"QUO-{date.today():%Y%m%d}-"
        f"{uuid4().hex[:6].upper()}"
    )


def get_quotation_or_404(quotation_id):
    return db.get_or_404(Quotation, quotation_id)


def get_template_or_404(template_id):
    return db.get_or_404(QuotationTemplate, template_id)


# =========================================
# EXPIRY MANAGEMENT
# =========================================

def expire_quotation_if_needed(quotation):
    if (
        quotation.status == "sent"
        and quotation.valid_until < date.today()
    ):
        quotation.status = "expired"
        return True

    return False


# =========================================
# STATUS MANAGEMENT
# =========================================

def validate_status_transition(quotation, new_status):
    old_status = quotation.status

    if new_status not in QUOTATION_STATUSES:
        raise ValueError("Invalid quotation status.")

    if new_status == old_status:
        return

    allowed = STATUS_TRANSITIONS.get(old_status, set())

    if new_status not in allowed:
        raise ValueError(
            f"Cannot change quotation from {old_status.title()} "
            f"to {new_status.title()}."
        )

    if new_status == "sent":
        if quotation.valid_until < date.today():
            raise ValueError(
                "An expired quotation cannot be sent."
            )

        if not quotation.lines:
            raise ValueError(
                "A quotation must contain at least one product line."
            )

    if new_status == "accepted":
        if quotation.valid_until < date.today():
            quotation.status = "expired"
            raise ValueError(
                "This quotation has expired and cannot be accepted."
            )

    quotation.status = new_status


# =========================================
# FORM CHOICES
# =========================================

def get_quotation_form_choices():
    customers = (
        Customer.query
        .join(Customer.user)
        .filter(
            User.role == "customer",
            User.is_active.is_(True),
        )
        .order_by(User.name.asc())
        .all()
    )

    products = (
        Product.query
        .filter(Product.is_active.is_(True))
        .order_by(Product.name.asc())
        .all()
    )

    tax_rules = (
        TaxRule.query
        .filter(TaxRule.is_active.is_(True))
        .order_by(TaxRule.name.asc())
        .all()
    )

    quotation_templates = (
        QuotationTemplate.query
        .filter(QuotationTemplate.is_active.is_(True))
        .order_by(QuotationTemplate.name.asc())
        .all()
    )

    return customers, products, tax_rules, quotation_templates


def get_template_form_choices():
    products = (
        Product.query
        .filter(Product.is_active.is_(True))
        .order_by(Product.name.asc())
        .all()
    )

    plans = (
        Plan.query
        .join(Plan.product)
        .filter(
            Plan.is_active.is_(True),
            Product.is_active.is_(True),
        )
        .order_by(Plan.name.asc())
        .all()
    )

    return products, plans


# =========================================
# QUOTATION LINE VALIDATION
# =========================================

def get_quotation_lines_from_form():
    product_ids = request.form.getlist("product_id[]")
    descriptions = request.form.getlist("description[]")
    quantities = request.form.getlist("quantity[]")
    unit_prices = request.form.getlist("unit_price[]")
    tax_percentages = request.form.getlist("tax_percentage[]")

    lengths = {
        len(product_ids),
        len(descriptions),
        len(quantities),
        len(unit_prices),
        len(tax_percentages),
    }

    if len(lengths) != 1:
        raise ValueError("Quotation product line data is incomplete.")

    if not product_ids:
        raise ValueError("Add at least one product line.")

    active_taxes = {
        Decimal(str(tax.percentage))
        for tax in TaxRule.query.filter(
            TaxRule.is_active.is_(True)
        ).all()
    }

    active_taxes.add(Decimal("0"))

    lines = []

    for index in range(len(product_ids)):
        product_id = (product_ids[index] or "").strip()
        description = (descriptions[index] or "").strip()

        if not description:
            raise ValueError(
                f"Description is required for line {index + 1}."
            )

        if len(description) > 255:
            raise ValueError(
                "Product descriptions cannot exceed 255 characters."
            )

        quantity = parse_integer(
            quantities[index],
            f"Quantity in line {index + 1}",
        )

        unit_price = parse_decimal(
            unit_prices[index],
            f"Unit price in line {index + 1}",
            minimum=MONEY_ZERO,
        )

        tax_percentage = parse_decimal(
            tax_percentages[index],
            f"Tax in line {index + 1}",
            minimum=Decimal("0"),
            maximum=Decimal("100"),
        )

        if tax_percentage not in active_taxes:
            raise ValueError(
                f"Tax rate {tax_percentage}% is not an active tax rule."
            )

        product = None

        if product_id:
            try:
                product_id = int(product_id)
            except ValueError:
                raise ValueError("Invalid product selection.")

            product = db.session.get(Product, product_id)

            if not product or not product.is_active:
                raise ValueError(
                    f"Selected product in line {index + 1} is unavailable."
                )

        line_subtotal = money(quantity * unit_price)

        line_tax = money(
            line_subtotal * tax_percentage / Decimal("100")
        )

        lines.append({
            "product": product,
            "description": description,
            "quantity": quantity,
            "unit_price": money(unit_price),
            "tax_percentage": tax_percentage,
            "line_subtotal": line_subtotal,
            "line_tax": line_tax,
        })

    return lines


def calculate_quotation_totals(lines, discount_amount):
    subtotal = money(sum(
        (line["line_subtotal"] for line in lines),
        MONEY_ZERO,
    ))

    original_tax = money(sum(
        (line["line_tax"] for line in lines),
        MONEY_ZERO,
    ))

    discount_amount = money(discount_amount)

    if discount_amount > subtotal:
        raise ValueError(
            "Discount cannot exceed the quotation subtotal."
        )

    # Allocate the discount proportionally across the taxable subtotal.
    if subtotal > MONEY_ZERO:
        taxable_ratio = (
            subtotal - discount_amount
        ) / subtotal
    else:
        taxable_ratio = Decimal("0")

    tax_amount = money(original_tax * taxable_ratio)

    total = money(
        subtotal - discount_amount + tax_amount
    )

    return {
        "subtotal": subtotal,
        "discount_amount": discount_amount,
        "tax_amount": tax_amount,
        "total": total,
    }


# =========================================
# QUOTATION FORM DATA
# =========================================

def get_quotation_form_data():
    customer_id = request.form.get("customer_id", type=int)

    if not customer_id:
        raise ValueError("Please select a customer.")

    customer = db.session.get(Customer, customer_id)

    if (
        not customer
        or not customer.user
        or customer.user.role != "customer"
        or not customer.user.is_active
    ):
        raise ValueError("Selected customer is unavailable.")

    template_id = request.form.get("template_id", "").strip()
    template = None

    if template_id:
        try:
            template_id = int(template_id)
        except ValueError:
            raise ValueError("Invalid quotation template.")

        template = db.session.get(
            QuotationTemplate,
            template_id,
        )

        if not template or not template.is_active:
            raise ValueError("Selected quotation template is unavailable.")

    issue_date = parse_date(
        request.form.get("issue_date"),
        "Issue date",
    )

    valid_until = parse_date(
        request.form.get("valid_until"),
        "Valid until date",
    )

    if valid_until < issue_date:
        raise ValueError(
            "Valid until date cannot be before the issue date."
        )

    if valid_until < date.today():
        raise ValueError(
            "A new quotation cannot have an expiry date in the past."
        )

    currency = request.form.get("currency", "INR").strip().upper()

    if currency not in CURRENCIES:
        raise ValueError("Select a supported currency.")

    notes = request.form.get("notes", "").strip()

    if len(notes) > 10000:
        raise ValueError("Notes are too long.")

    lines = get_quotation_lines_from_form()

    discount_amount = parse_decimal(
        request.form.get("discount_amount", "0"),
        "Discount",
        minimum=MONEY_ZERO,
    )

    totals = calculate_quotation_totals(
        lines,
        discount_amount,
    )

    return {
        "customer": customer,
        "template": template,
        "issue_date": issue_date,
        "valid_until": valid_until,
        "currency": currency,
        "notes": notes or None,
        "lines": lines,
        **totals,
    }


def apply_quotation_data(quotation, values):
    quotation.customer = values["customer"]
    quotation.template = values["template"]
    quotation.issue_date = values["issue_date"]
    quotation.valid_until = values["valid_until"]
    quotation.currency = values["currency"]
    quotation.notes = values["notes"]

    quotation.subtotal = values["subtotal"]
    quotation.discount_amount = values["discount_amount"]
    quotation.tax_amount = values["tax_amount"]
    quotation.total = values["total"]

    # Replace existing lines with the validated submitted lines.
    quotation.lines.clear()

    for item in values["lines"]:
        line = QuotationLine(
            product=item["product"],
            description=item["description"],
            quantity=item["quantity"],
            unit_price=item["unit_price"],
            tax_percentage=item["tax_percentage"],
            line_subtotal=item["line_subtotal"],
            line_tax=item["line_tax"],
        )

        quotation.lines.append(line)


# =========================================
# QUOTATION LIST
# =========================================

@quotations_bp.get("/")
@staff_or_admin_required
def list_quotations():
    search = request.args.get("q", "").strip()
    status = request.args.get("status", "all").lower()

    query = (
        Quotation.query
        .join(Quotation.customer)
        .join(Customer.user)
        .options(
            joinedload(Quotation.customer).joinedload(Customer.user),
            joinedload(Quotation.lines),
        )
    )

    if status != "all":
        if status in QUOTATION_STATUSES:
            query = query.filter(Quotation.status == status)
        else:
            status = "all"

    if search:
        query = query.filter(
            or_(
                Quotation.number.ilike(f"%{search}%"),
                User.name.ilike(f"%{search}%"),
                Customer.company_name.ilike(f"%{search}%"),
            )
        )

    quotations = (
        query
        .order_by(Quotation.created_at.desc())
        .all()
    )

    changed = False

    for quotation in quotations:
        if expire_quotation_if_needed(quotation):
            changed = True

    if changed:
        db.session.commit()

    # Apply the status filter again after automatic expiry.
    if status != "all":
        quotations = [
            quotation
            for quotation in quotations
            if quotation.status == status
        ]

    return render_template(
        "quotations/list.html",
        quotations=quotations,
        search=search,
        status=status,
    )


# =========================================
# CREATE QUOTATION
# =========================================

@quotations_bp.route("/new", methods=["GET", "POST"])
@staff_or_admin_required
def create_quotation():
    customers, products, tax_rules, quotation_templates = (
        get_quotation_form_choices()
    )

    if request.method == "POST":
        try:
            values = get_quotation_form_data()

            quotation = Quotation(
                number=generate_quotation_number(),
                status="draft",
            )

            apply_quotation_data(quotation, values)

            db.session.add(quotation)
            db.session.commit()

            flash(
                "Quotation created successfully.",
                "success",
            )

            return redirect(
                url_for(
                    "quotations.quotation_detail",
                    quotation_id=quotation.id,
                )
            )

        except ValueError as error:
            db.session.rollback()
            flash(str(error), "danger")

        except IntegrityError:
            db.session.rollback()
            flash(
                "Could not create quotation. Please try again.",
                "danger",
            )

    return render_template(
        "quotations/form.html",
        quotation=None,
        customers=customers,
        products=products,
        tax_rules=tax_rules,
        quotation_templates=quotation_templates,
        today=date.today(),
        default_valid_until=date.today() + timedelta(days=15),
        selected_customer_id=request.form.get(
            "customer_id",
            type=int,
        ),
    )


# =========================================
# QUOTATION DETAIL
# =========================================

@quotations_bp.get("/<int:quotation_id>")
@staff_or_admin_required
def quotation_detail(quotation_id):
    quotation = (
        Quotation.query
        .options(
            joinedload(Quotation.customer).joinedload(Customer.user),
            joinedload(Quotation.template),
            joinedload(Quotation.lines),
        )
        .filter(Quotation.id == quotation_id)
        .first_or_404()
    )

    if expire_quotation_if_needed(quotation):
        db.session.commit()

    return render_template(
        "quotations/detail.html",
        quotation=quotation,
    )


# =========================================
# EDIT QUOTATION
# =========================================

@quotations_bp.route(
    "/<int:quotation_id>/edit",
    methods=["GET", "POST"],
)
@staff_or_admin_required
def edit_quotation(quotation_id):
    quotation = get_quotation_or_404(quotation_id)

    if expire_quotation_if_needed(quotation):
        db.session.commit()

    if quotation.status != "draft":
        flash(
            "Only draft quotations can be edited.",
            "warning",
        )

        return redirect(
            url_for(
                "quotations.quotation_detail",
                quotation_id=quotation.id,
            )
        )

    customers, products, tax_rules, quotation_templates = (
        get_quotation_form_choices()
    )

    if request.method == "POST":
        try:
            values = get_quotation_form_data()

            apply_quotation_data(quotation, values)

            db.session.commit()

            flash(
                "Quotation updated successfully.",
                "success",
            )

            return redirect(
                url_for(
                    "quotations.quotation_detail",
                    quotation_id=quotation.id,
                )
            )

        except ValueError as error:
            db.session.rollback()
            flash(str(error), "danger")

        except IntegrityError:
            db.session.rollback()
            flash(
                "Could not update quotation. Please try again.",
                "danger",
            )

    return render_template(
        "quotations/form.html",
        quotation=quotation,
        customers=customers,
        products=products,
        tax_rules=tax_rules,
        quotation_templates=quotation_templates,
        today=date.today(),
        default_valid_until=date.today() + timedelta(days=15),
        selected_customer_id=request.form.get(
            "customer_id",
            type=int,
        ),
    )


# =========================================
# SEND QUOTATION
# =========================================

@quotations_bp.post("/<int:quotation_id>/send")
@staff_or_admin_required
def send_quotation(quotation_id):
    quotation = get_quotation_or_404(quotation_id)

    try:
        expire_quotation_if_needed(quotation)

        if quotation.status != "draft":
            raise ValueError(
                "Only draft quotations can be sent."
            )

        validate_status_transition(quotation, "sent")

        db.session.commit()

        flash(
            "Quotation marked as sent successfully.",
            "success",
        )

    except ValueError as error:
        db.session.rollback()
        flash(str(error), "danger")

    return redirect(
        url_for(
            "quotations.quotation_detail",
            quotation_id=quotation.id,
        )
    )


# =========================================
# UPDATE QUOTATION STATUS
# =========================================

@quotations_bp.post("/<int:quotation_id>/status")
@staff_or_admin_required
def update_quotation_status(quotation_id):
    quotation = get_quotation_or_404(quotation_id)

    new_status = request.form.get(
        "status",
        "",
    ).strip().lower()

    try:
        expire_quotation_if_needed(quotation)

        # Only admin can cancel quotations.
        if (
            new_status == "cancelled"
            and current_user.role != "admin"
        ):
            raise ValueError(
                "Only administrators can cancel quotations."
            )

        validate_status_transition(
            quotation,
            new_status,
        )

        db.session.commit()

        flash(
            f"Quotation status updated to {new_status.title()}.",
            "success",
        )

    except ValueError as error:
        db.session.rollback()
        flash(str(error), "danger")

    return redirect(
        url_for(
            "quotations.quotation_detail",
            quotation_id=quotation.id,
        )
    )


# =========================================
# QUOTATION TEMPLATE LIST
# =========================================

@quotations_bp.get("/templates")
@admin_required
def list_templates():
    quotation_templates = (
        QuotationTemplate.query
        .options(
            joinedload(QuotationTemplate.lines)
            .joinedload(QuotationTemplateLine.product),
            joinedload(QuotationTemplate.lines)
            .joinedload(QuotationTemplateLine.plan),
        )
        .order_by(QuotationTemplate.created_at.desc())
        .all()
    )

    return render_template(
        "quotations/templates.html",
        quotation_templates=quotation_templates,
    )


# =========================================
# TEMPLATE FORM DATA
# =========================================

def get_template_form_data():
    name = request.form.get("name", "").strip()

    if not name:
        raise ValueError("Template name is required.")

    if len(name) > 180:
        raise ValueError("Template name is too long.")

    validity_days = parse_integer(
        request.form.get("validity_days"),
        "Validity days",
    )

    if validity_days > 3650:
        raise ValueError("Validity cannot exceed 3650 days.")

    notes = request.form.get("notes", "").strip()

    product_ids = request.form.getlist("product_id[]")
    plan_ids = request.form.getlist("plan_id[]")
    quantities = request.form.getlist("quantity[]")

    if not (
        len(product_ids)
        == len(plan_ids)
        == len(quantities)
    ):
        raise ValueError("Template product data is incomplete.")

    if not product_ids:
        raise ValueError(
            "Add at least one product to the template."
        )

    lines = []

    for index in range(len(product_ids)):
        try:
            product_id = int(product_ids[index])
        except (TypeError, ValueError):
            raise ValueError(
                f"Select a valid product in line {index + 1}."
            )

        product = db.session.get(Product, product_id)

        if not product or not product.is_active:
            raise ValueError(
                f"Product in line {index + 1} is unavailable."
            )

        quantity = parse_integer(
            quantities[index],
            f"Quantity in line {index + 1}",
        )

        plan = None
        plan_id = (plan_ids[index] or "").strip()

        if plan_id:
            try:
                plan_id = int(plan_id)
            except ValueError:
                raise ValueError("Invalid plan selection.")

            plan = db.session.get(Plan, plan_id)

            if (
                not plan
                or not plan.is_active
                or not plan.product.is_active
            ):
                raise ValueError(
                    f"Plan in line {index + 1} is unavailable."
                )

            if plan.product_id != product.id:
                raise ValueError(
                    "The selected plan does not belong to the selected product."
                )

        lines.append({
            "product": product,
            "plan": plan,
            "quantity": quantity,
        })

    # New templates default to active.
    # On edit, an unchecked checkbox means inactive.
    is_active = (
        request.form.get("is_active") == "1"
        if request.form.get("is_active") is not None
        else True
    )

    return {
        "name": name,
        "validity_days": validity_days,
        "notes": notes or None,
        "is_active": is_active,
        "lines": lines,
    }


def apply_template_data(template, values):
    template.name = values["name"]
    template.validity_days = values["validity_days"]
    template.notes = values["notes"]
    template.is_active = values["is_active"]

    template.lines.clear()

    for item in values["lines"]:
        template.lines.append(
            QuotationTemplateLine(
                product=item["product"],
                plan=item["plan"],
                quantity=item["quantity"],
            )
        )


# =========================================
# CREATE TEMPLATE
# =========================================

@quotations_bp.route(
    "/templates/new",
    methods=["GET", "POST"],
)
@admin_required
def create_template():
    products, plans = get_template_form_choices()

    if request.method == "POST":
        try:
            values = get_template_form_data()

            template = QuotationTemplate()

            apply_template_data(template, values)

            db.session.add(template)
            db.session.commit()

            flash(
                "Quotation template created successfully.",
                "success",
            )

            return redirect(
                url_for("quotations.list_templates")
            )

        except ValueError as error:
            db.session.rollback()
            flash(str(error), "danger")

        except IntegrityError:
            db.session.rollback()
            flash(
                "Could not create template. Please try again.",
                "danger",
            )

    return render_template(
        "quotations/template_form.html",
        template=None,
        products=products,
        plans=plans,
    )


# =========================================
# EDIT TEMPLATE
# =========================================

@quotations_bp.route(
    "/templates/<int:template_id>/edit",
    methods=["GET", "POST"],
)
@admin_required
def edit_template(template_id):
    template = get_template_or_404(template_id)

    products, plans = get_template_form_choices()

    if request.method == "POST":
        try:
            values = get_template_form_data()

            apply_template_data(template, values)

            db.session.commit()

            flash(
                "Quotation template updated successfully.",
                "success",
            )

            return redirect(
                url_for("quotations.list_templates")
            )

        except ValueError as error:
            db.session.rollback()
            flash(str(error), "danger")

        except IntegrityError:
            db.session.rollback()
            flash(
                "Could not update template. Please try again.",
                "danger",
            )

    return render_template(
        "quotations/template_form.html",
        template=template,
        products=products,
        plans=plans,
    )


# =========================================
# TOGGLE TEMPLATE STATUS
# =========================================

@quotations_bp.post(
    "/templates/<int:template_id>/toggle-status",
)
@admin_required
def toggle_template_status(template_id):
    template = get_template_or_404(template_id)

    template.is_active = not template.is_active

    db.session.commit()

    flash(
        (
            "Template activated successfully."
            if template.is_active
            else "Template deactivated successfully."
        ),
        "success",
    )

    return redirect(
        url_for("quotations.list_templates")
    )