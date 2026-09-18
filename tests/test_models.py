from datetime import date
import json
from pathlib import Path
import unittest

from pydantic import ValidationError

from fatura_parser.enums import Issuer, TransactionType
from fatura_parser.models import (
    CardSummary,
    Installment,
    ParserInfo,
    SourceInfo,
    StatementParseResult,
    StatementInfo,
    Transaction,
    ValidationInfo,
    ValidationWarning,
)


class CardSummaryTestCase(unittest.TestCase):
    def test_accepts_a_valid_card_summary(self) -> None:
        card = CardSummary(
            card_id="inter:1234",
            card_last_four="1234",
            declared_total_cents=14340,
        )

        self.assertEqual(
            card.model_dump(),
            {
                "card_id": "inter:1234",
                "card_last_four": "1234",
                "declared_total_cents": 14340,
            },
        )

    def test_accepts_a_negative_declared_total(self) -> None:
        card = CardSummary(
            card_id="inter:1234",
            card_last_four="1234",
            declared_total_cents=-500,
        )

        self.assertEqual(card.declared_total_cents, -500)

    def test_rejects_invalid_last_four(self) -> None:
        for invalid_value in ["123", "12A4", "12345"]:
            with self.subTest(invalid_value=invalid_value):
                with self.assertRaises(ValidationError):
                    CardSummary(
                        card_id="inter:1234",
                        card_last_four=invalid_value,
                        declared_total_cents=14340,
                    )

    def test_rejects_a_card_id_with_different_last_four(self) -> None:
        with self.assertRaises(ValidationError):
            CardSummary(
                card_id="inter:5678",
                card_last_four="1234",
                declared_total_cents=14340,
            )

    def test_rejects_a_malformed_card_id(self) -> None:
        with self.assertRaises(ValidationError):
            CardSummary(
                card_id="inter-1234",
                card_last_four="1234",
                declared_total_cents=14340,
            )

    def test_rejects_a_card_id_with_an_unsupported_issuer(self) -> None:
        with self.assertRaises(ValidationError):
            CardSummary(
                card_id="unsupported_bank:1234",
                card_last_four="1234",
                declared_total_cents=14340,
            )

    def test_rejects_a_total_received_as_text(self) -> None:
        with self.assertRaises(ValidationError):
            CardSummary.model_validate_json(
                """
                {
                    "card_id": "inter:1234",
                    "card_last_four": "1234",
                    "declared_total_cents": "14340"
                }
                """
            )


class SourceInfoTestCase(unittest.TestCase):
    def test_accepts_and_serializes_valid_source_information(self) -> None:
        source = SourceInfo(
            issuer=Issuer.INTER,
            filename="fatura-exemplo.pdf",
            file_sha256="0" * 64,
            page_count=8,
        )

        self.assertEqual(
            source.model_dump(mode="json"),
            {
                "issuer": "inter",
                "filename": "fatura-exemplo.pdf",
                "file_sha256": "0" * 64,
                "page_count": 8,
            },
        )

    def test_rejects_a_filename_containing_a_path(self) -> None:
        invalid_filenames = [
            "samples/private/fatura.pdf",
            r"C:\private\fatura.pdf",
        ]

        for filename in invalid_filenames:
            with self.subTest(filename=filename):
                with self.assertRaises(ValidationError):
                    SourceInfo(
                        issuer=Issuer.INTER,
                        filename=filename,
                        file_sha256="0" * 64,
                        page_count=8,
                    )


    def test_rejects_a_non_pdf_filename(self) -> None:
        with self.assertRaises(ValidationError):
            SourceInfo(
                issuer=Issuer.INTER,
                filename="fatura.txt",
                file_sha256="0" * 64,
                page_count=8,
            )

    def test_rejects_a_pdf_filename_without_a_stem(self) -> None:
        for filename in [".pdf", "   .pdf"]:
            with self.subTest(filename=filename):
                with self.assertRaises(ValidationError):
                    SourceInfo(
                        issuer=Issuer.INTER,
                        filename=filename,
                        file_sha256="0" * 64,
                        page_count=8,
                    )

    def test_rejects_an_invalid_sha256(self) -> None:
        for invalid_hash in ["abc123", "A" * 64, "g" * 64]:
            with self.subTest(invalid_hash=invalid_hash):
                with self.assertRaises(ValidationError):
                    SourceInfo(
                        issuer=Issuer.INTER,
                        filename="fatura.pdf",
                        file_sha256=invalid_hash,
                        page_count=8,
                    )

    def test_rejects_a_document_without_pages(self) -> None:
        with self.assertRaises(ValidationError):
            SourceInfo(
                issuer=Issuer.INTER,
                filename="fatura.pdf",
                file_sha256="0" * 64,
                page_count=0,
            )


class StatementInfoTestCase(unittest.TestCase):
    def test_accepts_and_serializes_valid_statement_information(self) -> None:
        statement = StatementInfo(
            due_date=date(2026, 8, 12),
            closing_date=date(2026, 8, 5),
            currency="BRL",
            declared_total_cents=22340,
            minimum_payment_cents=4468,
        )

        self.assertEqual(
            statement.model_dump(mode="json"),
            {
                "due_date": "2026-08-12",
                "closing_date": "2026-08-05",
                "currency": "BRL",
                "declared_total_cents": 22340,
                "minimum_payment_cents": 4468,
            },
        )

    def test_accepts_a_missing_closing_date_and_minimum_payment(self) -> None:
        statement = StatementInfo(
            due_date=date(2026, 8, 12),
            closing_date=None,
            currency="BRL",
            declared_total_cents=22340,
            minimum_payment_cents=None,
        )

        self.assertIsNone(statement.closing_date)
        self.assertIsNone(statement.minimum_payment_cents)

    def test_accepts_a_credit_balance_with_zero_minimum_payment(self) -> None:
        statement = StatementInfo(
            due_date=date(2026, 8, 12),
            closing_date=date(2026, 8, 5),
            currency="BRL",
            declared_total_cents=-500,
            minimum_payment_cents=0,
        )

        self.assertEqual(statement.declared_total_cents, -500)

    def test_rejects_a_closing_date_after_the_due_date(self) -> None:
        with self.assertRaises(ValidationError):
            StatementInfo(
                due_date=date(2026, 8, 12),
                closing_date=date(2026, 8, 13),
                currency="BRL",
                declared_total_cents=22340,
                minimum_payment_cents=4468,
            )

    def test_rejects_a_minimum_payment_greater_than_the_total(self) -> None:
        with self.assertRaises(ValidationError):
            StatementInfo(
                due_date=date(2026, 8, 12),
                closing_date=date(2026, 8, 5),
                currency="BRL",
                declared_total_cents=22340,
                minimum_payment_cents=22341,
            )

    def test_rejects_a_negative_minimum_payment(self) -> None:
        with self.assertRaises(ValidationError):
            StatementInfo(
                due_date=date(2026, 8, 12),
                closing_date=date(2026, 8, 5),
                currency="BRL",
                declared_total_cents=22340,
                minimum_payment_cents=-1,
            )

    def test_rejects_an_unsupported_currency(self) -> None:
        with self.assertRaises(ValidationError):
            StatementInfo(
                due_date=date(2026, 8, 12),
                closing_date=date(2026, 8, 5),
                currency="USD",
                declared_total_cents=22340,
                minimum_payment_cents=4468,
            )


class ValidationWarningTestCase(unittest.TestCase):
    def test_accepts_and_serializes_a_valid_warning(self) -> None:
        warning = ValidationWarning(
            code="TOTAL_MISMATCH",
            message="The calculated total differs from the declared total.",
            source_page=None,
        )

        self.assertEqual(
            warning.model_dump(),
            {
                "code": "TOTAL_MISMATCH",
                "message": "The calculated total differs from the declared total.",
                "source_page": None,
            },
        )

    def test_rejects_an_invalid_warning_code(self) -> None:
        for code in ["total_mismatch", "TOTAL-MISMATCH", ""]:
            with self.subTest(code=code):
                with self.assertRaises(ValidationError):
                    ValidationWarning(
                        code=code,
                        message="Review required.",
                        source_page=2,
                    )

    def test_rejects_a_blank_warning_message(self) -> None:
        with self.assertRaises(ValidationError):
            ValidationWarning(
                code="TOTAL_MISMATCH",
                message="   ",
                source_page=2,
            )


class ValidationInfoTestCase(unittest.TestCase):
    def make_validation(self, **overrides: object) -> ValidationInfo:
        data: dict[str, object] = {
            "transaction_count": 4,
            "included_transaction_count": 3,
            "computed_total_cents": 22340,
            "declared_total_cents": 22340,
            "difference_cents": 0,
            "reconciled": True,
            "warnings": [],
        }
        data.update(overrides)

        return ValidationInfo.model_validate(data)

    def test_accepts_and_serializes_a_reconciled_validation(self) -> None:
        validation = self.make_validation()

        self.assertEqual(
            validation.model_dump(mode="json"),
            {
                "transaction_count": 4,
                "included_transaction_count": 3,
                "computed_total_cents": 22340,
                "declared_total_cents": 22340,
                "difference_cents": 0,
                "reconciled": True,
                "warnings": [],
            },
        )

    def test_accepts_a_declared_unreconciled_result(self) -> None:
        warning = ValidationWarning(
            code="TOTAL_MISMATCH",
            message="Review required.",
            source_page=None,
        )

        validation = self.make_validation(
            computed_total_cents=22000,
            difference_cents=340,
            reconciled=False,
            warnings=[warning],
        )

        self.assertFalse(validation.reconciled)
        self.assertEqual(validation.difference_cents, 340)

    def test_rejects_an_incorrect_difference(self) -> None:
        with self.assertRaises(ValidationError):
            self.make_validation(difference_cents=1)

    def test_rejects_an_incorrect_reconciled_flag(self) -> None:
        with self.assertRaises(ValidationError):
            self.make_validation(reconciled=False)

    def test_rejects_more_included_than_total_transactions(self) -> None:
        with self.assertRaises(ValidationError):
            self.make_validation(
                transaction_count=3,
                included_transaction_count=4,
            )


class ParserInfoTestCase(unittest.TestCase):
    def test_accepts_and_serializes_a_valid_parser_identity(self) -> None:
        parser = ParserInfo(name=Issuer.INTER, version="0.1.0")

        self.assertEqual(
            parser.model_dump(mode="json"),
            {"name": "inter", "version": "0.1.0"},
        )

    def test_rejects_an_invalid_parser_version(self) -> None:
        for version in ["1", "1.0", "01.0.0", "1.0.0-beta"]:
            with self.subTest(version=version):
                with self.assertRaises(ValidationError):
                    ParserInfo(name=Issuer.INTER, version=version)


class StatementParseResultTestCase(unittest.TestCase):
    def make_cards(self) -> list[CardSummary]:
        return [
            CardSummary(
                card_id="inter:1234",
                card_last_four="1234",
                declared_total_cents=14340,
            ),
            CardSummary(
                card_id="inter:5678",
                card_last_four="5678",
                declared_total_cents=8000,
            ),
        ]

    def make_transactions(self) -> list[Transaction]:
        return [
            Transaction(
                transaction_id="example-transaction-1",
                card_id="inter:1234",
                date=date(2026, 7, 3),
                date_inferred=False,
                description="MERCADO EXEMPLO",
                amount_cents=10000,
                type=TransactionType.PURCHASE,
                included_in_statement_total=True,
                installment=None,
                source_page=3,
            ),
            Transaction(
                transaction_id="example-transaction-2",
                card_id="inter:1234",
                date=date(2026, 7, 4),
                date_inferred=False,
                description="LOJA PARCELADA",
                amount_cents=4340,
                type=TransactionType.PURCHASE,
                included_in_statement_total=True,
                installment=Installment(current=2, total=6),
                source_page=3,
            ),
            Transaction(
                transaction_id="example-transaction-3",
                card_id="inter:5678",
                date=date(2026, 7, 5),
                date_inferred=False,
                description="SERVICO EXEMPLO",
                amount_cents=8000,
                type=TransactionType.PURCHASE,
                included_in_statement_total=True,
                installment=None,
                source_page=4,
            ),
            Transaction(
                transaction_id="example-transaction-4",
                card_id=None,
                date=date(2026, 7, 1),
                date_inferred=False,
                description="PAGAMENTO DA FATURA ANTERIOR",
                amount_cents=-12000,
                type=TransactionType.PAYMENT,
                included_in_statement_total=False,
                installment=None,
                source_page=3,
            ),
        ]

    def make_result(self, **overrides: object) -> StatementParseResult:
        data: dict[str, object] = {
            "schema_version": "1.0",
            "parser": ParserInfo(name=Issuer.INTER, version="0.1.0"),
            "source": SourceInfo(
                issuer=Issuer.INTER,
                filename="fatura-exemplo.pdf",
                file_sha256="0" * 64,
                page_count=5,
            ),
            "statement": StatementInfo(
                due_date=date(2026, 8, 12),
                closing_date=date(2026, 8, 5),
                currency="BRL",
                declared_total_cents=22340,
                minimum_payment_cents=4468,
            ),
            "cards": self.make_cards(),
            "transactions": self.make_transactions(),
            "validation": ValidationInfo(
                transaction_count=4,
                included_transaction_count=3,
                computed_total_cents=22340,
                declared_total_cents=22340,
                difference_cents=0,
                reconciled=True,
                warnings=[],
            ),
        }
        data.update(overrides)

        return StatementParseResult.model_validate(data)

    def test_serializes_exactly_like_the_documented_example(self) -> None:
        result = self.make_result()
        example_path = (
            Path(__file__).resolve().parents[1]
            / "examples"
            / "statement.example.json"
        )
        expected = json.loads(example_path.read_text(encoding="utf-8"))

        self.assertEqual(result.model_dump(mode="json"), expected)

    def test_rejects_a_parser_for_a_different_issuer(self) -> None:
        with self.assertRaises(ValidationError):
            self.make_result(
                parser=ParserInfo(
                    name=Issuer.MERCADO_PAGO,
                    version="0.1.0",
                )
            )

    def test_rejects_an_unsupported_schema_version(self) -> None:
        with self.assertRaises(ValidationError):
            self.make_result(schema_version="2.0")

    def test_rejects_a_card_from_a_different_issuer(self) -> None:
        cards = self.make_cards()
        cards[1] = CardSummary(
            card_id="mercado_pago:5678",
            card_last_four="5678",
            declared_total_cents=8000,
        )

        with self.assertRaises(ValidationError):
            self.make_result(cards=cards)

    def test_rejects_duplicate_card_ids(self) -> None:
        card = self.make_cards()[0]

        with self.assertRaises(ValidationError):
            self.make_result(cards=[card, card])

    def test_rejects_a_transaction_for_an_unknown_card(self) -> None:
        transactions = self.make_transactions()
        transaction_data = transactions[0].model_dump()
        transaction_data["card_id"] = "inter:9999"
        transactions[0] = Transaction.model_validate(transaction_data)

        with self.assertRaises(ValidationError):
            self.make_result(transactions=transactions)

    def test_rejects_duplicate_transaction_ids(self) -> None:
        transactions = self.make_transactions()
        transaction_data = transactions[1].model_dump()
        transaction_data["transaction_id"] = transactions[0].transaction_id
        transactions[1] = Transaction.model_validate(transaction_data)

        with self.assertRaises(ValidationError):
            self.make_result(transactions=transactions)

    def test_rejects_validation_counts_that_do_not_match_the_lists(self) -> None:
        validation = ValidationInfo(
            transaction_count=5,
            included_transaction_count=3,
            computed_total_cents=22340,
            declared_total_cents=22340,
            difference_cents=0,
            reconciled=True,
            warnings=[],
        )

        with self.assertRaises(ValidationError):
            self.make_result(validation=validation)

    def test_rejects_a_validation_total_not_computed_from_transactions(self) -> None:
        validation = ValidationInfo(
            transaction_count=4,
            included_transaction_count=3,
            computed_total_cents=22000,
            declared_total_cents=22340,
            difference_cents=340,
            reconciled=False,
            warnings=[],
        )

        with self.assertRaises(ValidationError):
            self.make_result(validation=validation)

    def test_rejects_a_validation_declared_total_not_found_in_statement(self) -> None:
        validation = ValidationInfo(
            transaction_count=4,
            included_transaction_count=3,
            computed_total_cents=22340,
            declared_total_cents=22000,
            difference_cents=-340,
            reconciled=False,
            warnings=[],
        )

        with self.assertRaises(ValidationError):
            self.make_result(validation=validation)

    def test_rejects_card_subtotals_that_do_not_match_the_statement(self) -> None:
        cards = self.make_cards()
        cards[1] = CardSummary(
            card_id="inter:5678",
            card_last_four="5678",
            declared_total_cents=7999,
        )

        with self.assertRaises(ValidationError):
            self.make_result(cards=cards)

    def test_accepts_an_unreconciled_result_with_an_accurate_validation(self) -> None:
        transactions = self.make_transactions()
        transactions.pop(1)
        warning = ValidationWarning(
            code="TOTAL_MISMATCH",
            message="Review required.",
            source_page=None,
        )
        validation = ValidationInfo(
            transaction_count=3,
            included_transaction_count=2,
            computed_total_cents=18000,
            declared_total_cents=22340,
            difference_cents=4340,
            reconciled=False,
            warnings=[warning],
        )

        result = self.make_result(
            transactions=transactions,
            validation=validation,
        )

        self.assertFalse(result.validation.reconciled)

    def test_rejects_a_transaction_page_outside_the_source_pdf(self) -> None:
        transactions = self.make_transactions()
        transaction_data = transactions[0].model_dump()
        transaction_data["source_page"] = 6
        transactions[0] = Transaction.model_validate(transaction_data)

        with self.assertRaises(ValidationError):
            self.make_result(transactions=transactions)

    def test_rejects_a_warning_page_outside_the_source_pdf(self) -> None:
        warning = ValidationWarning(
            code="UNPARSED_TRANSACTION_LINE",
            message="Review page 6.",
            source_page=6,
        )
        validation = ValidationInfo(
            transaction_count=4,
            included_transaction_count=3,
            computed_total_cents=22340,
            declared_total_cents=22340,
            difference_cents=0,
            reconciled=True,
            warnings=[warning],
        )

        with self.assertRaises(ValidationError):
            self.make_result(validation=validation)


class TransactionTestCase(unittest.TestCase):
    def make_transaction(self, **overrides: object) -> Transaction:
        data: dict[str, object] = {
            "transaction_id": "example-transaction-1",
            "card_id": "inter:1234",
            "date": date(2026, 7, 3),
            "date_inferred": False,
            "description": "MERCADO EXEMPLO",
            "amount_cents": 10000,
            "type": TransactionType.PURCHASE,
            "included_in_statement_total": True,
            "installment": None,
            "source_page": 3,
        }
        data.update(overrides)

        return Transaction.model_validate(data)

    def test_accepts_and_serializes_a_valid_purchase(self) -> None:
        transaction = self.make_transaction(
            installment=Installment(current=2, total=6),
        )

        self.assertEqual(
            transaction.model_dump(mode="json"),
            {
                "transaction_id": "example-transaction-1",
                "card_id": "inter:1234",
                "date": "2026-07-03",
                "date_inferred": False,
                "description": "MERCADO EXEMPLO",
                "amount_cents": 10000,
                "type": "purchase",
                "included_in_statement_total": True,
                "installment": {"current": 2, "total": 6},
                "source_page": 3,
            },
        )

    def test_accepts_a_payment_outside_the_current_total(self) -> None:
        transaction = self.make_transaction(
            card_id=None,
            amount_cents=-12000,
            type=TransactionType.PAYMENT,
            included_in_statement_total=False,
        )

        self.assertIsNone(transaction.card_id)
        self.assertEqual(transaction.amount_cents, -12000)
        self.assertFalse(transaction.included_in_statement_total)

    def test_rejects_a_cardless_transaction_included_in_the_total(self) -> None:
        with self.assertRaisesRegex(
            ValidationError,
            "cardless transaction cannot be included in statement total",
        ):
            self.make_transaction(card_id=None)

    def test_requires_the_nullable_card_id_field(self) -> None:
        transaction_data = self.make_transaction().model_dump()
        transaction_data.pop("card_id")

        with self.assertRaises(ValidationError):
            Transaction.model_validate(transaction_data)

    def test_rejects_incorrect_signs_for_known_types(self) -> None:
        invalid_cases = [
            (TransactionType.PAYMENT, 100),
            (TransactionType.REFUND, 100),
            (TransactionType.PURCHASE, -100),
            (TransactionType.FEE, -100),
            (TransactionType.INTEREST, -100),
            (TransactionType.TAX, -100),
            (TransactionType.CASH_ADVANCE, -100),
        ]

        for transaction_type, amount_cents in invalid_cases:
            with self.subTest(
                transaction_type=transaction_type,
                amount_cents=amount_cents,
            ):
                with self.assertRaises(ValidationError):
                    self.make_transaction(
                        type=transaction_type,
                        amount_cents=amount_cents,
                    )

    def test_rejects_a_zero_amount(self) -> None:
        with self.assertRaises(ValidationError):
            self.make_transaction(amount_cents=0)

    def test_rejects_installments_on_a_non_purchase(self) -> None:
        with self.assertRaises(ValidationError):
            self.make_transaction(
                amount_cents=-100,
                type=TransactionType.REFUND,
                installment=Installment(current=2, total=6),
            )

    def test_rejects_blank_required_text(self) -> None:
        for field_name in ["transaction_id", "description"]:
            with self.subTest(field_name=field_name):
                with self.assertRaises(ValidationError):
                    self.make_transaction(**{field_name: "   "})


class InstallmentTestCase(unittest.TestCase):
    def test_accepts_a_valid_installment(self) -> None:
        installment = Installment(current=2, total=6)

        self.assertEqual(
            installment.model_dump(),
            {"current": 2, "total": 6},
        )

    def test_rejects_zero_as_an_installment_number(self) -> None:
        with self.assertRaises(ValidationError):
            Installment(current=0, total=6)

    def test_rejects_current_greater_than_total(self) -> None:
        with self.assertRaises(ValidationError):
            Installment(current=7, total=6)

    def test_rejects_unknown_fields(self) -> None:
        with self.assertRaises(ValidationError):
            Installment(current=2, total=6, bank_code="unexpected")

    def test_rejects_numbers_received_as_text(self) -> None:
        with self.assertRaises(ValidationError):
            Installment.model_validate_json('{"current": "2", "total": 6}')


if __name__ == "__main__":
    unittest.main()
