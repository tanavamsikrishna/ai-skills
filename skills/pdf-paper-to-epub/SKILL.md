---
name: pdf-paper-to-epub
description: Convert MinerU parser output for technical, scientific, academic, or research papers into EPUB files. Use when Codex needs to turn MinerU output directories containing *_content_list_v2.json, Markdown, and extracted images into an EPUB while preserving formulas, tables, figures, captions, footnotes, and producing formula audit artifacts without rereading the source PDF.
---

# PDF Paper to EPUB

Convert MinerU output into an EPUB without rereading the PDF. Treat `*_content_list_v2.json` as the primary source because it separates inline formulas, display formulas, tables, figures, and captions.

## Workflow

1. Locate the MinerU output directory. It is usually the `hybrid_auto` directory containing:

- `*_content_list_v2.json`
- `*.md`
- `images/`

2. Inspect the parsed structure before converting:

```bash
uv run /path/to/pdf-paper-to-epub/scripts/mineru_to_epub.py inspect /path/to/hybrid_auto
```

3. Convert to EPUB:

```bash
uv run /path/to/pdf-paper-to-epub/scripts/mineru_to_epub.py convert /path/to/hybrid_auto --output paper.epub
```

The script uses LaTeX as the source math syntax and asks Pandoc to emit EPUB3 MathML because EPUB readers do not reliably render raw LaTeX. Raw LaTeX is preserved in `book.md` and the audit.

This writes a build bundle, by default under `build/<paper-stem>/`, containing:

- `book.md`: Markdown generated from MinerU v2 JSON.
- `styles.css`: EPUB styling passed to Pandoc.
- `assets/`: copied figures and table fallback images referenced by the EPUB.
- `formula_images/`: copied display-equation crops for traceability.
- `audit/formula_audit.json`: formula counts, source locations, image paths, and warnings.
- `audit/formula_review.md`: human-readable list of suspicious formulas.
- `audit/formula_repair_tasks.md`: created when Pandoc cannot parse a formula.
- `audit/formula_repairs.template.json`: repair template created with formula IDs.

If `convert` stops with Pandoc formula failures, repair them as a second pass:

1. Open `audit/formula_repair_tasks.md`.
2. Compare each formula against its copied formula image when available.
3. Write corrected LaTeX into `formula_repairs.json` using the same IDs as the template.
4. Rebuild with repairs:

```bash
uv run /path/to/pdf-paper-to-epub/scripts/mineru_to_epub.py apply-repairs /path/to/hybrid_auto --repairs build/<paper-stem>/audit/formula_repairs.json --output paper.epub
```

4. Verify the final EPUB:

```bash
uv run /path/to/pdf-paper-to-epub/scripts/mineru_to_epub.py verify /path/to/hybrid_auto --epub paper.epub
```

Resolve any high-risk formula warnings before calling the EPUB finished.

## Conversion Rules

- Do not run OCR or parse the source PDF again unless the user explicitly asks.
- Use `*_content_list_v2.json` as canonical. Use MinerU Markdown and `*_content_list.json` only as fallback or diagnostic context.
- Render inline formula fragments as `$...$` and display formulas as `$$...$$`.
- Preserve MinerU LaTeX exactly unless an agent-reviewed repair file supplies a replacement for a formula ID.
- Do not apply automatic formula compatibility rewrites. The script detects Pandoc formula parse failures and emits repair tasks instead.
- Copy display formula image crops into `formula_images/` and include their paths in the audit report.
- Flag risky formulas instead of silently fixing them.
- Prefer MinerU table HTML when present. Copy table images for traceability; use the image as a fallback only when HTML is missing.
- Use extracted figure/chart images for visual content. Do not use full PDF page screenshots.
- Skip repetitive `page_number` and `page_footer` blocks by default. Preserve `page_footnote` and `page_aside_text` near their source position.

## Formula Review

Check `audit/formula_review.md` after conversion. Warnings usually mean the formula needs visual review against the copied crop image or original MinerU output. Common warnings include:

- missing display-equation image crop
- empty math content
- unbalanced braces
- replacement/unknown characters
- digit-separated OCR artifacts such as `5 0 0`
- Pandoc math conversion warnings

When uncertain, prefer adding a review note or using the copied formula crop as a visual reference rather than inventing a formula.
