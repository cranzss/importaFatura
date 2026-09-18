"""Controlled vocabularies shared by models and parsers."""

from enum import StrEnum


class Issuer(StrEnum):
    """Financial institutions currently supported by the parser."""

    INTER = "inter"
    MERCADO_PAGO = "mercado_pago"


class TransactionType(StrEnum):
    """Accounting meaning assigned to an extracted transaction."""

    PURCHASE = "purchase"
    PAYMENT = "payment"
    REFUND = "refund"
    FEE = "fee"
    INTEREST = "interest"
    TAX = "tax"
    CASH_ADVANCE = "cash_advance"
    OTHER = "other"
