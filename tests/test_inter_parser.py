from datetime import date as Date
import unittest

from fatura_parser.enums import TransactionType
from fatura_parser.parsers.inter import (
    InterCardSummaryNotFoundError,
    InterParserError,
    InterStatementFieldNotFoundError,
    UnexpectedInterDocumentError,
    parse_inter_card_summaries,
    parse_inter_statement_info,
    parse_inter_transactions,
)
from fatura_parser.pdf_extractor import ExtractedPage, ExtractedPdf


class InterStatementInfoParserTestCase(unittest.TestCase):
    def create_document(self, first_page_text: str) -> ExtractedPdf:
        return ExtractedPdf(
            filename="inter-statement.pdf",
            file_sha256="0" * 64,
            file_size_bytes=100,
            pages=(
                ExtractedPage(
                    number=1,
                    width=595.0,
                    height=842.0,
                    text=first_page_text,
                    words=(),
                ),
            ),
        )

    def valid_first_page_text(self) -> str:
        return """Resumo da fatura
Limite de crédito total
Total da sua fatura
R$ 10.000,00
R$ 123,45
Data de Vencimento
Este é o valor que você precisa pagar nesse mês 01/01/2030
Pagamento mínimo: R$ 20,00
Faça o pagamento pela conta do Inter
"""

    def test_extracts_statement_info_without_confusing_limit_and_total(self) -> None:
        document = self.create_document(self.valid_first_page_text())

        statement = parse_inter_statement_info(document)

        self.assertEqual(statement.declared_total_cents, 12_345)
        self.assertEqual(statement.due_date, Date(2030, 1, 1))
        self.assertEqual(statement.minimum_payment_cents, 2_000)
        self.assertEqual(statement.currency, "BRL")
        self.assertIsNone(statement.closing_date)

    def test_accepts_a_missing_minimum_payment(self) -> None:
        page_text = self.valid_first_page_text().replace(
            "Pagamento mínimo: R$ 20,00\n",
            "",
        )
        document = self.create_document(page_text)

        statement = parse_inter_statement_info(document)

        self.assertIsNone(statement.minimum_payment_cents)

    def test_rejects_a_page_without_the_statement_total(self) -> None:
        page_text = self.valid_first_page_text().replace(
            "Total da sua fatura\n",
            "",
        )
        document = self.create_document(page_text)

        with self.assertRaises(InterStatementFieldNotFoundError):
            parse_inter_statement_info(document)

    def test_rejects_a_statement_from_another_issuer(self) -> None:
        document = self.create_document("Pague pelo app Mercado Pago")

        with self.assertRaises(UnexpectedInterDocumentError):
            parse_inter_statement_info(document)


class InterCardSummariesParserTestCase(unittest.TestCase):
    def create_document(self, *card_pages: str) -> ExtractedPdf:
        """Create an in-memory Inter document with card summary pages."""
        page_texts = (
            "Banco Inter S.A.",
            *card_pages,
        )
        pages = tuple(
            ExtractedPage(
                number=page_number,
                width=595.0,
                height=842.0,
                text=page_text,
                words=(),
            )
            for page_number, page_text in enumerate(page_texts, start=1)
        )

        return ExtractedPdf(
            filename="inter-statement.pdf",
            file_sha256="2" * 64,
            file_size_bytes=100,
            pages=pages,
        )

    def test_extracts_card_summaries_from_multiple_pages(self) -> None:
        document = self.create_document(
            "\n".join(
                (
                    "Despesas da fatura",
                    "Total CARTÃO 0000****1111 R$ 100,00",
                    "Total CARTÃO 0000****2222 R$ 200,00",
                )
            ),
            "Total CARTÃO 0000****3333 R$ 300,00",
        )

        summaries = parse_inter_card_summaries(document)

        self.assertEqual(
            [
                (
                    summary.card_id,
                    summary.card_last_four,
                    summary.declared_total_cents,
                )
                for summary in summaries
            ],
            [
                ("inter:1111", "1111", 10_000),
                ("inter:2222", "2222", 20_000),
                ("inter:3333", "3333", 30_000),
            ],
        )

    def test_does_not_confuse_a_card_header_with_its_total(self) -> None:
        document = self.create_document(
            "\n".join(
                (
                    "CARTÃO 0000****1111",
                    "Total CARTÃO 0000****1111 R$ 100,00",
                )
            )
        )

        summaries = parse_inter_card_summaries(document)

        self.assertEqual(len(summaries), 1)
        self.assertEqual(summaries[0].card_id, "inter:1111")

    def test_rejects_a_document_without_card_totals(self) -> None:
        document = self.create_document(
            "CARTÃO 0000****1111",
        )

        with self.assertRaises(InterCardSummaryNotFoundError):
            parse_inter_card_summaries(document)

    def test_rejects_a_statement_from_another_issuer(self) -> None:
        mercado_pago_page = ExtractedPage(
            number=1,
            width=595.0,
            height=842.0,
            text="Pague pelo app Mercado Pago",
            words=(),
        )
        document = ExtractedPdf(
            filename="mercado-pago-statement.pdf",
            file_sha256="3" * 64,
            file_size_bytes=100,
            pages=(mercado_pago_page,),
        )

        with self.assertRaises(UnexpectedInterDocumentError):
            parse_inter_card_summaries(document)


class InterTransactionsParserTestCase(unittest.TestCase):
    def create_document(self, *transaction_pages: str) -> ExtractedPdf:
        """Create an in-memory Inter document without reading a real PDF."""
        page_texts = (
            "Banco Inter S.A.",
            *transaction_pages,
        )
        pages = tuple(
            ExtractedPage(
                number=page_number,
                width=595.0,
                height=842.0,
                text=page_text,
                words=(),
            )
            for page_number, page_text in enumerate(page_texts, start=1)
        )

        return ExtractedPdf(
            filename="inter-statement.pdf",
            file_sha256="1" * 64,
            file_size_bytes=100,
            pages=pages,
        )

    def card_section(self, *transaction_lines: str) -> str:
        """Wrap transaction lines in the same card section used by Inter."""
        lines = (
            "CARTÃO 0000****1111",
            *transaction_lines,
            "Total CARTÃO 0000****1111 R$ 999,99",
        )
        return "\n".join(lines)

    def test_extracts_a_regular_purchase(self) -> None:
        document = self.create_document(
            self.card_section(
                "10 de jan. 2030 COMPRA EXEMPLO - R$ 10,00",
            )
        )

        transactions = parse_inter_transactions(document)

        self.assertEqual(len(transactions), 1)
        transaction = transactions[0]
        self.assertEqual(transaction.card_id, "inter:1111")
        self.assertEqual(transaction.date, Date(2030, 1, 10))
        self.assertFalse(transaction.date_inferred)
        self.assertEqual(transaction.description, "COMPRA EXEMPLO")
        self.assertEqual(transaction.amount_cents, 1_000)
        self.assertIs(transaction.type, TransactionType.PURCHASE)
        self.assertTrue(transaction.included_in_statement_total)
        self.assertIsNone(transaction.installment)
        self.assertEqual(transaction.source_page, 2)

    def test_extracts_installment_information_from_a_purchase(self) -> None:
        document = self.create_document(
            self.card_section(
                "11 de jan. 2030 LOJA PARCELADA (Parcela 02 de 05) - R$ 20,00",
            )
        )

        transaction = parse_inter_transactions(document)[0]

        self.assertIsNotNone(transaction.installment)
        self.assertEqual(transaction.installment.current, 2)
        self.assertEqual(transaction.installment.total, 5)
        self.assertIs(transaction.type, TransactionType.PURCHASE)

    def test_payment_is_negative_and_excluded_from_statement_total(self) -> None:
        document = self.create_document(
            self.card_section(
                "12 de jan. 2030 PAGAMENTO ON LINE - + R$ 30,00",
            )
        )

        transaction = parse_inter_transactions(document)[0]

        self.assertEqual(transaction.amount_cents, -3_000)
        self.assertIs(transaction.type, TransactionType.PAYMENT)
        self.assertFalse(transaction.included_in_statement_total)

    def test_refund_is_negative_but_included_in_statement_total(self) -> None:
        document = self.create_document(
            self.card_section(
                "13 de jan. 2030 ESTORNO LOJA EXEMPLO - + R$ 5,00",
            )
        )

        transaction = parse_inter_transactions(document)[0]

        self.assertEqual(transaction.amount_cents, -500)
        self.assertIs(transaction.type, TransactionType.REFUND)
        self.assertTrue(transaction.included_in_statement_total)

    def test_classifies_inter_specific_transaction_descriptions(self) -> None:
        document = self.create_document(
            self.card_section(
                "14 de jan. 2030 IOF - R$ 1,00",
                "15 de jan. 2030 JUROS PIX CREDITO - R$ 2,00",
                "16 de jan. 2030 ANUIDADE - R$ 3,00",
                "17 de jan. 2030 PIX CRED A VISTA - R$ 4,00",
            )
        )

        transactions = parse_inter_transactions(document)

        self.assertEqual(
            [transaction.type for transaction in transactions],
            [
                TransactionType.TAX,
                TransactionType.INTEREST,
                TransactionType.FEE,
                TransactionType.CASH_ADVANCE,
            ],
        )

    def test_keeps_the_current_card_when_its_section_continues_next_page(self) -> None:
        document = self.create_document(
            "\n".join(
                (
                    "CARTÃO 0000****1111",
                    "18 de jan. 2030 COMPRA PAGINA DOIS - R$ 10,00",
                )
            ),
            "\n".join(
                (
                    "19 de jan. 2030 COMPRA PAGINA TRES - R$ 20,00",
                    "Total CARTÃO 0000****1111 R$ 30,00",
                )
            ),
        )

        transactions = parse_inter_transactions(document)

        self.assertEqual(len(transactions), 2)
        self.assertEqual(transactions[0].card_id, "inter:1111")
        self.assertEqual(transactions[1].card_id, "inter:1111")
        self.assertEqual(transactions[0].source_page, 2)
        self.assertEqual(transactions[1].source_page, 3)

    def test_creates_the_same_id_when_the_source_location_is_unchanged(self) -> None:
        document = self.create_document(
            self.card_section(
                "10 de jan. 2030 COMPRA EXEMPLO - R$ 10,00",
            )
        )

        first_result = parse_inter_transactions(document)
        second_result = parse_inter_transactions(document)

        self.assertEqual(
            first_result[0].transaction_id,
            second_result[0].transaction_id,
        )
        self.assertRegex(
            first_result[0].transaction_id,
            r"^txn_[0-9a-f]{24}$",
        )

    def test_rejects_a_transaction_outside_a_card_section(self) -> None:
        document = self.create_document(
            "10 de jan. 2030 COMPRA EXEMPLO - R$ 10,00",
        )

        with self.assertRaisesRegex(
            InterParserError,
            "transaction found outside a card section",
        ):
            parse_inter_transactions(document)

    def test_rejects_a_statement_from_another_issuer(self) -> None:
        document = self.create_document()
        mercado_pago_page = ExtractedPage(
            number=1,
            width=595.0,
            height=842.0,
            text="Pague pelo app Mercado Pago",
            words=(),
        )
        other_issuer_document = ExtractedPdf(
            filename=document.filename,
            file_sha256=document.file_sha256,
            file_size_bytes=document.file_size_bytes,
            pages=(mercado_pago_page,),
        )

        with self.assertRaises(UnexpectedInterDocumentError):
            parse_inter_transactions(other_issuer_document)


if __name__ == "__main__":
    unittest.main()
