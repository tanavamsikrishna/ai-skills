---
name: pdf-paper-to-epub
description: Convert technical, scientific, academic, or research PDF papers into high-fidelity EPUB files with preflight extraction, page tasks, focused visual reconstruction, and EPUB packaging. Use when the ai agent needs to coordinate token-efficient PDF-to-Markdown conversion with formulas as LaTeX math, figures/assets preserved, then package the completed Markdown into EPUB.
---

# PDF Paper to EPUB

## Overview

Use this skill to convert scholarly PDFs into EPUBs through preflight-driven page reconstruction. The helper script splits and renders pages, runs cheap extraction diagnostics when available, creates page tasks, and packages completed Markdown; it does not understand PDF content semantically.

## Workflow

1. Prepare page tasks and cheap preflight outputs:

Resolve the helper script from this skill directory, then run it with `uv`. For example, if this skill is installed at `/path/to/pdf-paper-to-epub`, set:

```bash
HELPER="/path/to/pdf-paper-to-epub/scripts/pdf_paper_to_epub.py"
```

```bash
uv run "$HELPER" prepare input.pdf --workdir build/input
```

This creates one directory per page under `pages/page-XXX/` and, by default, runs non-fatal preflight extraction with `pdftotext`, `pdftohtml`, and `pdfimages` when those tools are installed. Use `--no-preflight` only when the extra extraction is unwanted or unavailable.

Preflight writes:

- `pages/page-XXX/extracted.txt`: page-local text extraction draft.
- `work/preflight/preflight_report.json`: per-page diagnostics and extracted asset lists.
- `work/preflight/pdftohtml/`: HTML and extracted assets from `pdftohtml`.
- `work/preflight/pdfimages/`: image list and extracted embedded image objects.

Rerun preflight after `prepare` if needed:

```bash
uv run "$HELPER" preflight --workdir build/input
```

2. Review preflight and classify pages before spending vision tokens:

- Use `extracted.txt` for ordinary prose when reading order is sound.
- Use clean `pdftohtml` or `pdfimages` assets directly for figures when they preserve the visual content.
- Transcribe image-like text blocks into real Markdown text when that improves reflow and accessibility.
- Use `page.png`, `page.pdf`, or focused crops for formulas, tables, unclear figure boundaries, and pages where extraction is broken.
- Do not inspect or send full page images when extracted text/assets are sufficient.

Read `references/preflight-driven-conversion.md` before converting large papers or papers with many figures.

3. Process pages with lightweight subagents when the user has requested or allowed subagent work:

- Assign each worker a small page range, for example 3-8 pages depending on page complexity.
- Tell each worker they are not alone in the workspace and must edit only their assigned `pages/page-XXX/page.md` files.
- Give each worker the page directory paths and this task: read `task.md`, prefer `extracted.txt` for prose, inspect `page.png` or focused crops only where needed, optionally inspect `page.pdf`, and write faithful Markdown to `page.md`.
- Require formulas to be reconstructed from the page image as Pandoc-compatible LaTeX math, not copied from PDF text extraction.
- Require uncertain formulas/tables to be marked with `<!-- REVIEW: ... -->`.

4. Build the EPUB after all page Markdown files are complete:

```bash
uv run "$HELPER" build --workdir build/input -o output.epub
```

`build` writes separate EPUB source files under `epub_src/` and unpacks the packaged EPUB into `epub_unpacked/` for debugging.
If `--title` is not provided, `build` uses the first Markdown heading from `pages/page-001/page.md` as the EPUB title before falling back to the PDF metadata title from the manifest.

5. Verify:

```bash
uv run "$HELPER" verify --workdir build/input --epub output.epub
```

Repair empty pages, review notes, malformed XHTML, or missing content before calling the EPUB finished.

## Page Task Contract

Each `pages/page-XXX/` directory contains:

- `page.png`: primary visual source for the image-capable agent.
- `page.pdf`: exact one-page PDF source.
- `extracted.txt`: cheap text extraction draft, when preflight ran.
- `page.json`: page metadata and dimensions.
- `task.md`: page-specific conversion instructions.
- `page.md`: the worker-owned Markdown output file.

The worker must:

- Preserve all visible content from that page.
- Merge PDF line wraps into natural Markdown paragraphs.
- Use extraction outputs first when they are faithful enough.
- Use Markdown headings, lists, and tables when appropriate.
- Use Pandoc-compatible LaTeX math for formulas by default: inline `$...$`, display `$$...$$`.
- Do not define custom LaTeX macros.
- If standard LaTeX cannot represent a formula faithfully, add a `<!-- REVIEW: formula ... -->` note explaining the difficulty.
- For visual figures, use clean extracted assets first; otherwise create or place a cropped image in the same page directory and reference it from Markdown, for example `![Figure 1](figure-1.png)`.
- Preserve tables, captions, footnotes, references, and figure information.
- Avoid full-page screenshots in `page.md`.

## Formula Policy

- Formulas must be reconstructed visually from `page.png` or `page.pdf`.
- Use Pandoc-compatible LaTeX math for formulas when the structure is clear.
- Do not use text-preserving TeX generated from extracted PDF text as a substitute for formula reconstruction.
- If a formula cannot be reconstructed confidently, add `<!-- REVIEW: formula ... -->` with the reason.

Read `references/formula-reconstruction.md` before processing pages with significant formulas.

## Debugging Outputs

- `epub_src/pages/page-XXX.xhtml`: generated XHTML for each page before EPUB packaging.
- `epub_src/assets/page-XXX/`: page-local images referenced by Markdown, such as cropped figures.
- `epub_unpacked/`: unpacked final EPUB ZIP structure.
- `work/manifest.json`: page list and build/verify commands.
- `work/preflight/preflight_report.json`: extraction diagnostics and page hints.
- `work/verification_report.json`: latest verification result.

## References

- Read `references/formula-reconstruction.md` when reconstructing equations.
- Read `references/preflight-driven-conversion.md` before using extraction outputs or extracted assets.
- Read `references/fidelity-checklist.md` before final verification.
