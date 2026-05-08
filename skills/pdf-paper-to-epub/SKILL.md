---
name: pdf-paper-to-epub
description: Convert technical, scientific, academic, or research PDF papers into high-fidelity EPUB files by splitting the PDF into page tasks for image-capable agents. Use when the ai agent needs to coordinate page-by-page Markdown reconstruction with formulas as LaTeX math, then package the completed page Markdown files into EPUB.
---

# PDF Paper to EPUB

## Overview

Use this skill to convert scholarly PDFs into EPUBs through page-by-page agent reconstruction. The helper script only splits and renders pages, creates page tasks, and packages completed Markdown; it does not read or understand PDF content.

## Workflow

1. Prepare page tasks:

Resolve the helper script from this skill directory, then run it with `uv`. For example, if this skill is installed at `/path/to/pdf-paper-to-epub`, set:

```bash
HELPER="/path/to/pdf-paper-to-epub/scripts/pdf_paper_to_epub.py"
```

```bash
uv run "$HELPER" prepare input.pdf --workdir build/input
```

This creates one directory per page under `pages/page-XXX/`.

2. Process pages with lightweight subagents when the user has requested or allowed subagent work:

- Assign each worker a small page range, for example 3-8 pages depending on page complexity.
- Tell each worker they are not alone in the workspace and must edit only their assigned `pages/page-XXX/page.md` files.
- Give each worker the page directory paths and this task: read `task.md`, inspect `page.png` visually, optionally inspect `page.pdf`, and write faithful Markdown to `page.md`.
- Require formulas to be reconstructed from the page image as Pandoc-compatible LaTeX math, not copied from PDF text extraction.
- Require uncertain formulas/tables to be marked with `<!-- REVIEW: ... -->`.

3. Build the EPUB after all page Markdown files are complete:

```bash
uv run "$HELPER" build --workdir build/input -o output.epub
```

`build` writes separate EPUB source files under `epub_src/` and unpacks the packaged EPUB into `epub_unpacked/` for debugging.
If `--title` is not provided, `build` uses the first Markdown heading from `pages/page-001/page.md` as the EPUB title before falling back to the PDF metadata title from the manifest.

4. Verify:

```bash
uv run "$HELPER" verify --workdir build/input --epub output.epub
```

Repair empty pages, review notes, malformed XHTML, or missing content before calling the EPUB finished.

## Page Task Contract

Each `pages/page-XXX/` directory contains:

- `page.png`: primary visual source for the image-capable agent.
- `page.pdf`: exact one-page PDF source.
- `page.json`: page metadata and dimensions.
- `task.md`: page-specific conversion instructions.
- `page.md`: the worker-owned Markdown output file.

The worker must:

- Preserve all visible content from that page.
- Merge PDF line wraps into natural Markdown paragraphs.
- Use Markdown headings, lists, and tables when appropriate.
- Use Pandoc-compatible LaTeX math for formulas by default: inline `$...$`, display `$$...$$`.
- Do not define custom LaTeX macros.
- If standard LaTeX cannot represent a formula faithfully, add a `<!-- REVIEW: formula ... -->` note explaining the difficulty.
- For visual figures, create or place a cropped image in the same page directory and reference it from Markdown, for example `![Figure 1](figure-1.png)`.
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
- `work/verification_report.json`: latest verification result.

## References

- Read `references/formula-reconstruction.md` when reconstructing equations.
- Read `references/fidelity-checklist.md` before final verification.
