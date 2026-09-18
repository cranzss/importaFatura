"""Extract structured information from Banco Inter statements."""

import re

from fatura_parser.enums import Issuer, TransactionType
from fatura_parser.issuer_detector import detect_issuer
from fatura_parser.models import CardSummary, StatementInfo, Transaction
from fatura_parser.parsers.common import create_transaction_id
from fatura_parser.pdf_extractor import ExtractedPdf
from fatura_parser.value_parsers import (
    parse_brazilian_date,
    parse_brazilian_textual_date,
    parse_brl_amount_to_cents,
)


_BRL_TEXT = r"R\$\s*(?:\d{1,3}(?:\.\d{3})+|\d+),\d{2}"
_SUMMARY_TOTAL_PATTERN = re.compile(
    r"Limite de crédito total\s+"
    r"Total da sua fatura\s+"
    rf"{_BRL_TEXT}\s+"
    rf"(?P<declared_total>{_BRL_TEXT})",
    flags=re.IGNORECASE,
)
_DUE_DATE_PATTERN = re.compile(
    r"Data de Vencimento\s*\n"
    r"[^\n]*?(?P<due_date>\d{2}/\d{2}/\d{4})",
    flags=re.IGNORECASE,
)
_MINIMUM_PAYMENT_PATTERN = re.compile(
    rf"Pagamento mínimo:\s*(?P<minimum_payment>{_BRL_TEXT})",
    flags=re.IGNORECASE,
)

_CARD_TOTAL_PATTERN = re.compile(
    rf"^Total CARTÃO\s+\d{{4}}\*+"
    rf"(?P<last_four>\d{{4}})\s+"
    rf"(?P<declared_total>{_BRL_TEXT})$",
    flags=re.IGNORECASE | re.MULTILINE,
)

_INTER_DATE_TEXT = (
    r"\d{2}\s+de\s+"
    r"(?:jan|fev|mar|abr|mai|jun|jul|ago|set|out|nov|dez)\.\s+"
    r"\d{4}"
)

_TRANSACTION_LINE_PATTERN = re.compile(
    rf"^(?P<date>{_INTER_DATE_TEXT})\s+"
    rf"(?P<details>.+?)\s+"
    rf"(?:-\s+)?"
    rf"(?P<credit_marker>\+\s+)?"
    rf"(?P<amount>{_BRL_TEXT})$",
    flags=re.IGNORECASE,
)

_INSTALLMENT_PATTERN = re.compile(
    r"\s*\(Parcela\s+"
    r"(?P<current>\d{2})\s+de\s+"
    r"(?P<total>\d{2})"
    r"\)\s*",
    flags=re.IGNORECASE,
)

_CARD_HEADER_PATTERN = re.compile(
    r"^CARTÃO\s+\d{4}\*+"
    r"(?P<last_four>\d{4})$",
    flags=re.IGNORECASE,
)

class InterParserError(Exception):
    """Base error for expected Banco Inter parsing failures."""


class UnexpectedInterDocumentError(InterParserError):
    """Raised when the Inter parser receives another issuer's PDF."""


class InterStatementFieldNotFoundError(InterParserError):
    """Raised when a required statement summary field cannot be found."""


class InterCardSummaryNotFoundError(InterParserError):
    """Raised when a required card summary field cannot be found."""


def _required_group(
    pattern: re.Pattern[str],
    group_name: str,
    text: str,
) -> str:
    """Return one required regex group or raise a parser-specific error."""
    match = pattern.search(text)
    if match is None:
        raise InterStatementFieldNotFoundError(
            f"required Inter statement field was not found: {group_name}"
        )

    return match.group(group_name)


def parse_inter_statement_info(document: ExtractedPdf) -> StatementInfo:
    """Extract and validate statement-level fields from an Inter PDF."""
    if detect_issuer(document) is not Issuer.INTER:
        raise UnexpectedInterDocumentError(
            "Inter parser received a statement from another issuer"
        )

    first_page_text = document.pages[0].text.replace("\r\n", "\n").replace(
        "\r", "\n"
    )
    declared_total_text = _required_group(
        _SUMMARY_TOTAL_PATTERN,
        "declared_total",
        first_page_text,
    )
    due_date_text = _required_group(
        _DUE_DATE_PATTERN,
        "due_date",
        first_page_text,
    )
    minimum_payment_match = _MINIMUM_PAYMENT_PATTERN.search(first_page_text)
    minimum_payment_text = (
        minimum_payment_match.group("minimum_payment")
        if minimum_payment_match is not None
        else None
    )

    return StatementInfo(
        due_date=parse_brazilian_date(due_date_text),
        closing_date=None,
        currency="BRL",
        declared_total_cents=parse_brl_amount_to_cents(declared_total_text),
        minimum_payment_cents=(
            parse_brl_amount_to_cents(minimum_payment_text)
            if minimum_payment_text is not None
            else None
        ),
    )


def parse_inter_card_summaries(document: ExtractedPdf) -> list[CardSummary]:
    """Extract and validate card-level fields from an Inter PDF."""
    summaries: list[CardSummary] = []

    if detect_issuer(document) is not Issuer.INTER:
        raise UnexpectedInterDocumentError(
            "Inter parser received a statement from another issuer"
            )

    for page in document.pages:
        for match in _CARD_TOTAL_PATTERN.finditer(page.text):
            last_four = match.group("last_four")
            declared_total_text = match.group("declared_total")

            summaries.append(
                CardSummary(
                    card_id=f"{Issuer.INTER.value}:{last_four}",
                    card_last_four=last_four,
                    declared_total_cents=parse_brl_amount_to_cents(
                        declared_total_text
                    ),
                )
            )

    if not summaries:
        raise InterCardSummaryNotFoundError(
            "no Inter card summaries were found"
        )
    return summaries


def _parse_inter_transaction_amount_to_cents(
    amount_text: str,
    credit_marker: str | None,
) -> int:
    """Convert an Inter amount using our accounting sign convention."""
    amount_cents = parse_brl_amount_to_cents(amount_text)

    if credit_marker is None:
        return amount_cents

    if credit_marker.strip() == "+":
        return -amount_cents

    raise InterParserError(
        f"unsupported Inter credit marker: {credit_marker!r}"
    )


def _classify_inter_transaction(
    details: str,
    credit_marker: str | None,
) -> TransactionType:
    """Classify one Inter transaction from its extracted description."""
    normalized_details = " ".join(
        details.casefold().split()
    )

    if "pagamento" in normalized_details:
        return TransactionType.PAYMENT

    if (
        "estorno" in normalized_details
        or "cancelamento" in normalized_details
    ):
        return TransactionType.REFUND

    if "iof" in normalized_details:
        return TransactionType.TAX

    if "juros" in normalized_details:
        return TransactionType.INTEREST

    if (
        "tarifa" in normalized_details
        or "anuidade" in normalized_details
    ):
        return TransactionType.FEE

    if "pix cred" in normalized_details:
        return TransactionType.CASH_ADVANCE

    if credit_marker is not None:
        return TransactionType.OTHER

    return TransactionType.PURCHASE


def _is_included_in_statement_total(
    transaction_type: TransactionType,
) -> bool:
    """Return whether a transaction composes the current statement total."""
    return transaction_type is not TransactionType.PAYMENT


def parse_inter_transactions (document: ExtractedPdf) -> list[Transaction]:

    transactions: list[Transaction] = []
    current_card_id: str | None = None

    if detect_issuer(document) is not Issuer.INTER:
        raise UnexpectedInterDocumentError(
            "Inter parser received a statement from another issuer"
        )

    for page in document.pages:
        for line_number, line in enumerate(
            page.text.splitlines(),
            start=1,
        ):
            header_match = _CARD_HEADER_PATTERN.fullmatch(line)

            if header_match is not None:
                last_four = header_match.group("last_four")
                current_card_id = (
                    f"{Issuer.INTER.value}:{last_four}"
                )
                continue

            if _CARD_TOTAL_PATTERN.fullmatch(line) is not None:
                current_card_id = None
                continue

            transaction_match = (
                _TRANSACTION_LINE_PATTERN.fullmatch(line)
            )

            if transaction_match is None:
                continue

            if current_card_id is None:
                raise InterParserError(
                    "transaction found outside a card section"
                )

            transaction_date_text = transaction_match.group("date")
            transaction_date = parse_brazilian_textual_date(
                transaction_date_text
            )

            details = transaction_match.group("details")
            credit_marker = transaction_match.group("credit_marker")
            amount_text = transaction_match.group("amount")
            amount_cents = _parse_inter_transaction_amount_to_cents(
                amount_text=amount_text,
                credit_marker=credit_marker,
            )

            transaction_type = _classify_inter_transaction(
                details=details,
                credit_marker=credit_marker,
            )

            included_in_statement_total = (
                _is_included_in_statement_total(
                    transaction_type
                )
            )

            installment_data = None

            installment_match = (
                _INSTALLMENT_PATTERN.search(details)
            )

            if installment_match is not None:
                installment_data = {
                    "current": int(installment_match.group("current")),
                    "total": int(installment_match.group("total")),
                }

            transaction_id = create_transaction_id(
                issuer=Issuer.INTER,
                document=document,
                page_number=page.number,
                line_number=line_number,
            )

            transactions.append(
                Transaction(
                    transaction_id=transaction_id,
                    card_id=current_card_id,
                    date=transaction_date,
                    date_inferred=False,
                    description=details,
                    amount_cents=amount_cents,
                    type=transaction_type,
                    included_in_statement_total=(
                        included_in_statement_total
                    ),
                    installment=installment_data,
                    source_page=page.number,
                )
            )

    return transactions
