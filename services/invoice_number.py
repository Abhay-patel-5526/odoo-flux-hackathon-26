
from datetime import date
from uuid import uuid4


def generate_invoice_number():
    """
    Generate a unique invoice number.

    Example:
    INV-20261031-A1B2C3
    """
    today = date.today()

    unique_part = uuid4().hex[:6].upper()

    return f"INV-{today:%Y%m%d}-{unique_part}"
