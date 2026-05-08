# Fidelity Checklist

Use this checklist before calling the EPUB finished.

## Required Checks

- Every `pages/page-XXX/page.md` is non-empty and starts with `<!-- source-page: XXX -->`.
- Reading order within each page follows the visual page.
- Prose is reflowed into natural paragraphs rather than PDF line wraps.
- Formulas are LaTeX reconstructed from the page image, not extracted text.
- Review comments `<!-- REVIEW: ... -->` are resolved or intentionally accepted.
- Tables preserve rows, columns, headings, notes, units, and significance marks.
- Figures, captions, footnotes, acknowledgments, references, and appendices are retained.
- Visual figures are cropped page-local images referenced from `page.md`; full-page screenshots are not used as figure substitutes.
- `epub_src/pages/page-XXX.xhtml` exists for each page.
- `epub_unpacked/` exists and mirrors the packaged EPUB contents for debugging.
- EPUB ZIP validation passes.
- XHTML validation passes.

## Acceptance Standard

The EPUB should be more readable on phones than the PDF while preserving all scientific content. For formulas, the page image is the source of truth; do not accept plausible-looking LaTeX that does not match the page.
