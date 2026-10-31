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
from sqlalchemy.exc import IntegrityError

from extensions import db
from models import Customer, User
from permissions import admin_required, staff_or_admin_required


customers_bp = Blueprint("customers", __name__)


def get_customer_or_404(customer_id):
    return db.get_or_404(Customer, customer_id)


def validate_password(password):
    if len(password) < 8:
        raise ValueError("Password must contain at least 8 characters.")

    if not any(char.isupper() for char in password):
        raise ValueError("Password must contain an uppercase letter.")

    if not any(char.islower() for char in password):
        raise ValueError("Password must contain a lowercase letter.")

    if not any(not char.isalnum() for char in password):
        raise ValueError("Password must contain a special character.")


# --------------------------------------------------
# CUSTOMER LIST
# --------------------------------------------------

@customers_bp.get("/")
@staff_or_admin_required
def list_customers():

    search = request.args.get("q", "").strip()
    status = request.args.get("status", "active")

    query = Customer.query.join(User).filter(User.role == "customer")

    if status == "active":
        query = query.filter(User.is_active.is_(True))

    elif status == "inactive":
        query = query.filter(User.is_active.is_(False))

    if search:
        query = query.filter(
            or_(
                User.name.ilike(f"%{search}%"),
                User.email.ilike(f"%{search}%"),
                Customer.company_name.ilike(f"%{search}%"),
            )
        )

    customers = query.order_by(Customer.created_at.desc()).all()

    return render_template(
        "customers/list.html",
        customers=customers,
        search=search,
        status=status,
    )


# --------------------------------------------------
# CREATE CUSTOMER
# --------------------------------------------------

@customers_bp.route("/new", methods=["GET", "POST"])
@admin_required
def create_customer():

    if request.method == "POST":

        try:
            name = request.form.get("name", "").strip()
            email = request.form.get("email", "").strip().lower()
            password = request.form.get("password", "")

            company_name = request.form.get("company_name", "").strip()
            phone = request.form.get("phone", "").strip()
            tax_identifier = request.form.get("tax_identifier", "").strip()
            billing_address = request.form.get("billing_address", "").strip()

            if not name:
                raise ValueError("Customer name is required.")

            if not email or "@" not in email:
                raise ValueError("Enter a valid email address.")

            if User.query.filter_by(email=email).first():
                raise ValueError("An account with this email already exists.")

            validate_password(password)

            user = User(
                name=name,
                email=email,
                role="customer",
                is_active=True,
            )
            user.set_password(password)

            customer = Customer(
                user=user,
                company_name=company_name or None,
                phone=phone or None,
                tax_identifier=tax_identifier or None,
                billing_address=billing_address or None,
            )

            db.session.add(user)
            db.session.add(customer)
            db.session.commit()

            flash("Customer created successfully.", "success")

            return redirect(
                url_for("customers.customer_detail", customer_id=customer.id)
            )

        except ValueError as error:
            db.session.rollback()
            flash(str(error), "danger")

        except IntegrityError:
            db.session.rollback()
            flash("This email address is already registered.", "danger")

    return render_template(
        "customers/form.html",
        customer=None,
    )


# --------------------------------------------------
# CUSTOMER DETAILS
# --------------------------------------------------

@customers_bp.get("/<int:customer_id>")
@staff_or_admin_required
def customer_detail(customer_id):

    customer = get_customer_or_404(customer_id)

    return render_template(
        "customers/detail.html",
        customer=customer,
    )


# --------------------------------------------------
# EDIT CUSTOMER
# --------------------------------------------------

@customers_bp.route("/<int:customer_id>/edit", methods=["GET", "POST"])
@admin_required
def edit_customer(customer_id):

    customer = get_customer_or_404(customer_id)

    if request.method == "POST":

        try:
            name = request.form.get("name", "").strip()
            email = request.form.get("email", "").strip().lower()

            if not name:
                raise ValueError("Customer name is required.")

            if not email or "@" not in email:
                raise ValueError("Enter a valid email address.")

            existing_user = User.query.filter(
                User.email == email,
                User.id != customer.user_id,
            ).first()

            if existing_user:
                raise ValueError("This email address is already registered.")

            customer.user.name = name
            customer.user.email = email

            customer.company_name = (
                request.form.get("company_name", "").strip() or None
            )
            customer.phone = (
                request.form.get("phone", "").strip() or None
            )
            customer.tax_identifier = (
                request.form.get("tax_identifier", "").strip() or None
            )
            customer.billing_address = (
                request.form.get("billing_address", "").strip() or None
            )

            customer.user.is_active = "is_active" in request.form

            db.session.commit()

            flash("Customer updated successfully.", "success")

            return redirect(
                url_for("customers.customer_detail", customer_id=customer.id)
            )

        except ValueError as error:
            db.session.rollback()
            flash(str(error), "danger")

        except IntegrityError:
            db.session.rollback()
            flash("This email address is already registered.", "danger")

    return render_template(
        "customers/form.html",
        customer=customer,
    )


# --------------------------------------------------
# ACTIVATE / DEACTIVATE CUSTOMER
# --------------------------------------------------

@customers_bp.post("/<int:customer_id>/toggle-status")
@admin_required
def toggle_customer_status(customer_id):

    customer = get_customer_or_404(customer_id)

    customer.user.is_active = not customer.user.is_active

    db.session.commit()

    if customer.user.is_active:
        flash("Customer account reactivated successfully.", "success")
    else:
        flash("Customer account deactivated successfully.", "success")

    return redirect(
        url_for("customers.customer_detail", customer_id=customer.id)
    )