"""Render a Word document to page PNGs, for visual inspection of the deliverable.

Word is driven through COM (``pywin32``), which is how the document will look
when the recipient opens it — unlike a Markdown preview or an HTML render.
``pypdfium2`` rasterises the intermediate PDF without needing Ghostscript or
Poppler.

Usage::

    python -m hallmark_repro.render_docx docs/02_课程论文.docx rendered/ --dpi 110
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def docx_to_pdf(docx: Path, pdf: Path, attempts: int = 3) -> None:
    """Convert with Word, retrying around COM busy states.

    ``Dispatch`` reuses a running Word instance, which is what makes the call
    intermittently fail with "call was rejected by callee" when the previous
    invocation has not finished shutting down.  ``DispatchEx`` forces a fresh
    instance, and a short backoff covers the remaining race.
    """
    import time

    import win32com.client

    last_exc: Exception | None = None
    for attempt in range(attempts):
        word = None
        try:
            word = win32com.client.DispatchEx("Word.Application")
            word.Visible = False
            word.DisplayAlerts = 0
            doc = word.Documents.Open(str(docx.resolve()), ReadOnly=True)
            try:
                doc.SaveAs(str(pdf.resolve()), FileFormat=17)   # 17 = wdFormatPDF
            finally:
                doc.Close(False)
            return
        except Exception as exc:                              # noqa: BLE001
            last_exc = exc
            time.sleep(2.0 * (attempt + 1))
        finally:
            if word is not None:
                try:
                    word.Quit()
                except Exception:                             # noqa: BLE001
                    pass
    raise RuntimeError(f"Word failed to convert {docx} after {attempts} attempts: {last_exc}")


def pdf_to_pngs(pdf: Path, out_dir: Path, dpi: int = 110) -> list[Path]:
    import pypdfium2 as pdfium

    out_dir.mkdir(parents=True, exist_ok=True)
    doc = pdfium.PdfDocument(str(pdf))
    scale = dpi / 72.0
    paths: list[Path] = []
    for i in range(len(doc)):
        page = doc[i]
        img = page.render(scale=scale).to_pil()
        p = out_dir / f"page-{i + 1:02d}.png"
        img.save(p)
        paths.append(p)
    return paths


def main() -> None:
    ap = argparse.ArgumentParser(description="Render a .docx to page PNGs")
    ap.add_argument("docx")
    ap.add_argument("out_dir")
    ap.add_argument("--dpi", type=int, default=110)
    args = ap.parse_args()

    docx = Path(args.docx)
    out_dir = Path(args.out_dir)
    pdf = out_dir / (docx.stem + ".pdf")
    out_dir.mkdir(parents=True, exist_ok=True)

    docx_to_pdf(docx, pdf)
    pages = pdf_to_pngs(pdf, out_dir, args.dpi)
    print(f"{docx} -> {len(pages)} pages in {out_dir}")
    for p in pages:
        print(f"  {p}")


if __name__ == "__main__":
    sys.exit(main())
