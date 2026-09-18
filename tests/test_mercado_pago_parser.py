from datetime import date as Date
import unittest

from fatura_parser.enums import TransactionType
from fatura_parser.parsers.mercado_pago import (
    MercadoPagoCardSummaryNotFoundError,
    MercadoPagoParserError,
    MercadoPagoStatementFieldNotFoundError,
    UnexpectedMercadoPagoDocumentError,
    parse_mercado_pago_card_summaries,
    parse_mercado_pago_statement_info,
    parse_mercado_pago_transactions,
)
from fatura_parser.pdf_extractor import ExtractedPage, ExtractedPdf


class MercadoPagoParserTestCase(unittest.TestCase):
    def create_document(self, *page_texts: str) -> ExtractedPdf:
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
            filename="mercado-pago-statement.pdf",
            file_sha256="5" * 64,
            file_size_bytes=100,
            pages=pages,
        )

    def create_statement_document(self) -> ExtractedPdf:
        return self.create_document(
            """Mercado Pago
Total a pagar Vence em Limite total Saque total
R$ 300,00 15/01/2030 R$ 10.000,00 R$ 0,00
""",
            """Informações adicionais
Fechamento da fatura 10/01/2030
O valor mínimo que você deve pagar é de R$ 45,00.
""",
        )

    def test_extracts_statement_info(self) -> None:
        statement = parse_mercado_pago_statement_info(
            self.create_statement_document()
        )

        self.assertEqual(statement.due_date, Date(2030, 1, 15))
        self.assertEqual(statement.closing_date, Date(2030, 1, 10))
        self.assertEqual(statement.currency, "BRL")
        self.assertEqual(statement.declared_total_cents, 30_000)
        self.assertEqual(statement.minimum_payment_cents, 4_500)

    def test_rejects_a_statement_without_the_summary(self) -> None:
        document = self.create_document(
            "Mercado Pago",
            "Fechamento da fatura 10/01/2030",
        )

        with self.assertRaises(MercadoPagoStatementFieldNotFoundError):
            parse_mercado_pago_statement_info(document)

    def test_accepts_a_missing_minimum_payment(self) -> None:
        document = self.create_document(
            """Mercado Pago
Total a pagar Vence em Limite total Saque total
R$ 300,00 15/01/2030 R$ 10.000,00 R$ 0,00
""",
            "Fechamento da fatura 10/01/2030",
        )

        statement = parse_mercado_pago_statement_info(document)

        self.assertIsNone(statement.minimum_payment_cents)

    def test_extracts_multiple_card_summaries(self) -> None:
        document = self.create_document(
            "Mercado Pago",
            """Total R$ 999,99
Cartão Visa [************1111]
10/01 COMPRA EXEMPLO R$ 100,00
Total R$ 100,00
Cartão Mastercard [************2222]
09/01 OUTRA COMPRA R$ 200,00
Total R$ 200,00
""",
        )

        summaries = parse_mercado_pago_card_summaries(document)

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
                ("mercado_pago:1111", "1111", 10_000),
                ("mercado_pago:2222", "2222", 20_000),
            ],
        )

    def test_rejects_a_card_section_without_a_total(self) -> None:
        document = self.create_document(
            "Mercado Pago",
            "Cartão Visa [************1111]",
        )

        with self.assertRaises(MercadoPagoCardSummaryNotFoundError):
            parse_mercado_pago_card_summaries(document)

    def test_extracts_payments_purchases_installments_and_inferred_dates(
        self,
    ) -> None:
        document = self.create_document(
            "Mercado Pago",
            """Detalhes de consumo
Movimentações na fatura
15/12 Pagamento da fatura anterior R$ 500,00
Cartão Visa [************1111]
16/08 LOJA PARCELADA Parcela 02 de 05 R$ 100,00
03/01 COMPRA EXEMPLO R$ 200,00
Total R$ 300,00
""",
            "Fechamento da fatura 10/01/2030",
        )

        transactions = parse_mercado_pago_transactions(document)

        self.assertEqual(len(transactions), 3)

        payment, installment_purchase, regular_purchase = transactions
        self.assertIsNone(payment.card_id)
        self.assertEqual(payment.date, Date(2029, 12, 15))
        self.assertTrue(payment.date_inferred)
        self.assertEqual(payment.amount_cents, -50_000)
        self.assertIs(payment.type, TransactionType.PAYMENT)
        self.assertFalse(payment.included_in_statement_total)

        self.assertEqual(
            installment_purchase.card_id,
            "mercado_pago:1111",
        )
        self.assertEqual(installment_purchase.date, Date(2029, 8, 16))
        self.assertEqual(installment_purchase.description, "LOJA PARCELADA")
        self.assertEqual(installment_purchase.amount_cents, 10_000)
        self.assertIsNotNone(installment_purchase.installment)
        self.assertEqual(installment_purchase.installment.current, 2)
        self.assertEqual(installment_purchase.installment.total, 5)

        self.assertEqual(regular_purchase.date, Date(2030, 1, 3))
        self.assertEqual(regular_purchase.amount_cents, 20_000)
        self.assertIs(regular_purchase.type, TransactionType.PURCHASE)
        self.assertTrue(regular_purchase.included_in_statement_total)

    def test_rejects_a_purchase_outside_a_card_section(self) -> None:
        document = self.create_document(
            "Mercado Pago",
            "10/01 COMPRA SEM CARTAO R$ 10,00",
            "Fechamento da fatura 10/01/2030",
        )

        with self.assertRaisesRegex(
            MercadoPagoParserError,
            "outside a card section",
        ):
            parse_mercado_pago_transactions(document)

    def test_rejects_a_statement_from_another_issuer(self) -> None:
        document = self.create_document("Banco Inter S.A.")

        parser_functions = (
            parse_mercado_pago_statement_info,
            parse_mercado_pago_card_summaries,
            parse_mercado_pago_transactions,
        )
        for parser_function in parser_functions:
            with self.subTest(parser_function=parser_function.__name__):
                with self.assertRaises(UnexpectedMercadoPagoDocumentError):
                    parser_function(document)


if __name__ == "__main__":
    unittest.main()
