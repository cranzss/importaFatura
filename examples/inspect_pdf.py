"""Show what the generic PDF extractor can currently read."""
import json

from argparse import ArgumentParser
from collections.abc import Sequence
from getpass import getpass
from pathlib import Path

from fatura_parser import (
    InterParserError,
    Issuer,
    IssuerDetectionError,
    MercadoPagoParserError,
    PdfExtractionError,
    build_source_info,
    build_validation_info,
    extract_pdf,
    parse_inter_statement_info,
    parse_inter_card_summaries,
    parse_inter_transactions,
    parse_mercado_pago_card_summaries,
    parse_mercado_pago_statement_info,
    parse_mercado_pago_transactions,
)


def build_argument_parser() -> ArgumentParser:
    """Create and configure the command-line argument parser."""
    parser = ArgumentParser(
        allow_abbrev=False,
        description=(
            "Inspeciona a extração de uma fatura em PDF, ocultando dados "
            "financeiros por padrão."
        ),
    )
    parser.add_argument(
        "pdf_path",
        type=Path,
        help="Caminho da fatura em PDF.",
    )
    parser.add_argument(
        "--page",
        type=int,
        help=(
            "Número da página cujo texto deve ser exibido. "
            "Exige --show-sensitive-data."
        ),
    )
    parser.add_argument(
        "--password-prompt",
        action="store_true",
        help="Solicita de forma oculta a senha de um PDF protegido.",
    )
    parser.add_argument(
        "--show-sensitive-data",
        action="store_true",
        help=(
            "Exibe dados financeiros e texto bruto no terminal. "
            "Use somente em um ambiente privado."
        ),
    )
    return parser


def main(arguments: Sequence[str] | None = None) -> int:
    """Extract the selected PDF and print a human-readable summary."""
    argument_parser = build_argument_parser()
    parsed_arguments = argument_parser.parse_args(arguments)

    if (
        parsed_arguments.page is not None
        and not parsed_arguments.show_sensitive_data
    ):
        argument_parser.error(
            "--page exige --show-sensitive-data porque o texto da página "
            "pode conter informações financeiras"
        )

    password = (
        getpass("Senha do PDF: ")
        if parsed_arguments.password_prompt
        else None
    )

    if parsed_arguments.show_sensitive_data:
        print(
            "ATENÇÃO: dados sensíveis serão exibidos neste terminal. "
            "Evite compartilhar ou salvar esta saída."
        )

    try:
        document = extract_pdf(
            parsed_arguments.pdf_path,
            password=password,
        )
    except PdfExtractionError as error:
        argument_parser.error(str(error))

    source_error = None
    try:
        source = build_source_info(document)
        issuer_summary = source.issuer.value
    except IssuerDetectionError as error:
        source = None
        source_error = str(error)
        issuer_summary = f"não identificado ({error})"

    if source is not None and parsed_arguments.show_sensitive_data:
        print("\nSource estruturado:")
        print(source.model_dump_json(indent=2))
    elif source_error is not None:
        print(f"\nEmissor não reconhecido: {source_error}")

    statement = None
    statement_error = None
    if source is not None and source.issuer is Issuer.INTER:
        try:
            statement = parse_inter_statement_info(document)
        except InterParserError as error:
            statement_error = str(error)
    elif source is not None and source.issuer is Issuer.MERCADO_PAGO:
        try:
            statement = parse_mercado_pago_statement_info(document)
        except MercadoPagoParserError as error:
            statement_error = str(error)

    if parsed_arguments.show_sensitive_data:
        print(f"Arquivo: {document.filename}")
        print(f"SHA-256: {document.file_sha256}")
    else:
        print("Arquivo: [oculto]")

    print(f"Emissor detectado: {issuer_summary}")
    print(f"Tamanho: {document.file_size_bytes} bytes")
    print(f"Páginas: {document.page_count}")

    print("\nResumo das páginas:")
    for page in document.pages:
        print(
            f"- Página {page.number}: "
            f"{len(page.text)} caracteres, {len(page.words)} palavras"
        )

    if statement is not None:
        if parsed_arguments.show_sensitive_data:
            print("\nStatementInfo estruturado:")
            print(statement.model_dump_json(indent=2))
        else:
            print("\nStatementInfo: extraído com sucesso (dados ocultos).")
    elif statement_error is not None:
        print(f"\nResumo da fatura não reconhecido: {statement_error}")

    card_summaries = None
    card_summaries_error = None
    if source is not None and source.issuer is Issuer.INTER:
        try:
            card_summaries = parse_inter_card_summaries(document)
        except InterParserError as error:
            card_summaries_error = str(error)
    elif source is not None and source.issuer is Issuer.MERCADO_PAGO:
        try:
            card_summaries = parse_mercado_pago_card_summaries(document)
        except MercadoPagoParserError as error:
            card_summaries_error = str(error)

    if card_summaries is not None:
        if parsed_arguments.show_sensitive_data:
            print("\nCardSummaries estruturado:")
            print(
                json.dumps(
                    [
                        card.model_dump(mode="json")
                        for card in card_summaries
                    ],
                    indent=2,
                    ensure_ascii=False,
                )
            )
        else:
            print("\nCardSummaries: extraído com sucesso (dados ocultos).")
    elif card_summaries_error is not None:
        print(
            "\nResumo dos cartões não reconhecido: "
            f"{card_summaries_error}"
        )

    transactions = None
    transactions_error = None
    if source is not None and source.issuer is Issuer.INTER:
        try:
            transactions = parse_inter_transactions(document)
        except InterParserError as error:
            transactions_error = str(error)
    elif source is not None and source.issuer is Issuer.MERCADO_PAGO:
        try:
            transactions = parse_mercado_pago_transactions(document)
        except MercadoPagoParserError as error:
            transactions_error = str(error)

    if transactions is not None:
        if parsed_arguments.show_sensitive_data:
            print("\nTransactions estruturado:")
            print(
                json.dumps(
                    [
                        transaction.model_dump(mode="json")
                        for transaction in transactions
                    ],
                    indent=2,
                    ensure_ascii=False,
                )
            )
        else:
            print("\nTransactions: extraído com sucesso (dados ocultos).")
    elif transactions_error is not None:
        print(
            "\nTransações da fatura não reconhecidas: "
            f"{transactions_error}"
        )

    validation = None
    if (
        statement is not None
        and card_summaries is not None
        and transactions is not None
    ):
        validation = build_validation_info(
            statement=statement,
            cards=card_summaries,
            transactions=transactions,
        )

    if validation is not None:
        if parsed_arguments.show_sensitive_data:
            print("\nValidationInfo estruturado:")
            print(validation.model_dump_json(indent=2))
        else:
            print("\nValidationInfo: calculado com sucesso (dados ocultos).")

    if not parsed_arguments.show_sensitive_data:
        print(
            "\nDados financeiros ocultos por padrão. Use "
            "--show-sensitive-data somente em um terminal privado."
        )

    if parsed_arguments.page is None:
        if parsed_arguments.show_sensitive_data:
            print("\nUse --page NUMERO para exibir o texto de uma página.")
        return 0

    if not 1 <= parsed_arguments.page <= document.page_count:
        argument_parser.error(
            f"a página deve estar entre 1 e {document.page_count}"
        )

    selected_page = document.pages[parsed_arguments.page - 1]
    print(f"\nTexto extraído da página {selected_page.number}:")
    print("=" * 60)
    print(selected_page.text)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
