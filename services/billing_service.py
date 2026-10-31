from calendar import monthrange
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from uuid import uuid4

from sqlalchemy import select

from extensions import db
from models import (
    BillingRecord,
    Discount,
    DiscountUsage,
    Invoice,
    InvoiceLine,
    Subscription,
)


CENT = Decimal("0.01")
ZERO = Decimal("0.00")


def money(value):
    """Convert a value to a two-decimal Decimal."""
    return Decimal(str(value or 0)).quantize(
        CENT,
        rounding=ROUND_HALF_UP,
    )


def add_months(source_date, months):
    """Add months while keeping the day valid for the target month."""
    month_index = source_date.month - 1 + months
    year = source_date.year + month_index // 12
    month = month_index % 12 + 1

    day = min(source_date.day, monthrange(year, month)[1])

    return date(year, month, day)


def next_billing_period(start_date, interval):
    """
    Return the inclusive end date of a billing period.

    Examples:
    monthly:  1 Jan - 31 Jan
    yearly:   1 Jan - 31 Dec
    weekly:   1 Jan - 7 Jan
    daily:    1 Jan - 1 Jan
    """
    interval = (interval or "").lower()

    if interval == "daily":
        next_date = start_date + timedelta(days=1)

    elif interval == "weekly":
        next_date = start_date + timedelta(weeks=1)

    elif interval == "monthly":
        next_date = add_months(start_date, 1)

    elif interval == "yearly":
        next_date = add_months(start_date, 12)

    else:
        raise ValueError(f"Unsupported billing interval: {interval}")

    return next_date - timedelta(days=1)


def generate_invoice_number():
    """Generate a unique invoice number."""
    return f"INV-{date.today():%Y%m%d}-{uuid4().hex[:6].upper()}"


def find_eligible_discount(subscription, subtotal, total_quantity, today):
    """
    Find the first active discount eligible for this subscription.

    Subscription discounts apply to the whole subscription.
    Product discounts apply to matching subscription lines.
    """
    discounts = (
        Discount.query
        .filter_by(is_active=True)
        .order_by(Discount.id.asc())
        .all()
    )

    for discount in discounts:
        if discount.starts_at and discount.starts_at > today:
            continue

        if discount.ends_at and discount.ends_at < today:
            continue

        if discount.usage_limit is not None:
            if discount.usage_count >= discount.usage_limit:
                continue

        if subtotal < money(discount.minimum_purchase):
            continue

        if total_quantity < (discount.minimum_quantity or 1):
            continue

        if discount.applies_to == "subscription":
            return discount

        if discount.applies_to == "product":
            if discount.product_id and any(
                line.product_id == discount.product_id
                for line in subscription.lines
            ):
                return discount

    return None


def calculate_discount(discount, subtotal):
    """Calculate a fixed or percentage discount."""
    if not discount:
        return ZERO

    value = money(discount.value)

    if discount.discount_type == "percentage":
        amount = subtotal * value / Decimal("100")

    elif discount.discount_type == "fixed":
        amount = value

    else:
        return ZERO

    return min(money(amount), subtotal)


def build_invoice_lines(subscription, invoice, discount_amount):
    """
    Copy subscription lines into invoice lines.

    Discount is allocated proportionally across eligible lines.
    Tax is calculated on the discounted taxable amount.
    """
    source_lines = subscription.lines

    if not source_lines:
        raise ValueError(
            f"Subscription {subscription.number} has no invoiceable lines."
        )

    raw_lines = []
    subtotal = ZERO
    total_quantity = 0

    for source in source_lines:
        quantity = int(source.quantity or 0)

        if quantity <= 0:
            raise ValueError(
                f"Subscription {subscription.number} has an invalid quantity."
            )

        unit_price = money(source.unit_price)
        line_subtotal = money(unit_price * quantity)

        tax_percentage = ZERO
        if source.tax_rule and source.tax_rule.is_active:
            tax_percentage = Decimal(
                str(source.tax_rule.percentage or 0)
            )

        raw_lines.append({
            "source": source,
            "quantity": quantity,
            "unit_price": unit_price,
            "line_subtotal": line_subtotal,
            "tax_percentage": tax_percentage,
        })

        subtotal += line_subtotal
        total_quantity += quantity

    subtotal = money(subtotal)

    if subtotal <= ZERO:
        raise ValueError(
            f"Subscription {subscription.number} has no billable amount."
        )

    discount_amount = min(money(discount_amount), subtotal)

    total_tax = ZERO
    allocated_discount = ZERO

    for index, item in enumerate(raw_lines):
        line_subtotal = item["line_subtotal"]

        if index == len(raw_lines) - 1:
            line_discount = discount_amount - allocated_discount
        elif subtotal > ZERO:
            line_discount = money(
                discount_amount * line_subtotal / subtotal
            )
            allocated_discount += line_discount
        else:
            line_discount = ZERO

        taxable_amount = max(
            ZERO,
            line_subtotal - line_discount,
        )

        line_tax = money(
            taxable_amount * item["tax_percentage"] / Decimal("100")
        )

        total_tax += line_tax

        invoice.lines.append(
            InvoiceLine(
                product_id=item["source"].product_id,
                description=(
                    item["source"].description
                    or item["source"].product.name
                ),
                quantity=item["quantity"],
                unit_price=item["unit_price"],
                tax_percentage=item["tax_percentage"],
                line_subtotal=line_subtotal,
                line_tax=line_tax,
            )
        )

    invoice.subtotal = subtotal
    invoice.discount_amount = discount_amount
    invoice.tax_amount = money(total_tax)
    invoice.total = money(
        subtotal - discount_amount + invoice.tax_amount
    )


def subscription_period_already_billed(subscription_id, period_start, period_end):
    """Check whether this exact subscription period has been billed."""
    return db.session.execute(
        select(BillingRecord.id).where(
            BillingRecord.subscription_id == subscription_id,
            BillingRecord.period_start == period_start,
            BillingRecord.period_end == period_end,
        )
    ).first() is not None


def create_subscription_invoice(subscription, today=None):
    """
    Generate one invoice for a subscription's current billing period.

    This function does not commit. The caller controls the transaction.
    """
    today = today or date.today()

    if subscription.status != "active":
        raise ValueError("Only active subscriptions can be billed.")

    if not subscription.plan or not subscription.plan.is_active:
        raise ValueError("The subscription plan is inactive or unavailable.")

    period_start = subscription.next_billing_date

    if not period_start:
        raise ValueError("Subscription has no next billing date.")

    if period_start > today:
        raise ValueError("Subscription is not due for billing yet.")

    if subscription.start_date and period_start < subscription.start_date:
        raise ValueError("Billing date is earlier than the subscription start date.")

    if subscription.expiry_date and period_start > subscription.expiry_date:
        raise ValueError("Subscription has already expired.")

    period_end = next_billing_period(
        period_start,
        subscription.plan.billing_interval,
    )

    if subscription.expiry_date:
        period_end = min(period_end, subscription.expiry_date)

    if subscription_period_already_billed(
        subscription.id,
        period_start,
        period_end,
    ):
        raise ValueError("This subscription period has already been billed.")

    if not subscription.lines:
        raise ValueError("Subscription has no billable lines.")

    subtotal = money(
        sum(
            (
                money(line.unit_price) * int(line.quantity or 0)
                for line in subscription.lines
            ),
            ZERO,
        )
    )

    total_quantity = sum(
        int(line.quantity or 0)
        for line in subscription.lines
    )

    discount = find_eligible_discount(
        subscription,
        subtotal,
        total_quantity,
        today,
    )

    discount_amount = calculate_discount(discount, subtotal)

    due_date = today + timedelta(
        days=max(0, subscription.payment_terms_days or 0)
    )

    invoice = Invoice(
        number=generate_invoice_number(),
        customer_id=subscription.customer_id,
        subscription_id=subscription.id,
        discount_id=discount.id if discount else None,
        status="confirmed",
        issue_date=today,
        due_date=due_date,
        period_start=period_start,
        period_end=period_end,
        paid_amount=ZERO,
        notes=(
            f"Recurring invoice for subscription {subscription.number}. "
            f"Billing period: {period_start:%d %b %Y} to {period_end:%d %b %Y}."
        ),
    )

    build_invoice_lines(
        subscription,
        invoice,
        discount_amount,
    )

    db.session.add(invoice)
    db.session.flush()

    record = BillingRecord(
        subscription_id=subscription.id,
        invoice_id=invoice.id,
        period_start=period_start,
        period_end=period_end,
    )

    db.session.add(record)

    if discount:
        discount.usage_count += 1

        db.session.add(
            DiscountUsage(
                discount_id=discount.id,
                invoice_id=invoice.id,
            )
        )

    # Move the next billing date forward.
    subscription.next_billing_date = period_end + timedelta(days=1)

    # Close subscriptions that have reached their expiry date.
    if (
        subscription.expiry_date
        and subscription.next_billing_date > subscription.expiry_date
        and subscription.plan.auto_close
    ):
        subscription.status = "closed"

    return invoice


def generate_due_invoices(today=None):
    """
    Generate invoices for all active subscriptions due on or before today.

    A single transaction is used for the batch. If an unexpected database
    error occurs, the batch is rolled back rather than partially committed.
    """
    today = today or date.today()

    due_subscriptions = (
        Subscription.query
        .filter(
            Subscription.status == "active",
            Subscription.next_billing_date.isnot(None),
            Subscription.next_billing_date <= today,
        )
        .order_by(Subscription.next_billing_date.asc())
        .all()
    )

    generated = []
    skipped = []

    try:
        for subscription in due_subscriptions:
            try:
                invoice = create_subscription_invoice(
                    subscription,
                    today=today,
                )

                generated.append({
                    "subscription": subscription.number,
                    "invoice": invoice.number,
                    "invoice_id": invoice.id,
                })

            except ValueError as exc:
                skipped.append({
                    "subscription": subscription.number,
                    "reason": str(exc),
                })

        db.session.commit()

    except Exception:
        db.session.rollback()
        raise

    return {
        "generated": generated,
        "skipped": skipped,
        "generated_count": len(generated),
        "skipped_count": len(skipped),
    }