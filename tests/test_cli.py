from contextlib import redirect_stderr
from io import StringIO
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock, patch

from fatura_parser.cli import (
    JsonOutputExistsError,
    StatementValidationError,
    build_argument_parser,
    convert_pdf_to_json,
    default_output_path,
    main,
)


class StatementCliTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.directory = Path(self.temporary_directory.name)

    def make_result(
        self,
        *,
        reconciled: bool = True,
        warning_codes: tuple[str, ...] = (),
    ) -> Mock:
        result = Mock()
        result.model_dump_json.return_value = (
            '{"schema_version":"1.0","description":"CAFÉ"}'
        )
        result.validation.reconciled = reconciled
        result.validation.warnings = [
            Mock(code=warning_code)
            for warning_code in warning_codes
        ]
        return result

    def test_builds_the_default_path_inside_the_output_directory(self) -> None:
        self.assertEqual(
            default_output_path(Path("samples/fatura-inter.pdf")),
            Path("output/fatura-inter.json"),
        )

    @patch("fatura_parser.cli.parse_statement")
    @patch("fatura_parser.cli.extract_pdf")
    def test_converts_a_pdf_and_writes_utf8_json(
        self,
        extract_pdf_mock: Mock,
        parse_statement_mock: Mock,
    ) -> None:
        document = object()
        result = self.make_result()
        pdf_path = self.directory / "statement.pdf"
        output_path = self.directory / "nested" / "statement.json"
        extract_pdf_mock.return_value = document
        parse_statement_mock.return_value = result

        written_path = convert_pdf_to_json(
            pdf_path=pdf_path,
            output_path=output_path,
            password="secret",
        )

        self.assertEqual(written_path, output_path)
        self.assertEqual(
            output_path.read_text(encoding="utf-8"),
            '{"schema_version":"1.0","description":"CAFÉ"}\n',
        )
        extract_pdf_mock.assert_called_once_with(
            pdf_path,
            password="secret",
        )
        parse_statement_mock.assert_called_once_with(document)

    @patch("fatura_parser.cli.parse_statement")
    @patch("fatura_parser.cli.extract_pdf")
    def test_refuses_to_overwrite_an_existing_json_by_default(
        self,
        extract_pdf_mock: Mock,
        parse_statement_mock: Mock,
    ) -> None:
        output_path = self.directory / "statement.json"
        output_path.write_text("existing content", encoding="utf-8")

        with self.assertRaises(JsonOutputExistsError):
            convert_pdf_to_json(
                pdf_path=self.directory / "statement.pdf",
                output_path=output_path,
            )

        self.assertEqual(
            output_path.read_text(encoding="utf-8"),
            "existing content",
        )
        extract_pdf_mock.assert_not_called()
        parse_statement_mock.assert_not_called()

    @patch("fatura_parser.cli.parse_statement")
    @patch("fatura_parser.cli.extract_pdf")
    def test_overwrites_an_existing_json_when_explicitly_allowed(
        self,
        extract_pdf_mock: Mock,
        parse_statement_mock: Mock,
    ) -> None:
        output_path = self.directory / "statement.json"
        output_path.write_text("old content", encoding="utf-8")
        extract_pdf_mock.return_value = object()
        parse_statement_mock.return_value = self.make_result()

        convert_pdf_to_json(
            pdf_path=self.directory / "statement.pdf",
            output_path=output_path,
            overwrite=True,
        )

        self.assertIn(
            '"schema_version":"1.0"',
            output_path.read_text(encoding="utf-8"),
        )

    @patch("fatura_parser.cli.parse_statement")
    @patch("fatura_parser.cli.extract_pdf")
    def test_uses_an_atomic_replace_when_overwriting(
        self,
        extract_pdf_mock: Mock,
        parse_statement_mock: Mock,
    ) -> None:
        output_path = self.directory / "statement.json"
        output_path.write_text("old content", encoding="utf-8")
        extract_pdf_mock.return_value = object()
        parse_statement_mock.return_value = self.make_result()

        with patch(
            "fatura_parser.cli.os.replace",
            wraps=os.replace,
        ) as replace_mock:
            convert_pdf_to_json(
                pdf_path=self.directory / "statement.pdf",
                output_path=output_path,
                overwrite=True,
            )

        replace_mock.assert_called_once()
        temporary_path, replaced_path = replace_mock.call_args.args
        self.assertEqual(Path(replaced_path), output_path)
        self.assertFalse(Path(temporary_path).exists())

    @patch("fatura_parser.cli.parse_statement")
    @patch("fatura_parser.cli.extract_pdf")
    def test_preserves_the_old_json_and_cleans_up_after_a_replace_failure(
        self,
        extract_pdf_mock: Mock,
        parse_statement_mock: Mock,
    ) -> None:
        output_path = self.directory / "statement.json"
        output_path.write_text("old content", encoding="utf-8")
        extract_pdf_mock.return_value = object()
        parse_statement_mock.return_value = self.make_result()

        with patch(
            "fatura_parser.cli.os.replace",
            side_effect=OSError("simulated replacement failure"),
        ):
            with self.assertRaises(OSError):
                convert_pdf_to_json(
                    pdf_path=self.directory / "statement.pdf",
                    output_path=output_path,
                    overwrite=True,
                )

        self.assertEqual(
            output_path.read_text(encoding="utf-8"),
            "old content",
        )
        self.assertFalse(
            any(path.suffix == ".tmp" for path in self.directory.iterdir())
        )

    @patch("fatura_parser.cli.parse_statement")
    @patch("fatura_parser.cli.extract_pdf")
    def test_does_not_overwrite_a_file_created_during_processing(
        self,
        extract_pdf_mock: Mock,
        parse_statement_mock: Mock,
    ) -> None:
        output_path = self.directory / "statement.json"
        extract_pdf_mock.return_value = object()
        parse_statement_mock.return_value = self.make_result()

        def simulate_competing_writer(
            temporary_path: Path,
            destination: Path,
        ) -> None:
            del temporary_path
            destination.write_text("competing content", encoding="utf-8")
            raise FileExistsError

        with patch(
            "fatura_parser.cli.os.link",
            side_effect=simulate_competing_writer,
        ):
            with self.assertRaises(JsonOutputExistsError):
                convert_pdf_to_json(
                    pdf_path=self.directory / "statement.pdf",
                    output_path=output_path,
                )

        self.assertEqual(
            output_path.read_text(encoding="utf-8"),
            "competing content",
        )
        self.assertFalse(
            any(path.suffix == ".tmp" for path in self.directory.iterdir())
        )

    @patch("fatura_parser.cli.parse_statement")
    @patch("fatura_parser.cli.extract_pdf")
    def test_refuses_to_export_a_statement_with_warnings_by_default(
        self,
        extract_pdf_mock: Mock,
        parse_statement_mock: Mock,
    ) -> None:
        result = self.make_result(
            warning_codes=("CARD_TOTAL_MISMATCH",),
        )
        output_path = self.directory / "statement.json"
        extract_pdf_mock.return_value = object()
        parse_statement_mock.return_value = result

        with self.assertRaisesRegex(
            StatementValidationError,
            "CARD_TOTAL_MISMATCH",
        ):
            convert_pdf_to_json(
                pdf_path=self.directory / "statement.pdf",
                output_path=output_path,
            )

        self.assertFalse(output_path.exists())
        result.model_dump_json.assert_not_called()

    @patch("fatura_parser.cli.parse_statement")
    @patch("fatura_parser.cli.extract_pdf")
    def test_refuses_to_export_an_unreconciled_statement_by_default(
        self,
        extract_pdf_mock: Mock,
        parse_statement_mock: Mock,
    ) -> None:
        result = self.make_result(reconciled=False)
        output_path = self.directory / "statement.json"
        extract_pdf_mock.return_value = object()
        parse_statement_mock.return_value = result

        with self.assertRaises(StatementValidationError):
            convert_pdf_to_json(
                pdf_path=self.directory / "statement.pdf",
                output_path=output_path,
            )

        self.assertFalse(output_path.exists())

    @patch("fatura_parser.cli.parse_statement")
    @patch("fatura_parser.cli.extract_pdf")
    def test_exports_warnings_only_when_explicitly_allowed(
        self,
        extract_pdf_mock: Mock,
        parse_statement_mock: Mock,
    ) -> None:
        result = self.make_result(
            reconciled=False,
            warning_codes=("TOTAL_MISMATCH",),
        )
        output_path = self.directory / "statement.json"
        extract_pdf_mock.return_value = object()
        parse_statement_mock.return_value = result

        convert_pdf_to_json(
            pdf_path=self.directory / "statement.pdf",
            output_path=output_path,
            allow_warnings=True,
        )

        self.assertTrue(output_path.exists())

    @patch("fatura_parser.cli.convert_pdf_to_json")
    def test_main_reports_the_created_json_path(
        self,
        convert_mock: Mock,
    ) -> None:
        output_path = self.directory / "statement.json"
        convert_mock.return_value = output_path

        with patch("builtins.print") as print_mock:
            exit_code = main(
                [
                    "statement.pdf",
                    "--output",
                    str(output_path),
                ]
            )

        self.assertEqual(exit_code, 0)
        print_mock.assert_called_once_with(
            f"JSON criado em: {output_path.resolve()}"
        )

    @patch("fatura_parser.cli.getpass")
    @patch("fatura_parser.cli.convert_pdf_to_json")
    def test_main_reads_a_pdf_password_from_a_hidden_prompt(
        self,
        convert_mock: Mock,
        getpass_mock: Mock,
    ) -> None:
        output_path = self.directory / "statement.json"
        convert_mock.return_value = output_path
        getpass_mock.return_value = "secret"

        with patch("builtins.print"):
            exit_code = main(
                [
                    "statement.pdf",
                    "--output",
                    str(output_path),
                    "--password-prompt",
                ]
            )

        self.assertEqual(exit_code, 0)
        getpass_mock.assert_called_once_with("Senha do PDF: ")
        convert_mock.assert_called_once_with(
            pdf_path=Path("statement.pdf"),
            output_path=output_path,
            password="secret",
            overwrite=False,
            allow_warnings=False,
        )

    def test_rejects_a_password_written_in_the_command_line(self) -> None:
        argument_parser = build_argument_parser()

        with redirect_stderr(StringIO()):
            with self.assertRaises(SystemExit):
                argument_parser.parse_args(
                    ["statement.pdf", "--password", "secret"]
                )

    @patch("fatura_parser.cli.convert_pdf_to_json")
    def test_main_forwards_explicit_permission_to_export_warnings(
        self,
        convert_mock: Mock,
    ) -> None:
        output_path = self.directory / "statement.json"
        convert_mock.return_value = output_path

        with patch("builtins.print"):
            exit_code = main(
                [
                    "statement.pdf",
                    "--output",
                    str(output_path),
                    "--allow-warnings",
                ]
            )

        self.assertEqual(exit_code, 0)
        convert_mock.assert_called_once_with(
            pdf_path=Path("statement.pdf"),
            output_path=output_path,
            password=None,
            overwrite=False,
            allow_warnings=True,
        )


if __name__ == "__main__":
    unittest.main()
