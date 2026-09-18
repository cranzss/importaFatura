from datetime import date as Date
import unittest

from fatura_parser.value_parsers import (
    ValueParsingError,
    parse_brazilian_date,
    parse_brazilian_textual_date,
    parse_brl_amount_to_cents,
)


class BrlAmountParserTestCase(unittest.TestCase):
    def test_converts_a_formatted_brl_amount_to_cents(self) -> None:
        self.assertEqual(parse_brl_amount_to_cents("R$ 1.234,56"), 123_456)

    def test_accepts_an_amount_without_a_thousands_separator(self) -> None:
        self.assertEqual(parse_brl_amount_to_cents("R$ 19,90"), 1_990)

    def test_converts_a_negative_brl_amount_to_cents(self) -> None:
        self.assertEqual(parse_brl_amount_to_cents("-R$ 75,20"), -7_520)

    def test_rejects_a_non_brazilian_amount_format(self) -> None:
        with self.assertRaises(ValueParsingError):
            parse_brl_amount_to_cents("R$ 1,659.15")

    def test_rejects_an_amount_without_two_decimal_places(self) -> None:
        with self.assertRaises(ValueParsingError):
            parse_brl_amount_to_cents("R$ 19,9")


class BrazilianDateParserTestCase(unittest.TestCase):
    def test_converts_a_brazilian_date(self) -> None:
        self.assertEqual(
            parse_brazilian_date("01/01/2030"),
            Date(2030, 1, 1),
        )

    def test_accepts_surrounding_whitespace(self) -> None:
        self.assertEqual(
            parse_brazilian_date("  01/01/2030  "),
            Date(2030, 1, 1),
        )

    def test_rejects_an_impossible_calendar_date(self) -> None:
        with self.assertRaises(ValueParsingError):
            parse_brazilian_date("31/02/2026")

    def test_rejects_an_iso_date(self) -> None:
        with self.assertRaises(ValueParsingError):
            parse_brazilian_date("2026-07-12")

class BrazilianTextualDateParserTestCase(unittest.TestCase):
    def test_converts_a_brazilian_textual_date(self) -> None:
        self.assertEqual(
            parse_brazilian_textual_date(
                "10 de jan. 2030"
            ),
            Date(2030, 1, 10),
        )

    def test_accepts_case_variations(self) -> None:
        self.assertEqual(
            parse_brazilian_textual_date(
                "10 de JAN. 2030"
            ),
            Date(2030, 1, 10),
        )

    def test_converts_the_may_abbreviation(self) -> None:
        self.assertEqual(
            parse_brazilian_textual_date(
                "11 de fev. 2030"
            ),
            Date(2030, 2, 11),
        )

    def test_rejects_an_impossible_textual_date(self) -> None:
        with self.assertRaises(ValueParsingError):
            parse_brazilian_textual_date(
                "31 de fev. 2030"
            )

    def test_rejects_an_unknown_month(self) -> None:
        with self.assertRaises(ValueParsingError):
            parse_brazilian_textual_date(
                "10 de abc. 2030"
            )


if __name__ == "__main__":
    unittest.main()
