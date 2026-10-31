
from decimal import Decimal, ROUND_HALF_UP

from extensions import db
from models import Invoice, InvoiceLine, Payment


MONEY_ZERO = Decimal("0.00")
MONEY_CENT = Decimal("0.01")


def money(value):
    return Decimal(str(value)).quantize(
        MONEY_CENT,
        rounding=ROUND_HALF_UP,
    )


def calculate_invoice_totals(lines, discount_amount):
    """
    Calculate invoice subtotal, discount, tax and total.
    """

    subtotal = money(sum(
        (line["line_subtotal"] for line in lines),
        MONEY_ZERO,
    ))

    original_tax = money(sum(
        (line["line_tax"] for line in lines),
        MONEY_ZERO,
    ))

    discount_amount = money(discount_amount)

    if discount_amount < MONEY_ZERO:
        raise ValueError("Discount cannot be negative.")

    if discount_amount > subtotal:
        raise ValueError("Discount cannot exceed subtotal.")

    taxable_ratio = (
        (subtotal - discount_amount) / subtotal
        if subtotal > MONEY_ZERO
        else Decimal("0")
    )

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


def apply_invoice_lines(invoice, lines):
    """
    Replace invoice lines with validated line data.
    """

    invoice.lines.clear()

    for item in lines:
        invoice.lines.append(
            InvoiceLine(
                product=item["product"],
                description=item["description"],
                quantity=item["quantity"],
                unit_price=item["unit_price"],
                tax_percentage=item["tax_percentage"],
                line_subtotal=item["line_subtotal"],
                line_tax=item["line_tax"],
            )
        )


def refresh_invoice_payment_status(invoice):
    """
    Recalculate paid amount and invoice status
    using completed payments.
    """

    completed_payments = [
        payment
        for payment in invoice.payments
        if payment.status == "completed"
    ]

    invoice.paid_amount = money(sum(
        (Decimal(str(payment.amount)) for payment in completed_payments),
        MONEY_ZERO,
    ))

    if invoice.status == "cancelled":
        return

    if invoice.paid_amount >= money(invoice.total):
        invoice.status = "paid"
    elif invoice.paid_amount > MONEY_ZERO:
        invoice.status = "confirmed"
    elif invoice.status == "paid":
        invoice.status = "confirmed"


def record_invoice_payment(
    invoice,
    reference,
    amount,
    method,
    payment_date,
    note=None,
):
    """
    Record a payment against an invoice.
    """

    if invoice.status not in ("confirmed", "paid"):
        raise ValueError(
            "Payments can only be recorded against confirmed invoices."
        )

    amount = money(amount)

    if amount <= MONEY_ZERO:
        raise ValueError("Payment amount must be greater than zero.")

    if amount > invoice.outstanding_amount:
        raise ValueError(
            "Payment cannot exceed the outstanding balance."
        )

    if not reference:
        raise ValueError("Payment reference is required.")

    payment = Payment(
        invoice=invoice,
        reference=reference,
        amount=amount,
        method=method,
        payment_date=payment_date,
        note=note,
        status="completed",
    )

    db.session.add(payment)

    db.session.flush()

    refresh_invoice_payment_status(invoice)

    return payment
