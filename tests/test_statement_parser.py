import json
import unittest

from fatura_parser import (
    Issuer,
    StatementParserNotImplementedError,
    TransactionType,
    parse_statement,
)
from fatura_parser.pdf_extractor import ExtractedPage, ExtractedPdf


class StatementParserTestCase(unittest.TestCase):
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
            filename="inter-statement.pdf",
            file_sha256="4" * 64,
            file_size_bytes=100,
            pages=pages,
        )

    def create_inter_document(self) -> ExtractedPdf:
        first_page_text = """Banco Inter S.A.
Limite de crédito total
Total da sua fatura
R$ 10.000,00
R$ 30,00
Data de Vencimento
Este é o valor que você precisa pagar nesse mês 01/01/2030
"""
        transactions_page_text = """CARTÃO 0000****1111
10 de jan. 2030 COMPRA EXEMPLO A - R$ 10,00
11 de jan. 2030 COMPRA EXEMPLO B - R$ 20,00
Total CARTÃO 0000****1111 R$ 30,00
"""
        return self.create_document(
            first_page_text,
            transactions_page_text,
        )

    def test_builds_the_complete_inter_statement_result(self) -> None:
        result = parse_statement(self.create_inter_document())

        self.assertEqual(result.schema_version, "1.0")
        self.assertIs(result.parser.name, Issuer.INTER)
        self.assertEqual(result.parser.version, "0.1.0")
        self.assertIs(result.source.issuer, Issuer.INTER)
        self.assertEqual(result.statement.declared_total_cents, 3_000)
        self.assertEqual(len(result.cards), 1)
        self.assertEqual(result.cards[0].card_id, "inter:1111")
        self.assertEqual(len(result.transactions), 2)
        self.assertIs(
            result.transactions[0].type,
            TransactionType.PURCHASE,
        )
        self.assertTrue(result.validation.reconciled)
        self.assertEqual(result.validation.computed_total_cents, 3_000)

        json_data = json.loads(result.model_dump_json())
        self.assertEqual(json_data["source"]["issuer"], "inter")
        self.assertEqual(json_data["cards"][0]["card_last_four"], "1111")
        self.assertEqual(len(json_data["transactions"]), 2)

    def test_rejects_an_issuer_whose_parser_is_not_implemented(self) -> None:
        document = self.create_document(
            "Pague pelo app Mercado Pago",
        )

        with self.assertRaisesRegex(
            StatementParserNotImplementedError,
            "mercado_pago",
        ):
            parse_statement(document)


if __name__ == "__main__":
    unittest.main()
