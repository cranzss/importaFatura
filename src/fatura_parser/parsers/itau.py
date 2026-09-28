"""Extract structured information from Itaú credit-card statements."""

from dataclasses import dataclass
from datetime import date as Date
import re
from unicodedata import combining, normalize

from fatura_parser.enums import Issuer, TransactionType
from fatura_parser.issuer_detector import detect_issuer
from fatura_parser.models import CardSummary, Installment, StatementInfo, Transaction
from fatura_parser.parsers.common import create_transaction_id
from fatura_parser.pdf_extractor import ExtractedPdf, ExtractedWord
from fatura_parser.value_parsers import (
    ValueParsingError,
    parse_brazilian_date,
    parse_brl_amount_to_cents,
)


_AMOUNT_TEXT = r"-?(?:\d{1,3}(?:\.\d{3})+|\d+),\d{2}"
_FULL_DATE_TEXT = r"\d{2}/\d{2}/\d{4}"

_DUE_DATE_PATTERN = re.compile(
    rf"Vencimento:\s*(?P<due_date>{_FULL_DATE_TEXT})",
    flags=re.IGNORECASE,
)
_CLOSING_DATE_PATTERN = re.compile(
    rf"Emiss.o:\s*(?P<closing_date>{_FULL_DATE_TEXT})",
    flags=re.IGNORECASE,
)
_STATEMENT_TOTAL_PATTERN = re.compile(
    rf"Total desta fatura\s+(?P<amount>{_AMOUNT_TEXT})",
    flags=re.IGNORECASE,
)
_MINIMUM_PAYMENT_PATTERN = re.compile(
    rf"Pagamento m.nimo:[^\n]*\n\s*R\$\s*(?P<amount>{_AMOUNT_TEXT})",
    flags=re.IGNORECASE,
)
_CARD_PATTERN = re.compile(
    r"Cart.o\s+\d{4}\.[X*]{4}\.[X*]{4}\.(?P<last_four>\d{4})",
    flags=re.IGNORECASE,
)
_PREVIOUS_BALANCE_PATTERN = re.compile(
    rf"Total da fatura anterior\s+(?P<amount>{_AMOUNT_TEXT})",
    flags=re.IGNORECASE,
)
_PAYMENTS_TOTAL_PATTERN = re.compile(
    rf"Total dos pagamentos\s+(?P<amount>{_AMOUNT_TEXT})",
    flags=re.IGNORECASE,
)
_DOMESTIC_TOTAL_PATTERN = re.compile(
    rf"Lan.amentos no cart.o\s+(?P<amount>{_AMOUNT_TEXT})",
    flags=re.IGNORECASE,
)
_INTERNATIONAL_TRANSACTIONS_TOTAL_PATTERN = re.compile(
    rf"Total transa..es inter\. em R\$\s+(?P<amount>{_AMOUNT_TEXT})",
    flags=re.IGNORECASE,
)
_IOF_PATTERN = re.compile(
    rf"Repasse de IOF em R\$\s+(?P<amount>{_AMOUNT_TEXT})",
    flags=re.IGNORECASE,
)
_INTERNATIONAL_TOTAL_PATTERN = re.compile(
    rf"Total lan.amentos inter\. em R\$\s+(?P<amount>{_AMOUNT_TEXT})",
    flags=re.IGNORECASE,
)
_CURRENT_CHARGES_TOTAL_PATTERN = re.compile(
    rf"Total dos lan.amentos atuais\s+(?P<amount>{_AMOUNT_TEXT})",
    flags=re.IGNORECASE,
)
_TRANSACTION_LINE_PATTERN = re.compile(
    r"^(?P<date>\d{2}/\d{2})\s*"
    r"(?P<details>.+?)\s+"
    rf"(?P<amount>{_AMOUNT_TEXT})$",
    flags=re.IGNORECASE,
)
_INSTALLMENT_PATTERN = re.compile(
    r"(?<!\d)(?P<current>\d{2})/(?P<total>\d{2})(?!\d)"
)

_COLUMN_LEFT_RATIO = 0.20
_COLUMN_SPLIT_RATIO = 0.58
_COLUMN_RIGHT_RATIO = 0.96
_LINE_TOP_TOLERANCE = 2.5


class ItauParserError(Exception):
    """Base error for expected Itaú parsing failures."""


class UnexpectedItauDocumentError(ItauParserError):
    """Raised when this parser receives another issuer's PDF."""


class ItauStatementFieldNotFoundError(ItauParserError):
    """Raised when a required statement summary field cannot be found."""


class ItauCardSummaryNotFoundError(ItauParserError):
    """Raised when a supported card summary cannot be extracted."""


@dataclass(frozen=True, slots=True)
class _LayoutLine:
    """One visual line rebuilt from words in a single PDF column."""

    text: str
    page_number: int
    source_line: int


@dataclass(frozen=True, slots=True)
class _PendingTransaction:
    """Transaction fields kept temporarily while reading continuations."""

    date_text: str
    details: str
    amount_text: str
    page_number: int
    source_line: int


def _ensure_itau_document(document: ExtractedPdf) -> None:
    """Reject documents that were not issued by Itaú."""
    if detect_issuer(document) is not Issuer.ITAU:
        raise UnexpectedItauDocumentError(
            "Itau parser received a statement from another issuer"
        )


def _required_group(
    pattern: re.Pattern[str],
    group_name: str,
    text: str,
) -> str:
    """Return a required regex group with an Itaú-specific error."""
    match = pattern.search(text)
    if match is None:
        raise ItauStatementFieldNotFoundError(
            f"required Itau statement field was not found: {group_name}"
        )

    return match.group(group_name)


def _amount_to_cents(value: str) -> int:
    """Parse an Itaú amount whose rows omit the ``R$`` prefix."""
    stripped_value = value.strip()
    if stripped_value.startswith("-"):
        return parse_brl_amount_to_cents(f"-R$ {stripped_value[1:]}")

    return parse_brl_amount_to_cents(f"R$ {stripped_value}")


def _normalize_text(value: str) -> str:
    """Normalize text used only for comparisons, preserving output text."""
    decomposed = normalize("NFKD", value)
    without_accents = "".join(
        character
        for character in decomposed
        if not combining(character)
    )
    return " ".join(without_accents.casefold().split())


def _matches(value: str, pattern: str) -> bool:
    """Match a normalized label while tolerating a damaged accent glyph."""
    return re.search(pattern, _normalize_text(value)) is not None


def _group_words_into_lines(
    words: list[ExtractedWord],
) -> list[str]:
    """Rebuild visual lines from positioned words in one column."""
    ordered_words = sorted(words, key=lambda word: (word.top, word.x0))
    grouped_words: list[list[ExtractedWord]] = []
    line_top: float | None = None

    for word in ordered_words:
        if (
            line_top is None
            or abs(word.top - line_top) > _LINE_TOP_TOLERANCE
        ):
            grouped_words.append([word])
            line_top = word.top
        else:
            grouped_words[-1].append(word)

    return [
        " ".join(
            word.text
            for word in sorted(line_words, key=lambda word: word.x0)
        ).strip()
        for line_words in grouped_words
    ]


def _extract_column_lines(document: ExtractedPdf) -> list[_LayoutLine]:
    """Read transaction pages in left-to-right column order."""
    result: list[_LayoutLine] = []

    for page in document.pages[1:]:
        column_bounds = (
            (
                page.width * _COLUMN_LEFT_RATIO,
                page.width * _COLUMN_SPLIT_RATIO,
            ),
            (
                page.width * _COLUMN_SPLIT_RATIO,
                page.width * _COLUMN_RIGHT_RATIO,
            ),
        )

        for column_number, (left, right) in enumerate(
            column_bounds,
            start=1,
        ):
            column_words = [
                word for word in page.words if left <= word.x0 < right
            ]
            for line_number, text in enumerate(
                _group_words_into_lines(column_words),
                start=1,
            ):
                result.append(
                    _LayoutLine(
                        text=text,
                        page_number=page.number,
                        source_line=column_number * 10_000 + line_number,
                    )
                )

    return result


def _parse_inferred_transaction_date(
    value: str,
    closing_date: Date,
) -> Date:
    """Infer the year of a DD/MM date from the statement closing date."""
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


def _classify_card_transaction(
    details: str,
    amount_cents: int,
) -> TransactionType:
    """Classify a card movement using labels present in Itaú rows."""
    normalized_details = _normalize_text(details)

    if amount_cents < 0 or any(
        marker in normalized_details
        for marker in ("estorno", "cancelamento", "credito devolvido")
    ):
        return TransactionType.REFUND
    if "iof" in normalized_details:
        return TransactionType.TAX
    if "juros" in normalized_details:
        return TransactionType.INTEREST
    if any(marker in normalized_details for marker in ("tarifa", "anuidade")):
        return TransactionType.FEE
    if "saque" in normalized_details:
        return TransactionType.CASH_ADVANCE

    return TransactionType.PURCHASE


def _split_installment(details: str) -> tuple[str, Installment | None]:
    """Remove an Itaú ``current/total`` marker from a description."""
    match = _INSTALLMENT_PATTERN.search(details)
    if match is None:
        return details.strip(), None

    description_without_marker = (
        f"{details[:match.start()]} {details[match.end():]}"
    )
    return (
        " ".join(description_without_marker.split()),
        Installment(
            current=int(match.group("current")),
            total=int(match.group("total")),
        ),
    )


def _parse_transaction_line(line: _LayoutLine) -> _PendingTransaction | None:
    """Parse one dated visual line, leaving continuation handling to callers."""
    match = _TRANSACTION_LINE_PATTERN.fullmatch(line.text.strip())
    if match is None:
        return None

    return _PendingTransaction(
        date_text=match.group("date"),
        details=match.group("details").strip(),
        amount_text=match.group("amount"),
        page_number=line.page_number,
        source_line=line.source_line,
    )


def _build_card_transaction(
    raw: _PendingTransaction,
    *,
    document: ExtractedPdf,
    closing_date: Date,
    card_id: str,
) -> Transaction:
    """Convert a buffered Itaú row into the public transaction model."""
    amount_cents = _amount_to_cents(raw.amount_text)
    details, installment = _split_installment(raw.details)
    transaction_type = _classify_card_transaction(details, amount_cents)
    if installment is not None and transaction_type is not TransactionType.PURCHASE:
        raise ItauParserError(
            "installment marker was found on a non-purchase Itau transaction"
        )

    return Transaction(
        transaction_id=create_transaction_id(
            issuer=Issuer.ITAU,
            document=document,
            page_number=raw.page_number,
            line_number=raw.source_line,
        ),
        card_id=card_id,
        date=_parse_inferred_transaction_date(raw.date_text, closing_date),
        date_inferred=True,
        description=details,
        amount_cents=amount_cents,
        type=transaction_type,
        included_in_statement_total=True,
        installment=installment,
        source_page=raw.page_number,
    )


def _is_domestic_section_end(text: str) -> bool:
    """Identify the first label after a domestic purchases block."""
    return any(
        _matches(text, pattern)
        for pattern in (
            r"lan.amentos no cart.o",
            r"lan.amentos internacionais",
            r"compras parceladas",
            r"total dos lan.amentos atuais",
            r"continua",
        )
    )


def _extract_domestic_rows(lines: list[_LayoutLine]) -> list[_PendingTransaction]:
    """Extract domestic rows and attach their optional continuation line."""
    result: list[_PendingTransaction] = []
    in_section = False
    pending: _PendingTransaction | None = None

    def flush_pending() -> None:
        nonlocal pending
        if pending is not None:
            result.append(pending)
            pending = None

    for line in lines:
        if _matches(line.text, r"lan.amentos:\s*compras e saques"):
            flush_pending()
            in_section = True
            continue

        if not in_section:
            continue

        if _is_domestic_section_end(line.text):
            flush_pending()
            in_section = False
            continue

        parsed = _parse_transaction_line(line)
        if parsed is not None:
            flush_pending()
            pending = parsed
            continue

        if pending is not None and line.text.strip():
            pending = _PendingTransaction(
                date_text=pending.date_text,
                details=f"{pending.details} {line.text.strip()}",
                amount_text=pending.amount_text,
                page_number=pending.page_number,
                source_line=pending.source_line,
            )

    flush_pending()
    return result


def _extract_international_rows(
    lines: list[_LayoutLine],
) -> list[_PendingTransaction]:
    """Extract only dated BRL rows from the international section."""
    result: list[_PendingTransaction] = []
    in_section = False

    for line in lines:
        if _matches(line.text, r"lan.amentos internacionais"):
            in_section = True
            continue
        if in_section and _matches(line.text, r"total transa..es inter"):
            in_section = False
            continue
        if not in_section:
            continue

        parsed = _parse_transaction_line(line)
        if parsed is not None:
            result.append(parsed)

    return result


def _assert_total(label: str, computed: int, declared: int) -> None:
    """Stop rather than emit incomplete data when an Itaú subtotal differs."""
    if computed != declared:
        raise ItauParserError(
            f"Itau {label} total does not reconcile: "
            f"computed={computed}, declared={declared}"
        )


def parse_itau_statement_info(document: ExtractedPdf) -> StatementInfo:
    """Extract statement-level fields from an Itaú PDF."""
    _ensure_itau_document(document)
    first_page_text = document.pages[0].text

    minimum_match = _MINIMUM_PAYMENT_PATTERN.search(first_page_text)
    minimum_payment_cents = (
        _amount_to_cents(minimum_match.group("amount"))
        if minimum_match is not None
        else None
    )

    return StatementInfo(
        due_date=parse_brazilian_date(
            _required_group(_DUE_DATE_PATTERN, "due_date", first_page_text)
        ),
        closing_date=parse_brazilian_date(
            _required_group(
                _CLOSING_DATE_PATTERN,
                "closing_date",
                first_page_text,
            )
        ),
        currency="BRL",
        declared_total_cents=_amount_to_cents(
            _required_group(
                _STATEMENT_TOTAL_PATTERN,
                "amount",
                first_page_text,
            )
        ),
        minimum_payment_cents=minimum_payment_cents,
    )


def parse_itau_card_summaries(document: ExtractedPdf) -> list[CardSummary]:
    """Extract the current-charge total for the Itaú card in the PDF."""
    _ensure_itau_document(document)
    last_fours = set(_CARD_PATTERN.findall(document.full_text))
    if len(last_fours) != 1:
        raise ItauCardSummaryNotFoundError(
            "expected exactly one Itaú card number in the supported layout"
        )

    last_four = next(iter(last_fours))
    total_text = _required_group(
        _CURRENT_CHARGES_TOTAL_PATTERN,
        "amount",
        document.full_text,
    )

    return [
        CardSummary(
            card_id=f"{Issuer.ITAU.value}:{last_four}",
            card_last_four=last_four,
            declared_total_cents=_amount_to_cents(total_text),
        )
    ]


def parse_itau_transactions(document: ExtractedPdf) -> list[Transaction]:
    """Extract balances, payments, purchases, and IOF from an Itaú PDF."""
    _ensure_itau_document(document)
    statement = parse_itau_statement_info(document)
    card = parse_itau_card_summaries(document)[0]
    closing_date = statement.closing_date
    if closing_date is None:
        raise ItauParserError("Itau closing date is required for transactions")

    transactions: list[Transaction] = []
    first_page_text = document.pages[0].text
    previous_balance_text = _required_group(
        _PREVIOUS_BALANCE_PATTERN,
        "amount",
        first_page_text,
    )
    previous_balance_cents = _amount_to_cents(previous_balance_text)
    if previous_balance_cents != 0:
        transactions.append(
            Transaction(
                transaction_id=create_transaction_id(
                    issuer=Issuer.ITAU,
                    document=document,
                    page_number=1,
                    line_number=1,
                ),
                card_id=None,
                date=closing_date,
                date_inferred=True,
                description="SALDO DA FATURA ANTERIOR",
                amount_cents=previous_balance_cents,
                type=TransactionType.OTHER,
                included_in_statement_total=True,
                installment=None,
                source_page=1,
            )
        )

    layout_lines = _extract_column_lines(document)
    in_payments = False
    payment_total_cents = 0
    for line in layout_lines:
        if _matches(line.text, r"pagamentos efetuados"):
            in_payments = True
            continue
        if in_payments and _matches(line.text, r"total dos pagamentos"):
            in_payments = False
            continue
        if not in_payments:
            continue

        raw_payment = _parse_transaction_line(line)
        if raw_payment is None:
            continue
        amount_cents = _amount_to_cents(raw_payment.amount_text)
        if amount_cents > 0:
            amount_cents = -amount_cents
        if amount_cents == 0:
            continue
        payment_total_cents += amount_cents
        transactions.append(
            Transaction(
                transaction_id=create_transaction_id(
                    issuer=Issuer.ITAU,
                    document=document,
                    page_number=raw_payment.page_number,
                    line_number=raw_payment.source_line,
                ),
                card_id=None,
                date=_parse_inferred_transaction_date(
                    raw_payment.date_text,
                    closing_date,
                ),
                date_inferred=True,
                description=raw_payment.details,
                amount_cents=amount_cents,
                type=TransactionType.PAYMENT,
                included_in_statement_total=True,
                installment=None,
                source_page=raw_payment.page_number,
            )
        )

    declared_payments = _amount_to_cents(
        _required_group(
            _PAYMENTS_TOTAL_PATTERN,
            "amount",
            document.full_text,
        )
    )
    _assert_total("payments", payment_total_cents, declared_payments)

    domestic_rows = _extract_domestic_rows(layout_lines)
    domestic_transactions = [
        _build_card_transaction(
            row,
            document=document,
            closing_date=closing_date,
            card_id=card.card_id,
        )
        for row in domestic_rows
    ]
    declared_domestic = _amount_to_cents(
        _required_group(
            _DOMESTIC_TOTAL_PATTERN,
            "amount",
            document.full_text,
        )
    )
    _assert_total(
        "domestic transactions",
        sum(transaction.amount_cents for transaction in domestic_transactions),
        declared_domestic,
    )
    transactions.extend(domestic_transactions)

    international_rows = _extract_international_rows(layout_lines)
    international_transactions = [
        _build_card_transaction(
            row,
            document=document,
            closing_date=closing_date,
            card_id=card.card_id,
        )
        for row in international_rows
    ]
    international_match = _INTERNATIONAL_TRANSACTIONS_TOTAL_PATTERN.search(
        document.full_text
    )
    declared_international = (
        _amount_to_cents(international_match.group("amount"))
        if international_match is not None
        else 0
    )
    _assert_total(
        "international transactions",
        sum(
            transaction.amount_cents
            for transaction in international_transactions
        ),
        declared_international,
    )
    transactions.extend(international_transactions)

    iof_match = _IOF_PATTERN.search(document.full_text)
    iof_cents = (
        _amount_to_cents(iof_match.group("amount"))
        if iof_match is not None
        else 0
    )
    if iof_cents != 0:
        iof_page_number = next(
            page.number
            for page in document.pages
            if _IOF_PATTERN.search(page.text) is not None
        )
        transactions.append(
            Transaction(
                transaction_id=create_transaction_id(
                    issuer=Issuer.ITAU,
                    document=document,
                    page_number=iof_page_number,
                    line_number=90_001,
                ),
                card_id=card.card_id,
                date=closing_date,
                date_inferred=True,
                description="REPASSE DE IOF",
                amount_cents=iof_cents,
                type=TransactionType.TAX,
                included_in_statement_total=True,
                installment=None,
                source_page=iof_page_number,
            )
        )

    international_total_match = _INTERNATIONAL_TOTAL_PATTERN.search(
        document.full_text
    )
    if international_total_match is not None:
        declared_international_with_tax = _amount_to_cents(
            international_total_match.group("amount")
        )
        _assert_total(
            "international charges",
            declared_international + iof_cents,
            declared_international_with_tax,
        )

    card_transactions_total = sum(
        transaction.amount_cents
        for transaction in transactions
        if transaction.card_id == card.card_id
    )
    _assert_total(
        "current charges",
        card_transactions_total,
        card.declared_total_cents,
    )

    return transactions
