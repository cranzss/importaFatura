"""Tests for the secure local user command."""

from contextlib import redirect_stderr
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from fatura_parser.auth.cli import build_argument_parser, main


class UserCliTests(unittest.TestCase):
    """Verify that secrets never become command-line arguments."""

    def test_does_not_accept_a_password_argument(self) -> None:
        argument_parser = build_argument_parser()

        with redirect_stderr(StringIO()):
            with self.assertRaises(SystemExit):
                argument_parser.parse_args(
                    ["chris@example.com", "--password", "secret"]
                )

    @patch("fatura_parser.auth.cli.create_local_user")
    @patch("fatura_parser.auth.cli.getpass")
    def test_reads_and_confirms_the_password_with_hidden_prompts(
        self,
        getpass_mock,
        create_local_user_mock,
    ) -> None:
        create_local_user_mock.return_value = "chris@example.com"
        getpass_mock.side_effect = [
            "uma frase senha longa",
            "uma frase senha longa",
        ]

        with patch("builtins.print") as print_mock:
            exit_code = main(["chris@example.com"])

        self.assertEqual(exit_code, 0)
        self.assertEqual(getpass_mock.call_count, 2)
        create_local_user_mock.assert_called_once_with(
            "chris@example.com",
            "uma frase senha longa",
            database_path=Path("data") / "fatura_parser.db",
        )
        print_mock.assert_called_once_with(
            "Usuário criado: chris@example.com"
        )

    @patch("fatura_parser.auth.cli.getpass")
    def test_rejects_different_password_confirmations(
        self,
        getpass_mock,
    ) -> None:
        getpass_mock.side_effect = [
            "uma frase senha longa",
            "outra frase senha longa",
        ]

        with redirect_stderr(StringIO()):
            with self.assertRaises(SystemExit):
                main(["chris@example.com"])

    def test_creates_a_real_user_after_the_schema_exists(self) -> None:
        from alembic import command
        from alembic.config import Config
        from sqlalchemy.engine import URL

        with TemporaryDirectory() as temporary_directory:
            database_path = Path(temporary_directory) / "test.db"
            project_root = Path(__file__).resolve().parents[1]
            config = Config(project_root / "alembic.ini")
            database_url = URL.create(
                drivername="sqlite+pysqlite",
                database=str(database_path),
            ).render_as_string(hide_password=False)
            config.set_main_option(
                "sqlalchemy.url",
                database_url.replace("%", "%%"),
            )
            command.upgrade(config, "head")

            with patch(
                "fatura_parser.auth.cli.getpass",
                side_effect=[
                    "uma frase senha longa",
                    "uma frase senha longa",
                ],
            ):
                with patch("builtins.print"):
                    exit_code = main(
                        [
                            "chris@example.com",
                            "--database",
                            str(database_path),
                        ]
                    )

            self.assertEqual(exit_code, 0)


if __name__ == "__main__":
    unittest.main()
