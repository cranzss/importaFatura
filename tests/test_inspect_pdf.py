from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from examples import inspect_pdf
from fatura_parser import Issuer


class InspectPdfTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.document = SimpleNamespace(
            filename="fatura-secreta.pdf",
            file_size_bytes=1_234,
            file_sha256="hash-secreto",
            page_count=1,
            pages=[
                SimpleNamespace(
                    number=1,
                    text="LOJA SIGILOSA R$ 9.999,99",
                    words=["LOJA", "SIGILOSA", "R$", "9.999,99"],
                )
            ],
        )
        self.source = Mock(issuer=Issuer.INTER)
        self.source.model_dump_json.return_value = '{"filename":"secreto"}'

        self.statement = Mock()
        self.statement.model_dump_json.return_value = (
            '{"declared_total_cents":999999}'
        )

        self.card = Mock()
        self.card.model_dump.return_value = {
            "card_last_four": "1111",
            "declared_total_cents": 999_999,
        }

        self.transaction = Mock()
        self.transaction.model_dump.return_value = {
            "description": "LOJA SIGILOSA",
            "amount_cents": 999_999,
        }

        self.validation = Mock()
        self.validation.model_dump_json.return_value = (
            '{"computed_total_cents":999999}'
        )

        patchers = [
            patch.object(
                inspect_pdf,
                "extract_pdf",
                return_value=self.document,
            ),
            patch.object(
                inspect_pdf,
                "build_source_info",
                return_value=self.source,
            ),
            patch.object(
                inspect_pdf,
                "parse_inter_statement_info",
                return_value=self.statement,
            ),
            patch.object(
                inspect_pdf,
                "parse_inter_card_summaries",
                return_value=[self.card],
            ),
            patch.object(
                inspect_pdf,
                "parse_inter_transactions",
                return_value=[self.transaction],
            ),
            patch.object(
                inspect_pdf,
                "build_validation_info",
                return_value=self.validation,
            ),
        ]
        self.mocks = [patcher.start() for patcher in patchers]
        for patcher in patchers:
            self.addCleanup(patcher.stop)

    def test_hides_sensitive_statement_data_by_default(self) -> None:
        output = StringIO()

        with redirect_stdout(output):
            exit_code = inspect_pdf.main(["statement.pdf"])

        printed_text = output.getvalue()
        self.assertEqual(exit_code, 0)
        self.assertIn("Arquivo: [oculto]", printed_text)
        self.assertIn("dados ocultos", printed_text)
        self.assertIn("--show-sensitive-data", printed_text)
        self.assertNotIn("fatura-secreta.pdf", printed_text)
        self.assertNotIn("hash-secreto", printed_text)
        self.assertNotIn("1111", printed_text)
        self.assertNotIn("LOJA SIGILOSA", printed_text)
        self.assertNotIn("999999", printed_text)
        self.source.model_dump_json.assert_not_called()
        self.statement.model_dump_json.assert_not_called()
        self.card.model_dump.assert_not_called()
        self.transaction.model_dump.assert_not_called()
        self.validation.model_dump_json.assert_not_called()

    def test_displays_sensitive_data_only_after_explicit_opt_in(self) -> None:
        output = StringIO()

        with redirect_stdout(output):
            exit_code = inspect_pdf.main(
                [
                    "statement.pdf",
                    "--show-sensitive-data",
                    "--page",
                    "1",
                ]
            )

        printed_text = output.getvalue()
        self.assertEqual(exit_code, 0)
        self.assertIn("ATENÇÃO", printed_text)
        self.assertIn("fatura-secreta.pdf", printed_text)
        self.assertIn("hash-secreto", printed_text)
        self.assertIn("1111", printed_text)
        self.assertIn("LOJA SIGILOSA", printed_text)
        self.assertIn("999999", printed_text)

    def test_page_output_requires_sensitive_data_opt_in(self) -> None:
        error_output = StringIO()

        with redirect_stderr(error_output):
            with self.assertRaises(SystemExit) as raised_error:
                inspect_pdf.main(["statement.pdf", "--page", "1"])

        self.assertEqual(raised_error.exception.code, 2)
        self.assertIn("--page exige --show-sensitive-data", error_output.getvalue())
        self.mocks[0].assert_not_called()

    def test_passes_the_pdf_path_as_a_path_object(self) -> None:
        with redirect_stdout(StringIO()):
            inspect_pdf.main(["statement.pdf"])

        self.mocks[0].assert_called_once_with(
            Path("statement.pdf"),
            password=None,
        )


if __name__ == "__main__":
    unittest.main()
