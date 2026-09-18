"""Safe, bank-agnostic extraction of text and word positions from PDFs."""

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path

import pdfplumber
from pdfminer.pdfdocument import PDFPasswordIncorrect
from pdfminer.pdfparser import PDFSyntaxError
from pdfplumber.utils.exceptions import PdfminerException


DEFAULT_MAX_FILE_SIZE_BYTES = 20 * 1024 * 1024
DEFAULT_MAX_PAGE_COUNT = 100
HASH_CHUNK_SIZE_BYTES = 1024 * 1024
PDF_HEADER_SEARCH_BYTES = 1024


class PdfExtractionError(Exception):
    """Base error for expected PDF extraction failures."""


class PdfFileNotFoundError(PdfExtractionError):
    """Raised when the requested PDF does not exist or is not a file."""


class InvalidPdfError(PdfExtractionError):
    """Raised when a file is not a readable PDF."""


class PdfTooLargeError(PdfExtractionError):
    """Raised when a PDF exceeds the configured safety limit."""


class PdfTooManyPagesError(PdfExtractionError):
    """Raised when a PDF exceeds the configured page-count limit."""


class PdfPasswordError(PdfExtractionError):
    """Raised when an encrypted PDF cannot be opened with the given password."""


class PdfTextNotFoundError(PdfExtractionError):
    """Raised when a PDF has no text layer and would require OCR."""


@dataclass(frozen=True, slots=True)
class ExtractedWord:
    """One word and its position on a PDF page."""

    text: str
    x0: float
    x1: float
    top: float
    bottom: float


@dataclass(frozen=True, slots=True)
class ExtractedPage:
    """Text and positioned words extracted from one page."""

    number: int
    width: float
    height: float
    text: str
    words: tuple[ExtractedWord, ...]


@dataclass(frozen=True, slots=True)
class ExtractedPdf:
    """Bank-agnostic intermediate representation of a PDF."""

    filename: str
    file_sha256: str
    file_size_bytes: int
    pages: tuple[ExtractedPage, ...]

    @property
    def page_count(self) -> int:
        """Return the number of extracted pages."""
        return len(self.pages)

    @property
    def full_text(self) -> str:
        """Join page text with a form-feed marker between pages."""
        return "\n\f\n".join(page.text for page in self.pages)


def calculate_file_sha256(file_path: str | Path) -> str:
    """Calculate SHA-256 without loading the whole file into memory."""
    path = Path(file_path)
    digest = sha256()

    with path.open("rb") as binary_file:
        for chunk in iter(
            lambda: binary_file.read(HASH_CHUNK_SIZE_BYTES),
            b"",
        ):
            digest.update(chunk)

    return digest.hexdigest()


def extract_pdf(
    file_path: str | Path,
    *,
    password: str | None = None,
    max_file_size_bytes: int = DEFAULT_MAX_FILE_SIZE_BYTES,
    max_page_count: int = DEFAULT_MAX_PAGE_COUNT,
) -> ExtractedPdf:
    """Validate and extract a PDF without applying bank-specific rules."""
    path = Path(file_path)

    if max_page_count < 1:
        raise ValueError("max_page_count must be positive")

    if not path.is_file():
        raise PdfFileNotFoundError(f"PDF file was not found: {path.name}")

    if path.suffix.lower() != ".pdf":
        raise InvalidPdfError("file must use the .pdf extension")

    file_size_bytes = path.stat().st_size
    if file_size_bytes > max_file_size_bytes:
        raise PdfTooLargeError(
            f"PDF exceeds the {max_file_size_bytes}-byte safety limit"
        )

    with path.open("rb") as binary_file:
        header = binary_file.read(PDF_HEADER_SEARCH_BYTES)

    if b"%PDF-" not in header:
        raise InvalidPdfError("file content does not contain a PDF header")

    pages: list[ExtractedPage] = []

    try:
        with pdfplumber.open(path, password=password) as pdf:
            page_count = len(pdf.pages)
            if page_count > max_page_count:
                raise PdfTooManyPagesError(
                    f"PDF has {page_count} pages and exceeds the "
                    f"{max_page_count}-page safety limit"
                )

            for page_number, page in enumerate(pdf.pages, start=1):
                text = page.extract_text(x_tolerance=2, y_tolerance=3) or ""
                words = tuple(
                    ExtractedWord(
                        text=word["text"],
                        x0=float(word["x0"]),
                        x1=float(word["x1"]),
                        top=float(word["top"]),
                        bottom=float(word["bottom"]),
                    )
                    for word in page.extract_words()
                )
                pages.append(
                    ExtractedPage(
                        number=page_number,
                        width=float(page.width),
                        height=float(page.height),
                        text=text,
                        words=words,
                    )
                )
    except PDFPasswordIncorrect as error:
        raise PdfPasswordError("PDF password is missing or incorrect") from error
    except PDFSyntaxError as error:
        raise InvalidPdfError("PDF structure is invalid") from error
    except PdfminerException as error:
        original_error = error.args[0] if error.args else None

        if isinstance(original_error, PDFPasswordIncorrect):
            raise PdfPasswordError(
                "PDF password is missing or incorrect"
            ) from error

        if isinstance(original_error, PDFSyntaxError):
            raise InvalidPdfError("PDF structure is invalid") from error

        raise InvalidPdfError("PDF could not be parsed") from error

    if not pages:
        raise InvalidPdfError("PDF does not contain any pages")

    if not any(page.text.strip() for page in pages):
        raise PdfTextNotFoundError("PDF has no extractable text layer")

    return ExtractedPdf(
        filename=path.name,
        file_sha256=calculate_file_sha256(path),
        file_size_bytes=file_size_bytes,
        pages=tuple(pages),
    )
