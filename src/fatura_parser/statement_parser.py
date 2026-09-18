"""Coordinate issuer-specific parsers into one complete result."""

from fatura_parser.enums import Issuer
from fatura_parser.issuer_detector import build_source_info
from fatura_parser.models import ParserInfo, StatementParseResult
from fatura_parser.parsers.inter import (
    parse_inter_card_summaries,
    parse_inter_statement_info,
    parse_inter_transactions,
)
from fatura_parser.parsers.mercado_pago import (
    parse_mercado_pago_card_summaries,
    parse_mercado_pago_statement_info,
    parse_mercado_pago_transactions,
)
from fatura_parser.pdf_extractor import ExtractedPdf
from fatura_parser.validation import build_validation_info


_INTER_PARSER_VERSION = "0.1.0"
_MERCADO_PAGO_PARSER_VERSION = "0.1.0"


class StatementParserError(Exception):
    """Base error for failures while coordinating statement parsers."""


class StatementParserNotImplementedError(StatementParserError):
    """Raised when an issuer is recognized but has no parser yet."""


def parse_statement(document: ExtractedPdf) -> StatementParseResult:
    """Parse one extracted PDF into the complete statement model."""
    source = build_source_info(document)

    if source.issuer is Issuer.INTER:
        statement = parse_inter_statement_info(document)
        cards = parse_inter_card_summaries(document)
        transactions = parse_inter_transactions(document)
        parser_version = _INTER_PARSER_VERSION
    elif source.issuer is Issuer.MERCADO_PAGO:
        statement = parse_mercado_pago_statement_info(document)
        cards = parse_mercado_pago_card_summaries(document)
        transactions = parse_mercado_pago_transactions(document)
        parser_version = _MERCADO_PAGO_PARSER_VERSION
    else:
        raise StatementParserNotImplementedError(
            f"statement parser is not implemented for {source.issuer.value}"
        )

    validation = build_validation_info(
        statement=statement,
        cards=cards,
        transactions=transactions,
    )

    return StatementParseResult(
        schema_version="1.0",
        parser=ParserInfo(
            name=source.issuer,
            version=parser_version,
        ),
        source=source,
        statement=statement,
        cards=cards,
        transactions=transactions,
        validation=validation,
    )
