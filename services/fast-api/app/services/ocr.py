"""OCR / text extraction service (Step 4).

Strategy
--------
- Images (PNG/JPEG) → Tesseract via pytesseract
- PDFs → extract embedded text with PyMuPDF first; if a page looks empty
  (scanned/image-only), rasterize that page and OCR with Tesseract

Called from ``POST /documents/{id}/extract`` (Step 5).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from io import BytesIO

import fitz  # PyMuPDF
import pytesseract
from fastapi import HTTPException, status
from PIL import Image

from app.config import Settings, get_settings

IMAGE_TYPES = {"image/png", "image/jpeg"}
PDF_TYPE = "application/pdf"


@dataclass
class OcrPageResult:
    page_number: int
    text: str
    method: str  # "pdf-text" | "tesseract"


@dataclass
class OcrResult:
    text: str
    page_count: int
    engine: str
    content_type: str
    language: str
    pages: list[OcrPageResult] = field(default_factory=list)

    @property
    def char_count(self) -> int:
        return len(self.text)


class OcrService:
    """Extract plain text from PDF / PNG / JPEG bytes."""

    def __init__(self, settings: Settings) -> None:
        self._language = settings.ocr_language
        self._min_chars = settings.ocr_pdf_min_chars_per_page
        if settings.tesseract_cmd:
            pytesseract.pytesseract.tesseract_cmd = settings.tesseract_cmd

    def extract(self, content: bytes, content_type: str) -> OcrResult:
        if content_type == PDF_TYPE:
            return self._extract_pdf(content)
        if content_type in IMAGE_TYPES:
            return self._extract_image(content, content_type)
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"OCR does not support content type '{content_type}'.",
        )

    def _run_tesseract(self, image: Image.Image) -> str:
        """Run pytesseract, translating a missing binary into a clear 503."""
        try:
            return pytesseract.image_to_string(image, lang=self._language).strip()
        except pytesseract.TesseractNotFoundError as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=(
                    "Tesseract binary not found. Install it "
                    "(`brew install tesseract`) or set TESSERACT_CMD."
                ),
            ) from exc

    def _extract_image(self, content: bytes, content_type: str) -> OcrResult:
        try:
            image = Image.open(BytesIO(content))
            text = self._run_tesseract(image)
        except HTTPException:
            raise
        except Exception as exc:  # noqa: BLE001 — surface as 422 for bad image bytes
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=f"Failed to OCR image: {exc}",
            ) from exc

        page = OcrPageResult(page_number=1, text=text, method="tesseract")
        return OcrResult(
            text=text,
            page_count=1,
            engine="tesseract",
            content_type=content_type,
            language=self._language,
            pages=[page],
        )

    def _extract_pdf(self, content: bytes) -> OcrResult:
        try:
            doc = fitz.open(stream=content, filetype="pdf")
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=f"Failed to open PDF: {exc}",
            ) from exc

        pages: list[OcrPageResult] = []
        methods_used: set[str] = set()

        try:
            for index, page in enumerate(doc, start=1):
                embedded = page.get_text("text").strip()
                if len(embedded) >= self._min_chars:
                    pages.append(
                        OcrPageResult(page_number=index, text=embedded, method="pdf-text")
                    )
                    methods_used.add("pdf-text")
                    continue

                # Sparse/empty page — likely a scan; OCR the rendered page
                ocr_text = self._ocr_pdf_page(page)
                # Prefer whichever yielded more usable text
                chosen = ocr_text if len(ocr_text) > len(embedded) else embedded
                method = "tesseract" if len(ocr_text) > len(embedded) else "pdf-text"
                pages.append(OcrPageResult(page_number=index, text=chosen, method=method))
                methods_used.add(method)
        finally:
            doc.close()

        combined = "\n\n".join(p.text for p in pages if p.text).strip()
        if methods_used == {"pdf-text"}:
            engine = "pdf-text"
        elif methods_used == {"tesseract"}:
            engine = "tesseract"
        else:
            engine = "pdf-text+tesseract"

        return OcrResult(
            text=combined,
            page_count=len(pages),
            engine=engine,
            content_type=PDF_TYPE,
            language=self._language,
            pages=pages,
        )

    def _ocr_pdf_page(self, page: fitz.Page) -> str:
        """Rasterize a PDF page and run Tesseract."""
        try:
            # 2x zoom improves OCR on typical 72 dpi PDF pages
            pix = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
            image = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
            return self._run_tesseract(image)
        except HTTPException:
            raise
        except Exception as exc:  # noqa: BLE001 — surface as 422, e.g. bad OCR language pack
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=f"Failed to OCR PDF page {page.number + 1}: {exc}",
            ) from exc


@lru_cache
def get_ocr_service() -> OcrService:
    return OcrService(get_settings())
