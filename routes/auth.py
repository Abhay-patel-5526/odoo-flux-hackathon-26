
import re
from urllib.parse import urlsplit

from email_validator import EmailNotValidError, validate_email
from flask import (
    Blueprint, current_app, flash, redirect,
    render_template, request, url_for
)
from flask_login import current_user, login_user, logout_user
from itsdangerous import (
    BadSignature, SignatureExpired, URLSafeTimedSerializer
)
from sqlalchemy.exc import IntegrityError

from extensions import db
from models import Customer, User


auth_bp = Blueprint("auth", __name__)

RESET_TOKEN_SALT = "brightloop-password-reset-v1"
RESET_TOKEN_MAX_AGE = 1800


def role_home(user):
    # if user.role in ("admin", "staff"):
    #     if "dashboard.index" in current_app.view_functions:
    #         return url_for("dashboard.index")

    # if user.role == "customer":
    #     if "portal.index" in current_app.view_functions:
    #         return url_for("portal.index")

    # return url_for("index")
    return url_for("dashboard.index")

def valid_password(password):
    return (
        len(password) > 8
        and bool(re.search(r"[A-Z]", password))
        and bool(re.search(r"[a-z]", password))
        and bool(re.search(r"[^A-Za-z0-9]", password))
    )


def reset_serializer():
    return URLSafeTimedSerializer(current_app.config["SECRET_KEY"])


def generate_reset_token(user):
    return reset_serializer().dumps(
        {"user_id": user.id},
        salt=RESET_TOKEN_SALT
    )


def verify_reset_token(token):
    try:
        data = reset_serializer().loads(
            token,
            salt=RESET_TOKEN_SALT,
            max_age=RESET_TOKEN_MAX_AGE
        )
        return db.session.get(User, int(data["user_id"]))
    except (
        BadSignature, SignatureExpired,
        KeyError, TypeError, ValueError
    ):
        return None


def safe_redirect(target):
    if not target:
        return False

    parsed = urlsplit(target)

    return (
        not parsed.scheme
        and not parsed.netloc
        and target.startswith("/")
        and not target.startswith("//")
    )


@auth_bp.route("/register", methods=["GET", "POST"])
def register():

    if current_user.is_authenticated:
        return redirect(role_home(current_user))

    if request.method == "POST":

        name = request.form.get("name", "").strip()
        email_input = request.form.get("email", "").strip()
        password = request.form.get("password", "")
        confirm_password = request.form.get(
            "confirm_password", ""
        )
        company_name = request.form.get(
            "company_name", ""
        ).strip()

        if not name or len(name) > 120:
            flash("Enter a valid name.", "danger")
            return render_template("auth/register.html")

        try:
            email = validate_email(
                email_input,
                check_deliverability=False
            ).normalized.lower()
        except EmailNotValidError:
            flash("Enter a valid email address.", "danger")
            return render_template("auth/register.html")

        if User.query.filter_by(email=email).first():
            flash("Email already registered.", "warning")
            return render_template("auth/register.html")

        if not valid_password(password):
            flash(
                "Password must be longer than 8 characters "
                "and include uppercase, lowercase and special characters.",
                "danger"
            )
            return render_template("auth/register.html")

        if password != confirm_password:
            flash("Passwords do not match.", "danger")
            return render_template("auth/register.html")

        user = User(
            name=name,
            email=email,
            role="customer",
            is_active=True
        )

        user.set_password(password)

        user.customer_profile = Customer(
            company_name=company_name or None
        )

        try:
            db.session.add(user)
            db.session.commit()

        except IntegrityError:
            db.session.rollback()
            flash("This email is already registered.", "warning")
            return render_template("auth/register.html")

        login_user(user)

        flash("Account created successfully!", "success")

        return redirect(role_home(user))

    return render_template("auth/register.html")


@auth_bp.route("/login", methods=["GET", "POST"])
def login():

    if current_user.is_authenticated:
        return redirect(role_home(current_user))

    if request.method == "POST":

        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        remember = request.form.get("remember") == "on"

        user = User.query.filter_by(email=email).first()

        if (
            not user
            or not user.check_password(password)
            or not user.is_active
        ):
            flash("Invalid email or password.", "danger")
            return render_template("auth/login.html")

        login_user(user, remember=remember)

        flash(f"Welcome back, {user.name}!", "success")

        next_url = request.args.get("next")

        if safe_redirect(next_url):
            return redirect(next_url)

        return redirect(role_home(user))

    return render_template("auth/login.html")


@auth_bp.get("/logout")
def logout():

    if current_user.is_authenticated:
        logout_user()
        flash("Logged out successfully.", "success")

    return redirect(url_for("auth.login"))


@auth_bp.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():

    if request.method == "POST":

        email = request.form.get("email", "").strip().lower()

        user = User.query.filter_by(
            email=email,
            is_active=True
        ).first()

        if user:
            token = generate_reset_token(user)

            reset_url = url_for(
                "auth.reset_password",
                token=token,
                _external=True
            )

            current_app.logger.info(
                "Password reset link for %s: %s",
                user.email,
                reset_url
            )

        flash(
            "If an active account exists, reset instructions "
            "have been generated.",
            "info"
        )

        if current_app.debug and user:
            flash(
                "Development only: check your Flask terminal "
                "for the reset link.",
                "warning"
            )

        return redirect(url_for("auth.login"))

    return render_template("auth/forgot_password.html")


@auth_bp.route(
    "/reset-password/<token>",
    methods=["GET", "POST"]
)
def reset_password(token):

    user = verify_reset_token(token)

    if not user or not user.is_active:
        flash(
            "Invalid or expired password reset link.",
            "danger"
        )
        return redirect(url_for("auth.forgot_password"))

    if request.method == "POST":

        password = request.form.get("password", "")
        confirm_password = request.form.get(
            "confirm_password", ""
        )

        if not valid_password(password):
            flash("Password does not meet requirements.", "danger")

        elif password != confirm_password:
            flash("Passwords do not match.", "danger")

        else:
            user.set_password(password)
            db.session.commit()

            flash(
                "Password reset successfully. Please log in.",
                "success"
            )

            return redirect(url_for("auth.login"))

    return render_template(
        "auth/reset_password.html"
    )
