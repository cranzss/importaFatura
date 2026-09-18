"""Command-line entry point for converting statement PDFs to JSON."""

from argparse import ArgumentParser
from collections.abc import Sequence
from getpass import getpass
import os
from pathlib import Path
from tempfile import NamedTemporaryFile

from fatura_parser.issuer_detector import IssuerDetectionError
from fatura_parser.parsers.inter import InterParserError
from fatura_parser.parsers.mercado_pago import MercadoPagoParserError
from fatura_parser.pdf_extractor import PdfExtractionError, extract_pdf
from fatura_parser.statement_parser import (
    StatementParserError,
    parse_statement,
)
from fatura_parser.value_parsers import ValueParsingError


class JsonExportError(Exception):
    """Base error for expected failures while exporting statement JSON."""


class JsonOutputExistsError(JsonExportError):
    """Raised when an output file would be overwritten without permission."""


class StatementValidationError(JsonExportError):
    """Raised when statement validation does not allow a JSON export."""


def default_output_path(pdf_path: Path) -> Path:
    """Return the default JSON path for one input PDF."""
    return Path("output") / f"{pdf_path.stem}.json"


def _write_json_atomically(
    destination: Path,
    json_text: str,
    *,
    overwrite: bool,
) -> None:
    """Write complete JSON without exposing a partially written destination."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None

    try:
        with NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            dir=destination.parent,
            prefix=f".{destination.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary_file:
            temporary_path = Path(temporary_file.name)
            temporary_file.write(f"{json_text}\n")
            temporary_file.flush()
            os.fsync(temporary_file.fileno())

        if overwrite:
            os.replace(temporary_path, destination)
        else:
            try:
                os.link(temporary_path, destination)
            except FileExistsError as error:
                raise JsonOutputExistsError(
                    f"output file already exists: {destination}"
                ) from error
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def convert_pdf_to_json(
    pdf_path: str | Path,
    *,
    output_path: str | Path | None = None,
    password: str | None = None,
    overwrite: bool = False,
    allow_warnings: bool = False,
) -> Path:
    """Parse one statement PDF and write its complete validated JSON."""
    input_path = Path(pdf_path)
    destination = (
        Path(output_path)
        if output_path is not None
        else default_output_path(input_path)
    )

    if destination.exists() and not overwrite:
        raise JsonOutputExistsError(
            f"output file already exists: {destination}"
        )

    document = extract_pdf(input_path, password=password)
    result = parse_statement(document)

    if (
        not allow_warnings
        and (
            not result.validation.reconciled
            or result.validation.warnings
        )
    ):
        warning_codes = sorted(
            {
                warning.code
                for warning in result.validation.warnings
            }
        )
        issue_summary = ", ".join(warning_codes) or "UNRECONCILED"
        raise StatementValidationError(
            "statement validation blocked the JSON export: "
            f"{issue_summary}. Use --allow-warnings to export it "
            "for manual review."
        )

    json_text = result.model_dump_json(indent=2)
    _write_json_atomically(
        destination,
        json_text,
        overwrite=overwrite,
    )

    return destination


def build_argument_parser() -> ArgumentParser:
    """Create the command-line arguments accepted by the JSON exporter."""
    parser = ArgumentParser(
        allow_abbrev=False,
        description="Converte uma fatura em PDF para o JSON padronizado."
    )
    parser.add_argument(
        "pdf_path",
        type=Path,
        help="Caminho da fatura em PDF.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Caminho do JSON. O padrão é output/NOME-DA-FATURA.json.",
    )
    parser.add_argument(
        "--password-prompt",
        action="store_true",
        help="Solicita de forma oculta a senha de um PDF protegido.",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Permite substituir um JSON que já existe.",
    )
    parser.add_argument(
        "--allow-warnings",
        action="store_true",
        help="Permite exportar uma fatura divergente para revisão manual.",
    )
    return parser


def main(arguments: Sequence[str] | None = None) -> int:
    """Run the PDF-to-JSON conversion from command-line arguments."""
    argument_parser = build_argument_parser()
    parsed_arguments = argument_parser.parse_args(arguments)
    password = (
        getpass("Senha do PDF: ")
        if parsed_arguments.password_prompt
        else None
    )

    try:
        written_path = convert_pdf_to_json(
            pdf_path=parsed_arguments.pdf_path,
            output_path=parsed_arguments.output,
            password=password,
            overwrite=parsed_arguments.overwrite,
            allow_warnings=parsed_arguments.allow_warnings,
        )
    except (
        InterParserError,
        IssuerDetectionError,
        JsonExportError,
        MercadoPagoParserError,
        OSError,
        PdfExtractionError,
        StatementParserError,
        ValueParsingError,
    ) as error:
        argument_parser.error(str(error))

    print(f"JSON criado em: {written_path.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
