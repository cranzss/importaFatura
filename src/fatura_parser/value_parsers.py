"""Convert Brazilian formatted text into typed Python values."""

from datetime import date as Date
from datetime import datetime
import re


_BRL_AMOUNT_PATTERN = re.compile(
    r"^\s*(?P<sign>-)?R\$\s*"
    r"(?P<whole>(?:\d{1,3}(?:\.\d{3})+|\d+))"
    r",(?P<cents>\d{2})\s*$"
)
_BRAZILIAN_DATE_PATTERN = re.compile(r"^\d{2}/\d{2}/\d{4}$")

_BRAZILIAN_MONTH_NUMBERS = {
    "jan": 1,
    "fev": 2,
    "mar": 3,
    "abr": 4,
    "mai": 5,
    "jun": 6,
    "jul": 7,
    "ago": 8,
    "set": 9,
    "out": 10,
    "nov": 11,
    "dez": 12,
}

_BRAZILIAN_TEXTUAL_DATE_PATTERN = re.compile(
    r"^(?P<day>\d{2})\s+de\s+"
    r"(?P<month>jan|fev|mar|abr|mai|jun|jul|ago|set|out|nov|dez)"
    r"\.\s+"
    r"(?P<year>\d{4})$",
    flags=re.IGNORECASE,
)

class ValueParsingError(ValueError):
    """Raised when extracted text does not use the expected format."""


def parse_brl_amount_to_cents(value: str) -> int:
    """Convert a value such as 'R$ 1.234,56' to 123456 cents."""
    match = _BRL_AMOUNT_PATTERN.fullmatch(value)
    if match is None:
        raise ValueParsingError(f"invalid BRL amount: {value!r}")

    whole_reais = int(match.group("whole").replace(".", ""))
    cents = int(match.group("cents"))
    amount_cents = whole_reais * 100 + cents

    if match.group("sign") == "-":
        return -amount_cents

    return amount_cents


def parse_brazilian_date(value: str) -> Date:
    """Convert a DD/MM/YYYY string to a validated date."""
    stripped_value = value.strip()
    if _BRAZILIAN_DATE_PATTERN.fullmatch(stripped_value) is None:
        raise ValueParsingError(f"invalid Brazilian date: {value!r}")

    try:
        return datetime.strptime(stripped_value, "%d/%m/%Y").date()
    except ValueError as error:
        raise ValueParsingError(
            f"invalid Brazilian date: {value!r}"
        ) from error


def parse_brazilian_textual_date(value: str) -> Date:
    """Convert 'DD de MMM. YYYY' text to a validated date."""
    stripped_value = value.strip()

    match = _BRAZILIAN_TEXTUAL_DATE_PATTERN.fullmatch(
        stripped_value
    )

    if match is None:
        raise ValueParsingError(
            f"invalid Brazilian textual date: {value!r}"
        )

    day = int(match.group("day"))
    month_text = match.group("month").casefold()
    month = _BRAZILIAN_MONTH_NUMBERS[month_text]
    year = int(match.group("year"))

    try:
        return Date(year, month, day)
    except ValueError as error:
        raise ValueParsingError(
            f"invalid Brazilian textual date: {value!r}"
        ) from error