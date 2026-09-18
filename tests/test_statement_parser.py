import json
import unittest

from fatura_parser import (
    Issuer,
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

    def create_mercado_pago_document(self) -> ExtractedPdf:
        first_page_text = """Mercado Pago
Total a pagar Vence em Limite total Saque total
R$ 300,00 15/01/2030 R$ 10.000,00 R$ 0,00
"""
        transactions_page_text = """Detalhes de consumo
10/01 Pagamento da fatura anterior R$ 500,00
Cartão Visa [************1111]
08/01 COMPRA EXEMPLO A R$ 100,00
09/01 COMPRA EXEMPLO B Parcela 02 de 05 R$ 200,00
Total R$ 300,00
"""
        information_page_text = """Informações adicionais
Fechamento da fatura 10/01/2030
O valor mínimo que você deve pagar é de R$ 45,00.
"""
        return self.create_document(
            first_page_text,
            transactions_page_text,
            information_page_text,
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

    def test_builds_the_complete_mercado_pago_statement_result(self) -> None:
        result = parse_statement(self.create_mercado_pago_document())

        self.assertIs(result.parser.name, Issuer.MERCADO_PAGO)
        self.assertEqual(result.parser.version, "0.1.0")
        self.assertEqual(result.statement.declared_total_cents, 30_000)
        self.assertEqual(result.cards[0].card_id, "mercado_pago:1111")
        self.assertEqual(len(result.transactions), 3)
        self.assertIsNone(result.transactions[0].card_id)
        self.assertIs(result.transactions[0].type, TransactionType.PAYMENT)
        self.assertTrue(result.validation.reconciled)

        json_data = json.loads(result.model_dump_json())
        self.assertEqual(json_data["source"]["issuer"], "mercado_pago")
        self.assertIsNone(json_data["transactions"][0]["card_id"])


if __name__ == "__main__":
    unittest.main()
