# Preflight-Driven Conversion

Use preflight outputs to reduce visual-token use while preserving fidelity.

## Sources

- `pages/page-XXX/extracted.txt`: best first source for prose.
- `work/preflight/preflight_report.json`: page hints and extracted asset lists.
- `work/preflight/pdftohtml/`: HTML plus image assets extracted by `pdftohtml`.
- `work/preflight/pdfimages/`: embedded-image list and extracted original image objects.
- `page.png` / `page.pdf`: source of truth for formulas, tables, layout, and visual checks.

## Page Triage

Treat preflight hints as diagnostics, not truth:

- `has_text`: prose may be recoverable from `extracted.txt`.
- `low_text`: page may be mostly visual, scanned, or extraction failed.
- `has_html_images`: check `pdftohtml` assets before manually cropping.
- `has_pdf_images`: check original embedded image objects before manually cropping.
- `formula_candidate`: inspect the visual page or focused crop before writing math.
- `table_candidate`: inspect the visual page or focused crop before writing a table.

## Preferred Workflow

1. Draft prose from `extracted.txt`; merge line wraps into natural paragraphs.
2. Compare headings, captions, equations, tables, and figures against `page.png`.
3. Use extracted figure assets directly when they are complete and include the intended visual content.
4. Transcribe image-like text blocks into Markdown text when they are simple labels, legends, or definitions.
5. Crop from `page.png` only when extracted assets are missing, incomplete, split awkwardly, or lower fidelity than the rendered page.
6. Use full-page visual inspection only for pages where the cheap extraction is insufficient.

## Tool-Specific Notes

`pdftotext` is usually best for prose and references, but it preserves PDF line wrapping and may scramble multi-column layouts, formulas, and tables.

`pdftohtml` is useful for discovering image assets and rough reading order. It often emits hard line breaks, non-breaking spaces, page anchors, and formula fragments, so do not treat the HTML as EPUB-ready.

`pdfimages` extracts embedded raster images at their original quality when the PDF contains image objects. It does not extract vector diagrams or charts drawn from PDF primitives, and captions usually remain separate.

## Formula and Table Rule

Never rely on extracted text alone for formulas or complex tables. Reconstruct formulas visually as Pandoc-compatible LaTeX and mark uncertainty with `<!-- REVIEW: ... -->`.
