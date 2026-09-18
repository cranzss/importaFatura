from datetime import date as Date
import unittest

from fatura_parser import build_validation_info
from fatura_parser.enums import TransactionType
from fatura_parser.models import CardSummary, StatementInfo, Transaction


class BuildValidationInfoTestCase(unittest.TestCase):
    def make_statement(self) -> StatementInfo:
        return StatementInfo(
            due_date=Date(2026, 7, 12),
            currency="BRL",
            declared_total_cents=3_000,
        )

    def make_cards(self) -> list[CardSummary]:
        return [
            CardSummary(
                card_id="inter:1111",
                card_last_four="1111",
                declared_total_cents=1_000,
            ),
            CardSummary(
                card_id="inter:2222",
                card_last_four="2222",
                declared_total_cents=2_000,
            ),
        ]

    def make_transaction(
        self,
        *,
        transaction_id: str,
        card_id: str | None,
        amount_cents: int,
        transaction_type: TransactionType = TransactionType.PURCHASE,
        included_in_statement_total: bool = True,
    ) -> Transaction:
        return Transaction(
            transaction_id=transaction_id,
            card_id=card_id,
            date=Date(2026, 6, 14),
            date_inferred=False,
            description="MOVIMENTACAO DE TESTE",
            amount_cents=amount_cents,
            type=transaction_type,
            included_in_statement_total=included_in_statement_total,
            source_page=2,
        )

    def make_reconciled_transactions(self) -> list[Transaction]:
        return [
            self.make_transaction(
                transaction_id="transaction-1",
                card_id="inter:1111",
                amount_cents=1_000,
            ),
            self.make_transaction(
                transaction_id="transaction-2",
                card_id="inter:2222",
                amount_cents=2_000,
            ),
        ]

    def test_builds_a_reconciled_validation_without_warnings(self) -> None:
        validation = build_validation_info(
            statement=self.make_statement(),
            cards=self.make_cards(),
            transactions=self.make_reconciled_transactions(),
        )

        self.assertEqual(validation.transaction_count, 2)
        self.assertEqual(validation.included_transaction_count, 2)
        self.assertEqual(validation.computed_total_cents, 3_000)
        self.assertEqual(validation.difference_cents, 0)
        self.assertTrue(validation.reconciled)
        self.assertEqual(validation.warnings, [])

    def test_excludes_a_payment_from_counts_and_totals(self) -> None:
        transactions = self.make_reconciled_transactions()
        transactions.append(
            self.make_transaction(
                transaction_id="payment-1",
                card_id=None,
                amount_cents=-5_000,
                transaction_type=TransactionType.PAYMENT,
                included_in_statement_total=False,
            )
        )

        validation = build_validation_info(
            statement=self.make_statement(),
            cards=self.make_cards(),
            transactions=transactions,
        )

        self.assertEqual(validation.transaction_count, 3)
        self.assertEqual(validation.included_transaction_count, 2)
        self.assertEqual(validation.computed_total_cents, 3_000)
        self.assertTrue(validation.reconciled)

    def test_warns_when_the_statement_total_does_not_reconcile(self) -> None:
        transactions = self.make_reconciled_transactions()[:1]

        validation = build_validation_info(
            statement=self.make_statement(),
            cards=self.make_cards(),
            transactions=transactions,
        )

        self.assertFalse(validation.reconciled)
        self.assertEqual(validation.difference_cents, 2_000)
        self.assertIn(
            "TOTAL_MISMATCH",
            [warning.code for warning in validation.warnings],
        )

    def test_warns_about_each_card_even_when_the_general_total_matches(self) -> None:
        transactions = [
            self.make_transaction(
                transaction_id="transaction-1",
                card_id="inter:1111",
                amount_cents=1_500,
            ),
            self.make_transaction(
                transaction_id="transaction-2",
                card_id="inter:2222",
                amount_cents=1_500,
            ),
        ]

        validation = build_validation_info(
            statement=self.make_statement(),
            cards=self.make_cards(),
            transactions=transactions,
        )

        card_warnings = [
            warning
            for warning in validation.warnings
            if warning.code == "CARD_TOTAL_MISMATCH"
        ]
        self.assertTrue(validation.reconciled)
        self.assertEqual(len(card_warnings), 2)
        self.assertIn("inter:1111", card_warnings[0].message)
        self.assertIn("inter:2222", card_warnings[1].message)


if __name__ == "__main__":
    unittest.main()
