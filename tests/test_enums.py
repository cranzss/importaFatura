import unittest

from fatura_parser.enums import Issuer, TransactionType


class IssuerTestCase(unittest.TestCase):
    def test_contains_the_supported_issuers(self) -> None:
        self.assertEqual(
            [issuer.value for issuer in Issuer],
            ["inter", "mercado_pago"],
        )

    def test_rejects_an_unsupported_issuer(self) -> None:
        with self.assertRaises(ValueError):
            Issuer("unsupported_bank")


class TransactionTypeTestCase(unittest.TestCase):
    def test_contains_the_types_defined_by_the_json_contract(self) -> None:
        self.assertEqual(
            [transaction_type.value for transaction_type in TransactionType],
            [
                "purchase",
                "payment",
                "refund",
                "fee",
                "interest",
                "tax",
                "cash_advance",
                "other",
            ],
        )

    def test_rejects_an_unknown_transaction_type(self) -> None:
        with self.assertRaises(ValueError):
            TransactionType("subscription")


if __name__ == "__main__":
    unittest.main()
