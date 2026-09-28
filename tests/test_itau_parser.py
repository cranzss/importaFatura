"""Tests for the Itaú statement parser."""

from datetime import date
import unittest

from fatura_parser.enums import TransactionType
from fatura_parser.parsers.itau import (
    ItauParserError,
    UnexpectedItauDocumentError,
    parse_itau_card_summaries,
    parse_itau_statement_info,
    parse_itau_transactions,
)
from fatura_parser.pdf_extractor import ExtractedPage, ExtractedPdf, ExtractedWord


def _words_for_rows(
    rows: list[tuple[float, str]],
    *,
    x_start: float,
) -> list[ExtractedWord]:
    """Create positioned words resembling one column extracted from a PDF."""
    words: list[ExtractedWord] = []
    for top, text in rows:
        current_x = x_start
        for token in text.split():
            width = max(len(token) * 3.5, 8.0)
            words.append(
                ExtractedWord(
                    text=token,
                    x0=current_x,
                    x1=current_x + width,
                    top=top,
                    bottom=top + 8.0,
                )
            )
            current_x += width + 3.0

    return words


def make_itau_document(
    *,
    issuer_text: str = "Banco Itaú S.A.",
    domestic_total: str = "110,00",
) -> ExtractedPdf:
    """Build a synthetic Itaú statement without storing personal data."""
    first_page_text = "\n".join(
        (
            issuer_text,
            "Total da fatura anterior 100,00",
            "Pagamentos efetuados -30,00",
            "Lançamentos atuais 130,00",
            "Vencimento: 08/09/2030 = Total desta fatura 200,00",
            "Emissão: 01/09/2030",
            "Cartão 4705.XXXX.XXXX.1111",
            "Pagamento mínimo:",
            "R$ 20,00",
        )
    )
    page_two_left = [
        (100.0, "Pagamentos efetuados"),
        (112.0, "01/08 PAGAMENTO -30,00"),
        (124.0, "Total dos pagamentos -30,00"),
        (150.0, "Lançamentos: compras e saques"),
        (162.0, "data estabelecimento valor"),
        (174.0, "02/08 MERCADO 60,00"),
        (186.0, "ALIMENTACAO"),
        (198.0, "03/08 LOJAPARCELADA02/05 20,00"),
        (210.0, "VESTUARIO SAO PAULO"),
        (220.0, f"Lançamentos no cartão {domestic_total}"),
    ]
    page_two_right = [
        (100.0, "Lançamentos: compras e saques"),
        (112.0, "04/08 POSTO 20,00"),
        (124.0, "continua..."),
    ]
    page_two_words = tuple(
        _words_for_rows(page_two_left, x_start=125.0)
        + _words_for_rows(page_two_right, x_start=355.0)
    )
    page_two_text = "\n".join(
        line for _, line in page_two_left + page_two_right
    )

    page_three_left = [
        (70.0, "Lançamentos: compras e saques"),
        (82.0, "05/08 CAFE 10,00"),
        (94.0, f"Lançamentos no cartão {domestic_total}"),
    ]
    page_three_right = [
        (70.0, "Lançamentos internacionais"),
        (82.0, "06/08SITE EXTERIOR 15,00"),
        (94.0, "USD 3,00 cambio 5,00"),
        (106.0, "Total transações inter. em R$ 15,00"),
        (118.0, "Repasse de IOF em R$ 5,00"),
        (130.0, "Total lançamentos inter. em R$ 20,00"),
        (142.0, "Total dos lançamentos atuais 130,00"),
        (154.0, "Compras parceladas - próximas faturas"),
        (166.0, "07/08 COMPRA FUTURA 999,00"),
    ]
    page_three_words = tuple(
        _words_for_rows(page_three_left, x_start=125.0)
        + _words_for_rows(page_three_right, x_start=355.0)
    )
    page_three_text = "\n".join(
        line for _, line in page_three_left + page_three_right
    )

    return ExtractedPdf(
        filename="fatura-itau.pdf",
        file_sha256="a" * 64,
        file_size_bytes=4_096,
        pages=(
            ExtractedPage(
                number=1,
                width=595.0,
                height=842.0,
                text=first_page_text,
                words=(),
            ),
            ExtractedPage(
                number=2,
                width=595.0,
                height=842.0,
                text=page_two_text,
                words=page_two_words,
            ),
            ExtractedPage(
                number=3,
                width=595.0,
                height=842.0,
                text=page_three_text,
                words=page_three_words,
            ),
        ),
    )


class ItauParserTestCase(unittest.TestCase):
    def test_extracts_statement_info(self) -> None:
        statement = parse_itau_statement_info(make_itau_document())

        self.assertEqual(statement.due_date, date(2030, 9, 8))
        self.assertEqual(statement.closing_date, date(2030, 9, 1))
        self.assertEqual(statement.declared_total_cents, 20_000)
        self.assertEqual(statement.minimum_payment_cents, 2_000)

    def test_extracts_the_current_total_for_the_card(self) -> None:
        cards = parse_itau_card_summaries(make_itau_document())

        self.assertEqual(len(cards), 1)
        self.assertEqual(cards[0].card_id, "itau:1111")
        self.assertEqual(cards[0].declared_total_cents, 13_000)

    def test_extracts_and_reconciles_both_transaction_columns(self) -> None:
        transactions = parse_itau_transactions(make_itau_document())

        self.assertEqual(len(transactions), 8)
        self.assertEqual(
            sum(transaction.amount_cents for transaction in transactions),
            20_000,
        )
        self.assertEqual(
            sum(
                transaction.amount_cents
                for transaction in transactions
                if transaction.card_id == "itau:1111"
            ),
            13_000,
        )
        self.assertFalse(
            any(
                "FUTURA" in transaction.description
                for transaction in transactions
            )
        )

    def test_keeps_payments_and_previous_balance_at_statement_level(self) -> None:
        transactions = parse_itau_transactions(make_itau_document())
        cardless = [
            transaction
            for transaction in transactions
            if transaction.card_id is None
        ]

        self.assertEqual(len(cardless), 2)
        self.assertEqual(
            {transaction.type for transaction in cardless},
            {TransactionType.OTHER, TransactionType.PAYMENT},
        )
        self.assertTrue(
            all(
                transaction.included_in_statement_total
                for transaction in cardless
            )
        )

    def test_extracts_installment_information(self) -> None:
        transactions = parse_itau_transactions(make_itau_document())
        installment_transaction = next(
            transaction
            for transaction in transactions
            if transaction.installment is not None
        )

        self.assertEqual(
            installment_transaction.description,
            "LOJAPARCELADA VESTUARIO SAO PAULO",
        )
        self.assertEqual(installment_transaction.installment.current, 2)
        self.assertEqual(installment_transaction.installment.total, 5)

    def test_rejects_a_subtotal_that_does_not_reconcile(self) -> None:
        with self.assertRaisesRegex(
            ItauParserError,
            "domestic transactions total does not reconcile",
        ):
            parse_itau_transactions(
                make_itau_document(domestic_total="109,99")
            )

    def test_rejects_a_statement_from_another_issuer(self) -> None:
        with self.assertRaises(UnexpectedItauDocumentError):
            parse_itau_statement_info(
                make_itau_document(issuer_text="Banco Inter S.A.")
            )


if __name__ == "__main__":
    unittest.main()
