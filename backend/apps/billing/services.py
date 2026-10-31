"""
Business logic and write services for billing (invoices, generation).
"""

from decimal import Decimal
from typing import Optional

from .models import Invoice, InvoiceDiscount, InvoiceLine


def confirm_invoice(invoice: Invoice) -> Invoice:
    """
    Confirm a draft invoice.
    Delegates to Invoice.confirm() which enforces status transitions and discount usage guards.
    """
    invoice.confirm()
    return invoice
