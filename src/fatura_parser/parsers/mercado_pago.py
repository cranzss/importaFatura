"""Extract structured information from Mercado Pago statements."""

from datetime import date as Date
import re
from unicodedata import combining, normalize

from fatura_parser.enums import Issuer, TransactionType
from fatura_parser.issuer_detector import detect_issuer
from fatura_parser.models import CardSummary, StatementInfo, Transaction
from fatura_parser.parsers.common import create_transaction_id
from fatura_parser.pdf_extractor import ExtractedPdf
from fatura_parser.value_parsers import (
    ValueParsingError,
    parse_brazilian_date,
    parse_brl_amount_to_cents,
)


_BRL_TEXT = r"R\$\s*(?:\d{1,3}(?:\.\d{3})+|\d+),\d{2}"
_FULL_DATE_TEXT = r"\d{2}/\d{2}/\d{4}"

_STATEMENT_SUMMARY_PATTERN = re.compile(
    r"Total a pagar\s+Vence em[^\n]*\n"
    rf"(?P<declared_total>{_BRL_TEXT})\s+"
    rf"(?P<due_date>{_FULL_DATE_TEXT})",
    flags=re.IGNORECASE,
)
_MINIMUM_PAYMENT_PATTERN = re.compile(
    r"O valor mínimo que você deve pagar é de\s+"
    rf"(?P<minimum_payment>{_BRL_TEXT})",
    flags=re.IGNORECASE,
)
_CLOSING_DATE_PATTERN = re.compile(
    rf"Fechamento da fatura\s+(?P<closing_date>{_FULL_DATE_TEXT})",
    flags=re.IGNORECASE,
)
_CARD_HEADER_PATTERN = re.compile(
    r"^Cartão\s+.+?\s+\[\*+"
    r"(?P<last_four>\d{4})\]$",
    flags=re.IGNORECASE,
)
_CARD_TOTAL_PATTERN = re.compile(
    rf"^Total\s+(?P<declared_total>{_BRL_TEXT})$",
    flags=re.IGNORECASE,
)
_TRANSACTION_LINE_PATTERN = re.compile(
    r"^(?P<date>\d{2}/\d{2})\s+"
    r"(?P<details>.+?)\s+"
    rf"(?P<amount>{_BRL_TEXT})$",
    flags=re.IGNORECASE,
)
_INSTALLMENT_PATTERN = re.compile(
    r"\s+Parcela\s+(?P<current>\d+)\s+de\s+(?P<total>\d+)\s*$",
    flags=re.IGNORECASE,
)


class MercadoPagoParserError(Exception):
    """Base error for expected Mercado Pago parsing failures."""


class UnexpectedMercadoPagoDocumentError(MercadoPagoParserError):
    """Raised when this parser receives another issuer's PDF."""


class MercadoPagoStatementFieldNotFoundError(MercadoPagoParserError):
    """Raised when a required statement summary field cannot be found."""


class MercadoPagoCardSummaryNotFoundError(MercadoPagoParserError):
    """Raised when a card section has no usable declared total."""


def _ensure_mercado_pago_document(document: ExtractedPdf) -> None:
    """Reject documents that were not issued by Mercado Pago."""
    if detect_issuer(document) is not Issuer.MERCADO_PAGO:
        raise UnexpectedMercadoPagoDocumentError(
            "Mercado Pago parser received a statement from another issuer"
        )


def _required_group(
    pattern: re.Pattern[str],
    group_name: str,
    text: str,
) -> str:
    """Return one required regex group or raise a parser-specific error."""
    match = pattern.search(text)
    if match is None:
        raise MercadoPagoStatementFieldNotFoundError(
            "required Mercado Pago statement field was not found: "
            f"{group_name}"
        )

    return match.group(group_name)


def parse_mercado_pago_statement_info(
    document: ExtractedPdf,
) -> StatementInfo:
    """Extract statement-level fields from a Mercado Pago PDF."""
    _ensure_mercado_pago_document(document)

    first_page_text = document.pages[0].text
    full_text = document.full_text
    summary_match = _STATEMENT_SUMMARY_PATTERN.search(first_page_text)
    if summary_match is None:
        raise MercadoPagoStatementFieldNotFoundError(
            "required Mercado Pago statement field was not found: summary"
        )

    minimum_payment_match = _MINIMUM_PAYMENT_PATTERN.search(full_text)
    minimum_payment_text = (
        minimum_payment_match.group("minimum_payment")
        if minimum_payment_match is not None
        else None
    )
    closing_date_text = _required_group(
        _CLOSING_DATE_PATTERN,
        "closing_date",
        full_text,
    )

    return StatementInfo(
        due_date=parse_brazilian_date(summary_match.group("due_date")),
        closing_date=parse_brazilian_date(closing_date_text),
        currency="BRL",
        declared_total_cents=parse_brl_amount_to_cents(
            summary_match.group("declared_total")
        ),
        minimum_payment_cents=(
            parse_brl_amount_to_cents(minimum_payment_text)
            if minimum_payment_text is not None
            else None
        ),
    )


def parse_mercado_pago_card_summaries(
    document: ExtractedPdf,
) -> list[CardSummary]:
    """Extract totals associated with Mercado Pago card sections."""
    _ensure_mercado_pago_document(document)

    summaries: list[CardSummary] = []
    current_last_four: str | None = None

    for page in document.pages:
        for raw_line in page.text.splitlines():
            line = raw_line.strip()
            header_match = _CARD_HEADER_PATTERN.fullmatch(line)
            if header_match is not None:
                if current_last_four is not None:
                    raise MercadoPagoCardSummaryNotFoundError(
                        "a new card section started before the previous total"
                    )

                current_last_four = header_match.group("last_four")
                continue

            total_match = _CARD_TOTAL_PATTERN.fullmatch(line)
            if total_match is None or current_last_four is None:
                continue

            summaries.append(
                CardSummary(
                    card_id=(
                        f"{Issuer.MERCADO_PAGO.value}:{current_last_four}"
                    ),
                    card_last_four=current_last_four,
                    declared_total_cents=parse_brl_amount_to_cents(
                        total_match.group("declared_total")
                    ),
                )
            )
            current_last_four = None

    if current_last_four is not None:
        raise MercadoPagoCardSummaryNotFoundError(
            "Mercado Pago card section has no declared total"
        )

    if not summaries:
        raise MercadoPagoCardSummaryNotFoundError(
            "no Mercado Pago card summaries were found"
        )

    return summaries


def _parse_inferred_transaction_date(
    value: str,
    closing_date: Date,
) -> Date:
    """Infer the year of a DD/MM transaction from the statement closing date."""
    match = re.fullmatch(r"(?P<day>\d{2})/(?P<month>\d{2})", value.strip())
    if match is None:
        raise ValueParsingError(
            f"invalid Brazilian day/month date: {value!r}"
        )

    day = int(match.group("day"))
    month = int(match.group("month"))
    year = closing_date.year
    if (month, day) > (closing_date.month, closing_date.day):
        year -= 1

    try:
        return Date(year, month, day)
    except ValueError as error:
        raise ValueParsingError(
            f"invalid Brazilian day/month date: {value!r}"
        ) from error


def _normalize_description(value: str) -> str:
    """Normalize accents, case, and whitespace for classification only."""
    decomposed = normalize("NFKD", value)
    without_accents = "".join(
        character
        for character in decomposed
        if not combining(character)
    )
    return " ".join(without_accents.casefold().split())


def _classify_transaction(details: str) -> TransactionType:
    """Classify a Mercado Pago movement from its description."""
    normalized_details = _normalize_description(details)

    if "pagamento da fatura" in normalized_details:
        return TransactionType.PAYMENT

    if any(
        marker in normalized_details
        for marker in ("estorno", "cancelamento", "credito devolvido")
    ):
        return TransactionType.REFUND

    if "iof" in normalized_details:
        return TransactionType.TAX

    if "juros" in normalized_details:
        return TransactionType.INTEREST

    if any(
        marker in normalized_details
        for marker in ("tarifa", "anuidade")
    ):
        return TransactionType.FEE

    if "saque" in normalized_details:
        return TransactionType.CASH_ADVANCE

    return TransactionType.PURCHASE


def parse_mercado_pago_transactions(
    document: ExtractedPdf,
) -> list[Transaction]:
    """Extract Mercado Pago payments and card transactions."""
    _ensure_mercado_pago_document(document)

    closing_date_text = _required_group(
        _CLOSING_DATE_PATTERN,
        "closing_date",
        document.full_text,
    )
    closing_date = parse_brazilian_date(closing_date_text)
    transactions: list[Transaction] = []
    current_card_id: str | None = None

    for page in document.pages:
        for line_number, raw_line in enumerate(
            page.text.splitlines(),
            start=1,
        ):
            line = raw_line.strip()
            header_match = _CARD_HEADER_PATTERN.fullmatch(line)
            if header_match is not None:
                last_four = header_match.group("last_four")
                current_card_id = (
                    f"{Issuer.MERCADO_PAGO.value}:{last_four}"
                )
                continue

            if (
                current_card_id is not None
                and _CARD_TOTAL_PATTERN.fullmatch(line) is not None
            ):
                current_card_id = None
                continue

            transaction_match = _TRANSACTION_LINE_PATTERN.fullmatch(line)
            if transaction_match is None:
                continue

            details = transaction_match.group("details").strip()
            installment_match = _INSTALLMENT_PATTERN.search(details)
            installment_data = None
            if installment_match is not None:
                installment_data = {
                    "current": int(installment_match.group("current")),
                    "total": int(installment_match.group("total")),
                }
                details = details[:installment_match.start()].strip()

            transaction_type = _classify_transaction(details)
            if (
                current_card_id is None
                and transaction_type is not TransactionType.PAYMENT
            ):
                raise MercadoPagoParserError(
                    "non-payment transaction found outside a card section"
                )

            amount_cents = parse_brl_amount_to_cents(
                transaction_match.group("amount")
            )
            if transaction_type in {
                TransactionType.PAYMENT,
                TransactionType.REFUND,
            }:
                amount_cents = -amount_cents

            transactions.append(
                Transaction(
                    transaction_id=create_transaction_id(
                        issuer=Issuer.MERCADO_PAGO,
                        document=document,
                        page_number=page.number,
                        line_number=line_number,
                    ),
                    card_id=current_card_id,
                    date=_parse_inferred_transaction_date(
                        transaction_match.group("date"),
                        closing_date,
                    ),
                    date_inferred=True,
                    description=details,
                    amount_cents=amount_cents,
                    type=transaction_type,
                    included_in_statement_total=(
                        transaction_type is not TransactionType.PAYMENT
                    ),
                    installment=installment_data,
                    source_page=page.number,
                )
            )

    return transactions
