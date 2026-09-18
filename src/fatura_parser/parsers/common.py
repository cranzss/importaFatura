"""Helpers shared by issuer-specific statement parsers."""

from hashlib import sha256

from fatura_parser.enums import Issuer
from fatura_parser.pdf_extractor import ExtractedPdf


def create_transaction_id(
    issuer: Issuer,
    document: ExtractedPdf,
    page_number: int,
    line_number: int,
) -> str:
    """Create a deterministic ID from a transaction's source location."""
    identity_source = (
        f"{issuer.value}|"
        f"{document.file_sha256}|"
        f"{page_number}|"
        f"{line_number}"
    )
    identity_hash = sha256(identity_source.encode("utf-8")).hexdigest()

    return f"txn_{identity_hash[:24]}"
