"""Identify the statement issuer from institutional text in the PDF."""

from unicodedata import normalize

from fatura_parser.enums import Issuer
from fatura_parser.models import SourceInfo
from fatura_parser.pdf_extractor import ExtractedPdf


_ISSUER_SIGNATURES: dict[Issuer, tuple[str, ...]] = {
    Issuer.INTER: (
        "conta do inter",
        "banco inter s.a.",
    ),
    Issuer.MERCADO_PAGO: (
        "app mercado pago",
        "mercado pago",
    ),
}


class IssuerDetectionError(Exception):
    """Base error for expected issuer-detection failures."""


class UnsupportedIssuerError(IssuerDetectionError):
    """Raised when the first page has no supported issuer signature."""


class AmbiguousIssuerError(IssuerDetectionError):
    """Raised when the first page matches more than one supported issuer."""


def _normalize_text(text: str) -> str:
    """Normalize case and whitespace before comparing institutional text."""
    compatible_text = normalize("NFKC", text)
    return " ".join(compatible_text.casefold().split())


def detect_issuer(document: ExtractedPdf) -> Issuer:
    """Detect one supported issuer using only the PDF's first-page text."""
    if not document.pages:
        raise UnsupportedIssuerError("PDF does not contain a page to inspect")

    first_page_text = _normalize_text(document.pages[0].text)
    matched_issuers = [
        issuer
        for issuer, signatures in _ISSUER_SIGNATURES.items()
        if any(signature in first_page_text for signature in signatures)
    ]

    if not matched_issuers:
        raise UnsupportedIssuerError(
            "PDF does not match a supported statement issuer"
        )

    if len(matched_issuers) > 1:
        raise AmbiguousIssuerError(
            "PDF matches more than one supported statement issuer"
        )

    return matched_issuers[0]


def build_source_info(document: ExtractedPdf) -> SourceInfo:
    """Convert extracted PDF metadata into the validated JSON source model."""
    return SourceInfo(
        issuer=detect_issuer(document),
        filename=document.filename,
        file_sha256=document.file_sha256,
        page_count=document.page_count,
    )
