import unittest

from fatura_parser.enums import Issuer
from fatura_parser.issuer_detector import (
    AmbiguousIssuerError,
    UnsupportedIssuerError,
    build_source_info,
    detect_issuer,
)
from fatura_parser.pdf_extractor import ExtractedPage, ExtractedPdf


class IssuerDetectorTestCase(unittest.TestCase):
    def create_document(
        self,
        first_page_text: str,
        *,
        filename: str = "statement.pdf",
        additional_page_texts: tuple[str, ...] = (),
    ) -> ExtractedPdf:
        page_texts = (first_page_text, *additional_page_texts)
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
            filename=filename,
            file_sha256="0" * 64,
            file_size_bytes=100,
            pages=pages,
        )

    def test_detects_inter_despite_case_line_breaks_and_extra_spaces(self) -> None:
        document = self.create_document("Pague pela CONTA\n  DO   INTER")

        self.assertIs(detect_issuer(document), Issuer.INTER)

    def test_detects_mercado_pago(self) -> None:
        document = self.create_document("Pague pelo app Mercado Pago")

        self.assertIs(detect_issuer(document), Issuer.MERCADO_PAGO)

    def test_does_not_use_the_filename_as_detection_evidence(self) -> None:
        document = self.create_document(
            "Instituição desconhecida",
            filename="inter.pdf",
        )

        with self.assertRaises(UnsupportedIssuerError):
            detect_issuer(document)

    def test_ignores_a_merchant_name_found_after_the_first_page(self) -> None:
        document = self.create_document(
            "Fatura de instituição desconhecida",
            additional_page_texts=("Compra em Mercado Pago",),
        )

        with self.assertRaises(UnsupportedIssuerError):
            detect_issuer(document)

    def test_rejects_a_document_without_a_supported_signature(self) -> None:
        document = self.create_document("Fatura de outro banco")

        with self.assertRaises(UnsupportedIssuerError):
            detect_issuer(document)

    def test_rejects_an_ambiguous_first_page(self) -> None:
        document = self.create_document(
            "Conta do Inter e aplicativo Mercado Pago"
        )

        with self.assertRaises(AmbiguousIssuerError):
            detect_issuer(document)

    def test_builds_validated_source_info_from_the_extracted_pdf(self) -> None:
        document = self.create_document("Pague pelo app Mercado Pago")

        source = build_source_info(document)

        self.assertIs(source.issuer, Issuer.MERCADO_PAGO)
        self.assertEqual(source.filename, document.filename)
        self.assertEqual(source.file_sha256, document.file_sha256)
        self.assertEqual(source.page_count, document.page_count)


if __name__ == "__main__":
    unittest.main()
