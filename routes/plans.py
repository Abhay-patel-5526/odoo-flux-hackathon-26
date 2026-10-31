from datetime import date
from decimal import Decimal, InvalidOperation

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import login_required
from sqlalchemy import or_

from extensions import db
from models import Plan, Product
from permissions import admin_required, staff_or_admin_required

plans_bp = Blueprint("plans", __name__)


def get_plan_or_404(plan_id):
    return db.get_or_404(Plan, plan_id)


def parse_price(value):
    try:
        price = Decimal(value)
    except (InvalidOperation, TypeError, ValueError):
        raise ValueError("Enter a valid price.")

    if not price.is_finite() or price < 0:
        raise ValueError("Price must be a non-negative number.")

    return price


def parse_optional_date(value):
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise ValueError("Enter a valid date.")


@plans_bp.get("/")
@staff_or_admin_required
def list_plans():
    search = request.args.get("q", "").strip()
    status = request.args.get("status", "active")

    query = Plan.query.join(Product)

    if status == "active":
        query = query.filter(Plan.is_active.is_(True))
    elif status == "archived":
        query = query.filter(Plan.is_active.is_(False))

    if search:
        query = query.filter(
            or_(
                Plan.name.ilike(f"%{search}%"),
                Product.name.ilike(f"%{search}%")
            )
        )

    plans = query.order_by(Plan.created_at.desc()).all()

    return render_template(
        "plans/list.html",
        plans=plans,
        search=search,
        status=status
    )


@plans_bp.route("/new", methods=["GET", "POST"])
@admin_required
def create_plan():
    products = Product.query.filter_by(is_active=True).order_by(Product.name).all()

    if request.method == "POST":
        try:
            name = request.form.get("name", "").strip()
            product_id = request.form.get("product_id", type=int)
            product = db.session.get(Product, product_id) if product_id else None

            if not name:
                raise ValueError("Plan name is required.")

            if not product or not product.is_active:
                raise ValueError("Select an active product.")

            interval = request.form.get("billing_interval")
            if interval not in ("daily", "weekly", "monthly", "yearly"):
                raise ValueError("Select a valid billing interval.")

            price = parse_price(request.form.get("price", ""))

            minimum_quantity = request.form.get("minimum_quantity", type=int)
            if minimum_quantity is None or minimum_quantity < 1:
                raise ValueError("Minimum quantity must be at least 1.")

            available_from = parse_optional_date(request.form.get("available_from"))
            available_until = parse_optional_date(request.form.get("available_until"))

            if available_from and available_until and available_until < available_from:
                raise ValueError("Availability end date cannot be before start date.")

            plan = Plan(
                name=name,
                product=product,
                description=request.form.get("description", "").strip() or None,
                price=price,
                billing_interval=interval,
                minimum_quantity=minimum_quantity,
                available_from=available_from,
                available_until=available_until,
                auto_close="auto_close" in request.form,
                allow_early_close="allow_early_close" in request.form,
                allow_pause="allow_pause" in request.form,
                allow_renewal="allow_renewal" in request.form,
            )

            db.session.add(plan)
            db.session.commit()

            flash("Plan created successfully.", "success")
            return redirect(url_for("plans.plan_detail", plan_id=plan.id))

        except ValueError as error:
            db.session.rollback()
            flash(str(error), "danger")

    return render_template("plans/form.html", plan=None, products=products)


@plans_bp.get("/<int:plan_id>")
@staff_or_admin_required
def plan_detail(plan_id):
    plan = get_plan_or_404(plan_id)
    return render_template("plans/detail.html", plan=plan)


@plans_bp.route("/<int:plan_id>/edit", methods=["GET", "POST"])
@admin_required
def edit_plan(plan_id):
    plan = get_plan_or_404(plan_id)
    products = Product.query.filter_by(is_active=True).order_by(Product.name).all()

    if request.method == "POST":
        try:
            name = request.form.get("name", "").strip()
            product_id = request.form.get("product_id", type=int)
            product = db.session.get(Product, product_id) if product_id else None

            if not name:
                raise ValueError("Plan name is required.")

            if not product or not product.is_active:
                raise ValueError("Select an active product.")

            interval = request.form.get("billing_interval")
            if interval not in ("daily", "weekly", "monthly", "yearly"):
                raise ValueError("Select a valid billing interval.")

            price = parse_price(request.form.get("price", ""))

            minimum_quantity = request.form.get("minimum_quantity", type=int)
            if minimum_quantity is None or minimum_quantity < 1:
                raise ValueError("Minimum quantity must be at least 1.")

            available_from = parse_optional_date(request.form.get("available_from"))
            available_until = parse_optional_date(request.form.get("available_until"))

            if available_from and available_until and available_until < available_from:
                raise ValueError("Availability end date cannot be before start date.")

            plan.name = name
            plan.product = product
            plan.description = request.form.get("description", "").strip() or None
            plan.price = price
            plan.billing_interval = interval
            plan.minimum_quantity = minimum_quantity
            plan.available_from = available_from
            plan.available_until = available_until
            plan.auto_close = "auto_close" in request.form
            plan.allow_early_close = "allow_early_close" in request.form
            plan.allow_pause = "allow_pause" in request.form
            plan.allow_renewal = "allow_renewal" in request.form
            plan.is_active = "is_active" in request.form

            db.session.commit()

            flash("Plan updated successfully.", "success")
            return redirect(url_for("plans.plan_detail", plan_id=plan.id))

        except ValueError as error:
            db.session.rollback()
            flash(str(error), "danger")

    return render_template("plans/form.html", plan=plan, products=products)


@plans_bp.post("/<int:plan_id>/archive")
@admin_required
def archive_plan(plan_id):
    plan = get_plan_or_404(plan_id)

    if plan.subscriptions:
        flash("This plan has subscriptions and cannot be archived.", "warning")
        return redirect(url_for("plans.plan_detail", plan_id=plan.id))

    plan.is_active = False
    db.session.commit()

    flash("Plan archived successfully.", "success")
    return redirect(url_for("plans.list_plans", status="archived"))


@plans_bp.post("/<int:plan_id>/restore")
@admin_required
def restore_plan(plan_id):
    plan = get_plan_or_404(plan_id)

    if not plan.product.is_active:
        flash("Restore the linked product before restoring this plan.", "warning")
        return redirect(url_for("plans.plan_detail", plan_id=plan.id))

    plan.is_active = True
    db.session.commit()

    flash("Plan restored successfully.", "success")
    return redirect(url_for("plans.plan_detail", plan_id=plan.id))