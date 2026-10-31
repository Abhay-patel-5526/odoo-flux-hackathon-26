
from decimal import Decimal, InvalidOperation

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

from extensions import db
from models import Product, ProductVariant
from permissions import admin_required, staff_or_admin_required


products_bp = Blueprint("products", __name__)


# -----------------------------------------
# Helpers
# -----------------------------------------

def parse_price(value, field_name):
    """Validate a price and return a Decimal."""
    try:
        price = Decimal(value)
    except (InvalidOperation, TypeError, ValueError):
        raise ValueError(f"Enter a valid {field_name}.")

    if not price.is_finite() or price < 0:
        raise ValueError(f"{field_name.title()} cannot be negative.")

    return price


def get_product_or_404(product_id):
    return db.get_or_404(Product, product_id)


# -----------------------------------------
# Product listing
# -----------------------------------------

@products_bp.get("/")
@login_required
@staff_or_admin_required
def list_products():

    search = request.args.get("search", "").strip()
    status = request.args.get("status", "active")

    query = Product.query

    if search:
        query = query.filter(Product.name.ilike(f"%{search}%"))

    if status == "active":
        query = query.filter_by(is_active=True)
    elif status == "archived":
        query = query.filter_by(is_active=False)

    products = query.order_by(Product.created_at.desc()).all()

    return render_template(
        "products/list.html",
        products=products,
        search=search,
        status=status,
    )


# -----------------------------------------
# Create product
# -----------------------------------------

@products_bp.route("/new", methods=["GET", "POST"])
@login_required
@admin_required
def create_product():

    if request.method == "POST":

        name = request.form.get("name", "").strip()
        product_type = request.form.get("product_type", "").strip()
        notes = request.form.get("notes", "").strip()

        if not name or not product_type:
            flash("Product name and type are required.", "danger")
            return render_template("products/form.html", product=None)

        try:
            sales_price = parse_price(
                request.form.get("sales_price", ""),
                "sales price",
            )

            cost_price = parse_price(
                request.form.get("cost_price", ""),
                "cost price",
            )

            product = Product(
                name=name,
                product_type=product_type,
                sales_price=sales_price,
                cost_price=cost_price,
                notes=notes or None,
                is_active=True,
            )

            db.session.add(product)
            db.session.flush()

            # Add new variants.
            variant_names = request.form.getlist("new_variant_name")
            variant_prices = request.form.getlist("new_variant_price")

            if len(variant_names) != len(variant_prices):
                raise ValueError("Invalid variant information.")

            for variant_name, variant_price in zip(
                variant_names, variant_prices
            ):
                variant_name = variant_name.strip()

                if not variant_name and not variant_price.strip():
                    continue

                if not variant_name:
                    raise ValueError("Every variant needs a name.")

                additional_price = parse_price(
                    variant_price,
                    "variant additional price",
                )

                db.session.add(
                    ProductVariant(
                        product_id=product.id,
                        name=variant_name,
                        additional_price=additional_price,
                        is_active=True,
                    )
                )

            db.session.commit()

            flash("Product created successfully!", "success")
            return redirect(
                url_for("products.product_detail", product_id=product.id)
            )

        except ValueError as error:
            db.session.rollback()
            flash(str(error), "danger")

        except Exception:
            db.session.rollback()
            flash("Something went wrong while creating the product.", "danger")

    return render_template("products/form.html", product=None)


# -----------------------------------------
# Product details
# -----------------------------------------

@products_bp.get("/<int:product_id>")
@login_required
@staff_or_admin_required
def product_detail(product_id):

    product = get_product_or_404(product_id)

    return render_template(
        "products/detail.html",
        product=product,
    )


# -----------------------------------------
# Edit product and variants
# -----------------------------------------

@products_bp.route("/<int:product_id>/edit", methods=["GET", "POST"])
@login_required
@admin_required
def edit_product(product_id):

    product = get_product_or_404(product_id)

    if request.method == "POST":

        name = request.form.get("name", "").strip()
        product_type = request.form.get("product_type", "").strip()
        notes = request.form.get("notes", "").strip()

        if not name or not product_type:
            flash("Product name and type are required.", "danger")
            return render_template(
                "products/form.html",
                product=product,
            )

        try:
            product.sales_price = parse_price(
                request.form.get("sales_price", ""),
                "sales price",
            )

            product.cost_price = parse_price(
                request.form.get("cost_price", ""),
                "cost price",
            )

            product.name = name
            product.product_type = product_type
            product.notes = notes or None

            # Update existing variants.
            for variant in product.variants:

                variant_name = request.form.get(
                    f"variant_{variant.id}_name", ""
                ).strip()

                variant_price = request.form.get(
                    f"variant_{variant.id}_price", ""
                )

                variant.name = variant_name
                variant.additional_price = parse_price(
                    variant_price,
                    "variant additional price",
                )

                variant.is_active = (
                    request.form.get(f"variant_{variant.id}_active") == "on"
                )

            # Add new variants.
            variant_names = request.form.getlist("new_variant_name")
            variant_prices = request.form.getlist("new_variant_price")

            if len(variant_names) != len(variant_prices):
                raise ValueError("Invalid variant information.")

            for variant_name, variant_price in zip(
                variant_names, variant_prices
            ):
                variant_name = variant_name.strip()

                if not variant_name and not variant_price.strip():
                    continue

                if not variant_name:
                    raise ValueError("Every variant needs a name.")

                additional_price = parse_price(
                    variant_price,
                    "variant additional price",
                )

                db.session.add(
                    ProductVariant(
                        product_id=product.id,
                        name=variant_name,
                        additional_price=additional_price,
                        is_active=True,
                    )
                )

            db.session.commit()

            flash("Product updated successfully!", "success")
            return redirect(
                url_for("products.product_detail", product_id=product.id)
            )

        except ValueError as error:
            db.session.rollback()
            flash(str(error), "danger")

            product = get_product_or_404(product_id)

        except Exception:
            db.session.rollback()
            flash("Something went wrong while updating the product.", "danger")
            product = get_product_or_404(product_id)

    return render_template(
        "products/form.html",
        product=product,
    )


# -----------------------------------------
# Archive product
# -----------------------------------------

@products_bp.post("/<int:product_id>/archive")
@login_required
@admin_required
def archive_product(product_id):

    product = get_product_or_404(product_id)

    if product.plans:
        flash(
            "This product has associated plans. Archive it only after "
            "reviewing those plans.",
            "warning",
        )
        return redirect(
            url_for("products.product_detail", product_id=product.id)
        )

    product.is_active = False
    db.session.commit()

    flash("Product archived successfully.", "success")

    return redirect(url_for("products.list_products"))


# -----------------------------------------
# Restore product
# -----------------------------------------

@products_bp.post("/<int:product_id>/restore")
@login_required
@admin_required
def restore_product(product_id):

    product = get_product_or_404(product_id)

    product.is_active = True
    db.session.commit()

    flash("Product restored successfully.", "success")

    return redirect(
        url_for("products.product_detail", product_id=product.id)
    )
