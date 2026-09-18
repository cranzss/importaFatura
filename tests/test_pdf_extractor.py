from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from reportlab.lib.pagesizes import A4
from reportlab.lib.pdfencrypt import StandardEncryption
from reportlab.pdfgen.canvas import Canvas

from fatura_parser.pdf_extractor import (
    InvalidPdfError,
    PdfFileNotFoundError,
    PdfPasswordError,
    PdfTextNotFoundError,
    PdfTooLargeError,
    PdfTooManyPagesError,
    calculate_file_sha256,
    extract_pdf,
)


class PdfExtractorTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.directory = Path(self.temporary_directory.name)

    def create_pdf(
        self,
        filename: str,
        pages: list[str],
        *,
        password: str | None = None,
    ) -> Path:
        pdf_path = self.directory / filename
        encryption = StandardEncryption(password) if password is not None else None
        canvas = Canvas(str(pdf_path), pagesize=A4, encrypt=encryption)

        for text in pages:
            if text:
                canvas.drawString(72, 770, text)
            canvas.showPage()

        canvas.save()
        return pdf_path

    def test_calculates_sha256_from_binary_content(self) -> None:
        file_path = self.directory / "content.bin"
        content = b"conteudo binario de teste"
        file_path.write_bytes(content)

        self.assertEqual(
            calculate_file_sha256(file_path),
            sha256(content).hexdigest(),
        )

    def test_extracts_text_words_and_metadata_from_every_page(self) -> None:
        pdf_path = self.create_pdf(
            "sample.pdf",
            ["PAGINA UM", "PAGINA DOIS"],
        )

        document = extract_pdf(pdf_path)

        self.assertEqual(document.filename, "sample.pdf")
        self.assertEqual(document.page_count, 2)
        self.assertEqual(document.file_sha256, calculate_file_sha256(pdf_path))
        self.assertEqual(len(document.pages), 2)
        self.assertEqual(document.pages[0].number, 1)
        self.assertIn("PAGINA UM", document.pages[0].text)
        self.assertIn("PAGINA DOIS", document.pages[1].text)
        self.assertIn("PAGINA UM", document.full_text)
        self.assertGreater(len(document.pages[0].words), 0)
        self.assertGreaterEqual(document.pages[0].words[0].x0, 0)

    def test_rejects_a_missing_file(self) -> None:
        with self.assertRaises(PdfFileNotFoundError):
            extract_pdf(self.directory / "missing.pdf")

    def test_rejects_a_non_pdf_extension(self) -> None:
        text_path = self.directory / "statement.txt"
        text_path.write_text("not a PDF", encoding="utf-8")

        with self.assertRaises(InvalidPdfError):
            extract_pdf(text_path)

    def test_rejects_non_pdf_content_with_a_pdf_extension(self) -> None:
        fake_pdf = self.directory / "fake.pdf"
        fake_pdf.write_bytes(b"this is not a PDF")

        with self.assertRaises(InvalidPdfError):
            extract_pdf(fake_pdf)

    def test_rejects_a_pdf_larger_than_the_configured_limit(self) -> None:
        pdf_path = self.create_pdf("large.pdf", ["TESTE"])

        with self.assertRaises(PdfTooLargeError):
            extract_pdf(pdf_path, max_file_size_bytes=10)

    def test_rejects_a_pdf_with_more_pages_than_the_limit(self) -> None:
        pdf_path = self.create_pdf(
            "too-many-pages.pdf",
            ["PAGINA UM", "PAGINA DOIS", "PAGINA TRES"],
        )

        with self.assertRaises(PdfTooManyPagesError):
            extract_pdf(pdf_path, max_page_count=2)

    def test_accepts_a_pdf_at_the_exact_page_limit(self) -> None:
        pdf_path = self.create_pdf(
            "page-limit.pdf",
            ["PAGINA UM", "PAGINA DOIS"],
        )

        document = extract_pdf(pdf_path, max_page_count=2)

        self.assertEqual(document.page_count, 2)

    def test_rejects_a_non_positive_page_limit(self) -> None:
        pdf_path = self.create_pdf("invalid-page-limit.pdf", ["TESTE"])

        with self.assertRaisesRegex(
            ValueError,
            "max_page_count must be positive",
        ):
            extract_pdf(pdf_path, max_page_count=0)

    def test_rejects_a_pdf_without_extractable_text(self) -> None:
        pdf_path = self.create_pdf("blank.pdf", [""])

        with self.assertRaises(PdfTextNotFoundError):
            extract_pdf(pdf_path)

    def test_requires_the_correct_password_for_an_encrypted_pdf(self) -> None:
        pdf_path = self.create_pdf(
            "encrypted.pdf",
            ["CONTEUDO PROTEGIDO"],
            password="secret",
        )

        with self.assertRaises(PdfPasswordError):
            extract_pdf(pdf_path)

        with self.assertRaises(PdfPasswordError):
            extract_pdf(pdf_path, password="wrong")

        document = extract_pdf(pdf_path, password="secret")
        self.assertIn("CONTEUDO PROTEGIDO", document.full_text)


if __name__ == "__main__":
    unittest.main()
