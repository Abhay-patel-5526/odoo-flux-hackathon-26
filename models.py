from datetime import date, datetime
from decimal import Decimal

from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash

from extensions import db, login_manager


# Store money as Decimal/Numeric, never binary float, to avoid rounding errors.
MONEY = db.Numeric(12, 2)


class TimestampMixin:
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class User(UserMixin, TimestampMixin, db.Model):
    __tablename__ = "users"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False, default="customer", index=True)  # admin, staff, customer
    is_active = db.Column(db.Boolean, nullable=False, default=True)

    customer_profile = db.relationship("Customer", back_populates="user", uselist=False, cascade="all, delete-orphan")

    def set_password(self, password: str):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)

    def __repr__(self):
        return f"<User {self.email} ({self.role})>"


@login_manager.user_loader
def load_user(user_id):
    try:
        return db.session.get(User, int(user_id))
    except (TypeError, ValueError):
        return None


class Customer(TimestampMixin, db.Model):
    __tablename__ = "customers"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), unique=True)
    company_name = db.Column(db.String(180))
    phone = db.Column(db.String(40))
    billing_address = db.Column(db.Text)
    tax_identifier = db.Column(db.String(80))

    quotations = db.relationship("Quotation", back_populates="customer")
    user = db.relationship("User", back_populates="customer_profile")
    subscriptions = db.relationship("Subscription", back_populates="customer")
    invoices = db.relationship("Invoice", back_populates="customer")


class Product(TimestampMixin, db.Model):
    __tablename__ = "products"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(180), nullable=False, index=True)
    product_type = db.Column(db.String(40), nullable=False, default="service")
    sales_price = db.Column(MONEY, nullable=False, default=Decimal("0.00"))
    cost_price = db.Column(MONEY, nullable=False, default=Decimal("0.00"))
    notes = db.Column(db.Text)
    is_active = db.Column(db.Boolean, nullable=False, default=True, index=True)

    variants = db.relationship("ProductVariant", back_populates="product", cascade="all, delete-orphan")
    plans = db.relationship("Plan", back_populates="product")


class ProductVariant(TimestampMixin, db.Model):
    __tablename__ = "product_variants"
    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey("products.id", ondelete="CASCADE"), nullable=False, index=True)
    name = db.Column(db.String(120), nullable=False)
    additional_price = db.Column(MONEY, nullable=False, default=Decimal("0.00"))
    is_active = db.Column(db.Boolean, nullable=False, default=True)

    product = db.relationship("Product", back_populates="variants")


class TaxRule(TimestampMixin, db.Model):
    __tablename__ = "tax_rules"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    percentage = db.Column(db.Numeric(6, 3), nullable=False, default=Decimal("0.000"))
    is_active = db.Column(db.Boolean, nullable=False, default=True)


class Plan(TimestampMixin, db.Model):
    __tablename__ = "plans"
    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey("products.id", ondelete="RESTRICT"), nullable=False, index=True)
    name = db.Column(db.String(180), nullable=False)
    description = db.Column(db.Text)
    price = db.Column(MONEY, nullable=False)
    billing_interval = db.Column(db.String(20), nullable=False)  # daily, weekly, monthly, yearly
    minimum_quantity = db.Column(db.Integer, nullable=False, default=1)
    available_from = db.Column(db.Date)
    available_until = db.Column(db.Date)
    auto_close = db.Column(db.Boolean, nullable=False, default=False)
    allow_early_close = db.Column(db.Boolean, nullable=False, default=True)
    allow_pause = db.Column(db.Boolean, nullable=False, default=True)
    allow_renewal = db.Column(db.Boolean, nullable=False, default=True)
    is_active = db.Column(db.Boolean, nullable=False, default=True, index=True)

    product = db.relationship("Product", back_populates="plans")
    subscriptions = db.relationship("Subscription", back_populates="plan")


class QuotationTemplate(TimestampMixin, db.Model):
    __tablename__ = "quotation_templates"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(180), nullable=False)
    validity_days = db.Column(db.Integer, nullable=False, default=15)
    notes = db.Column(db.Text)
    is_active = db.Column(db.Boolean, nullable=False, default=True)

    quotations = db.relationship("Quotation", back_populates="template")
    lines = db.relationship("QuotationTemplateLine", back_populates="template", cascade="all, delete-orphan")


class QuotationTemplateLine(db.Model):
    __tablename__ = "quotation_template_lines"
    id = db.Column(db.Integer, primary_key=True)
    template_id = db.Column(db.Integer, db.ForeignKey("quotation_templates.id", ondelete="CASCADE"), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey("products.id", ondelete="RESTRICT"), nullable=False)
    plan_id = db.Column(db.Integer, db.ForeignKey("plans.id", ondelete="RESTRICT"))
    quantity = db.Column(db.Integer, nullable=False, default=1)

    template = db.relationship("QuotationTemplate", back_populates="lines")
    product = db.relationship("Product")
    plan = db.relationship("Plan")

class Quotation(TimestampMixin, db.Model):
    __tablename__ = "quotations"

    id = db.Column(db.Integer, primary_key=True)
    number = db.Column(db.String(40), unique=True, nullable=False, index=True)

    customer_id = db.Column(
        db.Integer,
        db.ForeignKey("customers.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    template_id = db.Column(
        db.Integer,
        db.ForeignKey("quotation_templates.id", ondelete="SET NULL"),
    )

    status = db.Column(
        db.String(20),
        nullable=False,
        default="draft",
        index=True,
    )  # draft, sent, accepted, rejected, expired, cancelled

    issue_date = db.Column(db.Date, nullable=False, default=date.today)
    valid_until = db.Column(db.Date, nullable=False)

    currency = db.Column(db.String(3), nullable=False, default="INR")

    subtotal = db.Column(MONEY, nullable=False, default=Decimal("0.00"))
    discount_amount = db.Column(MONEY, nullable=False, default=Decimal("0.00"))
    tax_amount = db.Column(MONEY, nullable=False, default=Decimal("0.00"))
    total = db.Column(MONEY, nullable=False, default=Decimal("0.00"))

    notes = db.Column(db.Text)

    customer = db.relationship("Customer", back_populates="quotations")
    template = db.relationship("QuotationTemplate", back_populates="quotations")

    lines = db.relationship(
        "QuotationLine",
        back_populates="quotation",
        cascade="all, delete-orphan",
    )


class QuotationLine(db.Model):
    __tablename__ = "quotation_lines"

    id = db.Column(db.Integer, primary_key=True)

    quotation_id = db.Column(
        db.Integer,
        db.ForeignKey("quotations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    product_id = db.Column(
        db.Integer,
        db.ForeignKey("products.id", ondelete="SET NULL"),
    )

    description = db.Column(db.String(255), nullable=False)
    quantity = db.Column(db.Integer, nullable=False, default=1)

    unit_price = db.Column(MONEY, nullable=False)

    tax_percentage = db.Column(
        db.Numeric(6, 3),
        nullable=False,
        default=Decimal("0.000"),
    )

    line_subtotal = db.Column(MONEY, nullable=False)
    line_tax = db.Column(MONEY, nullable=False, default=Decimal("0.00"))

    quotation = db.relationship("Quotation", back_populates="lines")
    product = db.relationship("Product")

class Subscription(TimestampMixin, db.Model):
    __tablename__ = "subscriptions"
    id = db.Column(db.Integer, primary_key=True)
    number = db.Column(db.String(40), unique=True, nullable=False, index=True)
    customer_id = db.Column(db.Integer, db.ForeignKey("customers.id", ondelete="RESTRICT"), nullable=False, index=True)
    plan_id = db.Column(db.Integer, db.ForeignKey("plans.id", ondelete="RESTRICT"), nullable=False, index=True)
    quotation_template_id = db.Column(db.Integer, db.ForeignKey("quotation_templates.id", ondelete="SET NULL"))
    status = db.Column(db.String(24), nullable=False, default="draft", index=True)
    start_date = db.Column(db.Date)
    expiry_date = db.Column(db.Date)
    next_billing_date = db.Column(db.Date, index=True)
    payment_terms_days = db.Column(db.Integer, nullable=False, default=0)
    currency = db.Column(db.String(3), nullable=False, default="INR")
    notes = db.Column(db.Text)
    closed_at = db.Column(db.DateTime)

    customer = db.relationship("Customer", back_populates="subscriptions")
    plan = db.relationship("Plan", back_populates="subscriptions")
    quotation_template = db.relationship("QuotationTemplate")
    lines = db.relationship("SubscriptionLine", back_populates="subscription", cascade="all, delete-orphan")
    invoices = db.relationship("Invoice", back_populates="subscription")
    billing_records = db.relationship("BillingRecord", back_populates="subscription", cascade="all, delete-orphan")


class SubscriptionLine(db.Model):
    __tablename__ = "subscription_lines"
    id = db.Column(db.Integer, primary_key=True)
    subscription_id = db.Column(db.Integer, db.ForeignKey("subscriptions.id", ondelete="CASCADE"), nullable=False, index=True)
    product_id = db.Column(db.Integer, db.ForeignKey("products.id", ondelete="RESTRICT"), nullable=False)
    variant_id = db.Column(db.Integer, db.ForeignKey("product_variants.id", ondelete="SET NULL"))
    description = db.Column(db.String(255))
    quantity = db.Column(db.Integer, nullable=False, default=1)
    unit_price = db.Column(MONEY, nullable=False)
    tax_rule_id = db.Column(db.Integer, db.ForeignKey("tax_rules.id", ondelete="SET NULL"))

    subscription = db.relationship("Subscription", back_populates="lines")
    product = db.relationship("Product")
    variant = db.relationship("ProductVariant")
    tax_rule = db.relationship("TaxRule")


class Discount(TimestampMixin, db.Model):
    __tablename__ = "discounts"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(160), nullable=False)
    discount_type = db.Column(db.String(20), nullable=False)  # fixed, percentage
    value = db.Column(MONEY, nullable=False)
    minimum_purchase = db.Column(MONEY, nullable=False, default=Decimal("0.00"))
    minimum_quantity = db.Column(db.Integer, nullable=False, default=1)
    starts_at = db.Column(db.Date)
    ends_at = db.Column(db.Date)
    usage_limit = db.Column(db.Integer)
    usage_count = db.Column(db.Integer, nullable=False, default=0)
    applies_to = db.Column(db.String(20), nullable=False, default="subscription")  # product, subscription
    product_id = db.Column(db.Integer, db.ForeignKey("products.id", ondelete="SET NULL"))
    is_active = db.Column(db.Boolean, nullable=False, default=True)

    product = db.relationship("Product")
    usages = db.relationship("DiscountUsage", back_populates="discount")


class Invoice(TimestampMixin, db.Model):
    __tablename__ = "invoices"
    id = db.Column(db.Integer, primary_key=True)
    number = db.Column(db.String(40), unique=True, nullable=False, index=True)
    customer_id = db.Column(db.Integer, db.ForeignKey("customers.id", ondelete="RESTRICT"), nullable=False, index=True)
    subscription_id = db.Column(db.Integer, db.ForeignKey("subscriptions.id", ondelete="RESTRICT"), index=True)
    discount_id = db.Column(db.Integer, db.ForeignKey("discounts.id", ondelete="SET NULL"))
    status = db.Column(db.String(20), nullable=False, default="draft", index=True)  # draft, confirmed, paid, cancelled
    issue_date = db.Column(db.Date, nullable=False, default=date.today)
    due_date = db.Column(db.Date, nullable=False, index=True)
    period_start = db.Column(db.Date)
    period_end = db.Column(db.Date)
    subtotal = db.Column(MONEY, nullable=False, default=Decimal("0.00"))
    discount_amount = db.Column(MONEY, nullable=False, default=Decimal("0.00"))
    tax_amount = db.Column(MONEY, nullable=False, default=Decimal("0.00"))
    total = db.Column(MONEY, nullable=False, default=Decimal("0.00"))
    paid_amount = db.Column(MONEY, nullable=False, default=Decimal("0.00"))
    notes = db.Column(db.Text)

    customer = db.relationship("Customer", back_populates="invoices")
    subscription = db.relationship("Subscription", back_populates="invoices")
    discount = db.relationship("Discount")
    lines = db.relationship("InvoiceLine", back_populates="invoice", cascade="all, delete-orphan")
    payments = db.relationship("Payment", back_populates="invoice", cascade="all, delete-orphan")
    billing_record = db.relationship("BillingRecord", back_populates="invoice", uselist=False)

    @property
    def outstanding_amount(self):
        return max(Decimal("0.00"), Decimal(self.total or 0) - Decimal(self.paid_amount or 0))

    @property
    def is_overdue(self):
        return self.status not in ("paid", "cancelled") and self.due_date < date.today() and self.outstanding_amount > 0


class InvoiceLine(db.Model):
    __tablename__ = "invoice_lines"
    id = db.Column(db.Integer, primary_key=True)
    invoice_id = db.Column(db.Integer, db.ForeignKey("invoices.id", ondelete="CASCADE"), nullable=False, index=True)
    product_id = db.Column(db.Integer, db.ForeignKey("products.id", ondelete="SET NULL"))
    description = db.Column(db.String(255), nullable=False)
    quantity = db.Column(db.Integer, nullable=False, default=1)
    unit_price = db.Column(MONEY, nullable=False)
    tax_percentage = db.Column(db.Numeric(6, 3), nullable=False, default=Decimal("0.000"))
    line_subtotal = db.Column(MONEY, nullable=False)
    line_tax = db.Column(MONEY, nullable=False, default=Decimal("0.00"))

    invoice = db.relationship("Invoice", back_populates="lines")
    product = db.relationship("Product")


class BillingRecord(db.Model):
    __tablename__ = "billing_records"
    id = db.Column(db.Integer, primary_key=True)
    subscription_id = db.Column(db.Integer, db.ForeignKey("subscriptions.id", ondelete="CASCADE"), nullable=False)
    invoice_id = db.Column(db.Integer, db.ForeignKey("invoices.id", ondelete="SET NULL"), unique=True)
    period_start = db.Column(db.Date, nullable=False)
    period_end = db.Column(db.Date, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    subscription = db.relationship("Subscription", back_populates="billing_records")
    invoice = db.relationship("Invoice", back_populates="billing_record")
    __table_args__ = (
        db.UniqueConstraint("subscription_id", "period_start", "period_end", name="uq_subscription_billing_period"),
    )


class DiscountUsage(db.Model):
    __tablename__ = "discount_usages"
    id = db.Column(db.Integer, primary_key=True)
    discount_id = db.Column(db.Integer, db.ForeignKey("discounts.id", ondelete="RESTRICT"), nullable=False, index=True)
    invoice_id = db.Column(db.Integer, db.ForeignKey("invoices.id", ondelete="CASCADE"), nullable=False, unique=True)
    used_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    discount = db.relationship("Discount", back_populates="usages")
    invoice = db.relationship("Invoice")


class Payment(TimestampMixin, db.Model):
    __tablename__ = "payments"
    id = db.Column(db.Integer, primary_key=True)
    reference = db.Column(db.String(50), unique=True, nullable=False, index=True)
    invoice_id = db.Column(db.Integer, db.ForeignKey("invoices.id", ondelete="RESTRICT"), nullable=False, index=True)
    method = db.Column(db.String(30), nullable=False)  # cash, bank_transfer, upi, card, other
    amount = db.Column(MONEY, nullable=False)
    payment_date = db.Column(db.Date, nullable=False, default=date.today)
    note = db.Column(db.Text)
    status = db.Column(db.String(20), nullable=False, default="completed")  # completed, voided

    invoice = db.relationship("Invoice", back_populates="payments")


class CompanySetting(TimestampMixin, db.Model):
    __tablename__ = "company_settings"
    id = db.Column(db.Integer, primary_key=True)
    company_name = db.Column(db.String(180), nullable=False, default="Brightloop Software")
    email = db.Column(db.String(255))
    phone = db.Column(db.String(40))
    address = db.Column(db.Text)
    currency = db.Column(db.String(3), nullable=False, default="INR")
