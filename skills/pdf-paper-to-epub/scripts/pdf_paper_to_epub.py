#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "pymupdf>=1.24",
#   "ebooklib>=0.18",
#   "lxml>=5",
# ]
# ///
"""Page-task PDF-to-EPUB helper.

This script deliberately does not try to understand PDF content. It only splits
and renders pages, creates page-level tasks for image-capable agents, and
packages completed Markdown into EPUB.
"""

from __future__ import annotations

import argparse
import html
import json
import re
import shlex
import shutil
import subprocess
import uuid
import zipfile
from pathlib import Path
from typing import Any
from urllib.parse import unquote

import fitz
from ebooklib import epub
from lxml import etree

XHTML_NS = "http://www.w3.org/1999/xhtml"
PANDOC_MARKDOWN_FORMAT = "markdown+raw_html+pipe_tables+footnotes+tex_math_dollars"


def fail(message: str) -> None:
    raise SystemExit(f"error: {message}")


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def safe_stem(path: Path) -> str:
    stem = re.sub(r"[^A-Za-z0-9._-]+", "-", path.stem).strip("-")
    return stem or "paper"


def command_for(subcommand: str, workdir: Path) -> str:
    script_path = shlex.quote(str(Path(__file__).resolve()))
    workdir_arg = shlex.quote(str(workdir))
    return f"uv run {script_path} {subcommand} --workdir {workdir_arg}"


def write_json(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def render_page(page: fitz.Page, output: Path, dpi: int) -> None:
    scale = dpi / 72.0
    pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False)
    pix.save(str(output))


def save_single_page_pdf(doc: fitz.Document, page_index: int, output: Path) -> None:
    single = fitz.open()
    single.insert_pdf(doc, from_page=page_index, to_page=page_index)
    single.save(output)
    single.close()


def task_prompt(title: str, page_number: int, page_count: int) -> str:
    return f"""# Page {page_number} of {page_count}: {title}

Convert this single PDF page into Markdown.

## Inputs

- `page.png`: primary visual source. Use image reading; do not depend on PDF text extraction.
- `page.pdf`: original single-page PDF for optional inspection.
- `page.json`: page dimensions and source metadata.

## Output

Write `page.md` in this same directory.

## Requirements

- Preserve all visible content from this page.
- Merge PDF line wraps into natural Markdown paragraphs.
- Use Markdown headings/lists/tables where appropriate.
- Reconstruct formulas from the page image, not from extracted text.
- Use Pandoc-compatible LaTeX math for formulas:
  - Inline formulas: `$...$`
  - Display formulas: `$$...$$`
  - Do not define custom LaTeX macros.
  - If standard LaTeX cannot represent a formula faithfully, add a `<!-- REVIEW: formula ... -->` note explaining the difficulty.
- If a formula cannot be reconstructed confidently, add a `<!-- REVIEW: ... -->` note. Do not invent formula structure.
- Preserve tables. Wide Markdown tables are acceptable; HTML tables are acceptable when Markdown tables are too limiting.
- Preserve figure captions.
- For figures that must remain visual, place or create a cropped image in this page directory and reference it from `page.md`, for example `![Figure 1](figure-1.png)`.
- Do not include full-page screenshots in `page.md`.
- Keep source traceability by starting the file with:

```markdown
<!-- source-page: {page_number} -->
```
"""


def prepare(args: argparse.Namespace) -> None:
    pdf_path = Path(args.pdf).expanduser().resolve()
    if not pdf_path.exists():
        fail(f"PDF not found: {pdf_path}")

    workdir = Path(args.workdir).expanduser().resolve() if args.workdir else Path("build") / safe_stem(pdf_path)
    if workdir.exists() and args.overwrite:
        for child_name in ("pages", "epub_src", "epub_unpacked", "work"):
            child = workdir / child_name
            if child.exists():
                shutil.rmtree(child)
    elif (workdir / "work" / "manifest.json").exists():
        fail(f"Work bundle already exists: {workdir}. Use --overwrite to replace it.")

    ensure_dir(workdir)
    pages_dir = workdir / "pages"
    work_dir = workdir / "work"
    ensure_dir(pages_dir)
    ensure_dir(work_dir)

    doc = fitz.open(pdf_path)
    title = args.title or doc.metadata.get("title") or pdf_path.stem
    page_records: list[dict[str, Any]] = []

    for page_index, page in enumerate(doc, start=1):
        page_dir = pages_dir / f"page-{page_index:03d}"
        ensure_dir(page_dir)
        render_page(page, page_dir / "page.png", args.page_dpi)
        save_single_page_pdf(doc, page_index - 1, page_dir / "page.pdf")
        page_json = {
            "source_pdf": str(pdf_path),
            "title": title,
            "page": page_index,
            "page_count": doc.page_count,
            "width": round(page.rect.width, 3),
            "height": round(page.rect.height, 3),
            "rotation": page.rotation,
            "output_markdown": "page.md",
        }
        write_json(page_dir / "page.json", page_json)
        (page_dir / "task.md").write_text(task_prompt(title, page_index, doc.page_count), encoding="utf-8")
        if not (page_dir / "page.md").exists():
            (page_dir / "page.md").write_text(f"<!-- source-page: {page_index} -->\n\n", encoding="utf-8")
        page_records.append({"page": page_index, "dir": str(page_dir), "markdown": str(page_dir / "page.md")})

    shutil.copy2(pdf_path, workdir / pdf_path.name)
    manifest = {
        "source_pdf": str(pdf_path),
        "copied_pdf": pdf_path.name,
        "workdir": str(workdir),
        "title": title,
        "page_count": doc.page_count,
        "pages": page_records,
        "commands": {
            "build": command_for("build", workdir),
            "verify": command_for("verify", workdir),
        },
    }
    write_json(work_dir / "manifest.json", manifest)
    print(json.dumps({"workdir": str(workdir), "pages": doc.page_count, "next": str(work_dir / "manifest.json")}, indent=2))


def normalize_raw_html_voids(markdown: str) -> str:
    markdown = re.sub(r"<br\s*>", "<br />", markdown, flags=re.IGNORECASE)
    markdown = re.sub(r"<hr\s*>", "<hr />", markdown, flags=re.IGNORECASE)
    return markdown


def clean_markdown(markdown: str) -> str:
    cleaned = "".join(ch for ch in markdown if ch in "\n\r\t" or ord(ch) >= 0x20)
    return normalize_raw_html_voids(cleaned)


class MarkdownConversionError(RuntimeError):
    pass


def markdown_to_xhtml(markdown: str) -> str:
    pandoc = shutil.which("pandoc")
    if not pandoc:
        raise MarkdownConversionError("pandoc executable not found; install Pandoc before running build")
    result = subprocess.run(
        [
            pandoc,
            "--from",
            PANDOC_MARKDOWN_FORMAT,
            "--to",
            "html5",
            "--mathml",
            "--wrap=none",
        ],
        input=clean_markdown(markdown),
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        stderr = result.stderr.strip() or f"pandoc exited with status {result.returncode}"
        raise MarkdownConversionError(stderr)
    return result.stdout


def split_markdown_destination(raw_href: str) -> tuple[str, str]:
    raw_href = raw_href.strip()
    if raw_href.startswith("<"):
        end = raw_href.find(">")
        if end != -1:
            return unquote(raw_href[1:end]), raw_href[end + 1 :]
    parts = raw_href.split(maxsplit=1)
    if not parts:
        return "", ""
    rest = f" {parts[1]}" if len(parts) > 1 else ""
    return unquote(parts[0].strip("<>\"'")), rest


def rewrite_markdown_image_sources(markdown: str, assets: dict[str, str]) -> str:
    def replace(match: re.Match[str]) -> str:
        alt_text = match.group(1)
        clean_href, rest = split_markdown_destination(match.group(2))
        if clean_href not in assets:
            return match.group(0)
        return f"![{alt_text}]({assets[clean_href]}{rest})"

    return re.sub(r"!\[([^\]]*)\]\(([^)]+)\)", replace, markdown)


def collect_markdown_image_assets(markdown: str, page_dir: Path, epub_src: Path, page_number: int) -> dict[str, str]:
    assets: dict[str, str] = {}
    asset_dir = epub_src / "assets" / f"page-{page_number:03d}"
    for match in re.finditer(r"!\[[^\]]*\]\(([^)]+)\)", markdown):
        raw_href = match.group(1)
        if re.match(r"^[a-z]+:", raw_href, re.IGNORECASE) or raw_href.startswith(("/", "#")):
            continue
        clean_href, _rest = split_markdown_destination(raw_href)
        source = (page_dir / clean_href).resolve()
        try:
            source.relative_to(page_dir.resolve())
        except ValueError:
            continue
        if not source.exists() or not source.is_file():
            continue
        ensure_dir(asset_dir)
        target = asset_dir / source.name
        shutil.copy2(source, target)
        assets[clean_href] = f"../assets/page-{page_number:03d}/{source.name}"
    return assets


def clean_metadata_text(text: str) -> str:
    text = re.sub(r"<!--.*?-->", "", text, flags=re.DOTALL)
    text = re.sub(r"<sup\b[^>]*>.*?</sup>", "", text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"!\[[^\]]*\]\([^)]+\)", "", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"^\s{0,3}#{1,6}\s+", "", text)
    text = re.sub(r"[*_`]+", "", text)
    text = re.sub(r"\[\^[^\]]+\]", "", text)
    text = re.sub(r"\s+", " ", html.unescape(text)).strip()
    return text.strip(" *†‡§¶#")


def infer_title_from_markdown(manifest: dict[str, Any]) -> str | None:
    for page in manifest.get("pages", [])[:1]:
        markdown_path = Path(page["markdown"])
        if not markdown_path.exists():
            continue
        for line in markdown_path.read_text(encoding="utf-8").splitlines():
            if not re.match(r"^\s{0,3}#\s+", line):
                continue
            candidate = clean_metadata_text(line)
            if candidate:
                return candidate
    return None


def validate_xml_text(text: str, label: str) -> list[str]:
    parser = etree.XMLParser(resolve_entities=False, recover=False)
    try:
        etree.fromstring(text.encode("utf-8"), parser)
    except etree.XMLSyntaxError as exc:
        return [f"{label}: {exc}"]
    return []


def wrap_page_xhtml(title: str, page_number: int, body_html: str) -> str:
    return "\n".join(
        [
            '<?xml version="1.0" encoding="utf-8"?>',
            f'<html xmlns="{XHTML_NS}">',
            "<head>",
            f"<title>{html.escape(title)} - Page {page_number}</title>",
            '<link rel="stylesheet" type="text/css" href="../styles.css"/>',
            "</head>",
            f'<body data-source-page="{page_number}">',
            f'<section id="page-{page_number}" class="pdf-page" data-source-page="{page_number}">',
            f'<h1 class="page-marker">Page {page_number}</h1>',
            body_html,
            "</section>",
            "</body>",
            "</html>",
        ]
    )


def default_css() -> str:
    return """body {
  line-height: 1.45;
}
.page-marker {
  font-size: 0.85em;
  font-weight: normal;
  color: #666;
  border-top: 1px solid #ddd;
  padding-top: 0.75em;
}
table {
  display: block;
  overflow-x: auto;
  border-collapse: collapse;
}
td, th {
  border: 1px solid #ddd;
  padding: 0.25em 0.4em;
}
pre {
  overflow-x: auto;
  white-space: pre;
}
math {
  overflow-x: auto;
}
math[display="block"] {
  display: block;
}
img {
  max-width: 100%;
  height: auto;
}
"""


def add_item(book: epub.EpubBook, uid: str, href: str, media_type: str, content: bytes | str) -> epub.EpubItem:
    item = epub.EpubItem(
        uid=uid,
        file_name=href,
        media_type=media_type,
        content=content,
    )
    book.add_item(item)
    return item


def image_media_type(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in {".jpg", ".jpeg"}:
        return "image/jpeg"
    if suffix == ".svg":
        return "image/svg+xml"
    if suffix == ".gif":
        return "image/gif"
    if suffix == ".webp":
        return "image/webp"
    return "image/png"


def unpack_epub(epub_path: Path, output_dir: Path) -> None:
    if output_dir.exists():
        shutil.rmtree(output_dir)
    ensure_dir(output_dir)
    with zipfile.ZipFile(epub_path) as archive:
        archive.extractall(output_dir)


def build(args: argparse.Namespace) -> None:
    workdir = Path(args.workdir).expanduser().resolve()
    manifest_path = workdir / "work" / "manifest.json"
    if not manifest_path.exists():
        fail(f"Missing manifest: {manifest_path}")
    manifest = read_json(manifest_path)
    inferred_title = infer_title_from_markdown(manifest)
    title = args.title or inferred_title or manifest.get("title") or "Converted PDF"
    language = args.language or "en"

    epub_src = workdir / "epub_src"
    if epub_src.exists():
        shutil.rmtree(epub_src)
    ensure_dir(epub_src / "pages")
    (epub_src / "styles.css").write_text(default_css(), encoding="utf-8")

    book = epub.EpubBook()
    book.set_identifier(str(uuid.uuid4()))
    book.set_title(title)
    book.set_language(language)
    book.add_metadata("DC", "source", manifest.get("source_pdf", ""))

    style_item = add_item(book, "styles", "styles.css", "text/css", default_css())
    chapters: list[epub.EpubHtml] = []
    errors: list[str] = []

    for page in manifest["pages"]:
        page_number = int(page["page"])
        markdown_path = Path(page["markdown"])
        page_dir = markdown_path.parent
        if not markdown_path.exists():
            errors.append(f"Missing Markdown for page {page_number}: {markdown_path}")
            continue
        markdown = markdown_path.read_text(encoding="utf-8")
        if not markdown.strip() or markdown.strip() == f"<!-- source-page: {page_number} -->":
            errors.append(f"Empty Markdown for page {page_number}: {markdown_path}")
        page_href = f"pages/page-{page_number:03d}.xhtml"
        assets = collect_markdown_image_assets(markdown, page_dir, epub_src, page_number)
        try:
            body_html = markdown_to_xhtml(rewrite_markdown_image_sources(markdown, assets))
        except MarkdownConversionError as exc:
            errors.append(f"{page_href}: {exc}")
            continue
        xhtml = wrap_page_xhtml(title, page_number, body_html)
        (epub_src / page_href).write_text(xhtml, encoding="utf-8")
        errors.extend(validate_xml_text(xhtml, page_href))

        chapter = epub.EpubHtml(title=f"Page {page_number}", file_name=page_href, lang=language)
        chapter.content = xhtml.encode("utf-8")
        chapter.add_item(style_item)
        book.add_item(chapter)
        chapters.append(chapter)

    if errors and not args.allow_errors:
        fail("Cannot build EPUB:\n" + "\n".join(errors[:30]))

    book.toc = tuple(epub.Link(chapter.file_name, chapter.title, f"page-{idx:03d}") for idx, chapter in enumerate(chapters, start=1))
    book.spine = ["nav", *chapters]
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())
    assets_dir = epub_src / "assets"
    if assets_dir.exists():
        for asset in sorted(assets_dir.glob("**/*")):
            if asset.is_file():
                href = str(asset.relative_to(epub_src))
                uid = f"asset-{re.sub(r'[^A-Za-z0-9_-]', '_', href)}"
                add_item(book, uid, href, image_media_type(asset), asset.read_bytes())

    output = Path(args.output).expanduser().resolve() if args.output else workdir / f"{safe_stem(Path(manifest['source_pdf']))}.epub"
    epub.write_epub(str(output), book)
    unpack_epub(output, workdir / "epub_unpacked")
    print(
        json.dumps(
            {
                "epub": str(output),
                "title": title,
                "chapters": len(chapters),
                "errors": errors,
                "unpacked": str(workdir / "epub_unpacked"),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


def verify(args: argparse.Namespace) -> None:
    workdir = Path(args.workdir).expanduser().resolve()
    manifest_path = workdir / "work" / "manifest.json"
    if not manifest_path.exists():
        fail(f"Missing manifest: {manifest_path}")
    manifest = read_json(manifest_path)
    errors: list[str] = []
    checks: list[dict[str, Any]] = []

    markdown_files = []
    empty_pages = []
    review_notes = []
    for page in manifest["pages"]:
        markdown_path = Path(page["markdown"])
        if markdown_path.exists():
            markdown_files.append(str(markdown_path))
            markdown = markdown_path.read_text(encoding="utf-8")
            if not markdown.strip() or markdown.strip() == f"<!-- source-page: {page['page']} -->":
                empty_pages.append(page["page"])
            if "<!-- REVIEW:" in markdown:
                review_notes.append(page["page"])
        else:
            errors.append(f"Missing Markdown: {markdown_path}")
    checks.append({"markdown_files": len(markdown_files)})
    checks.append({"empty_pages": empty_pages})
    checks.append({"review_note_pages": sorted(set(review_notes))})

    if args.epub:
        epub_path = Path(args.epub).expanduser().resolve()
        if not epub_path.exists():
            errors.append(f"EPUB not found: {epub_path}")
        else:
            try:
                with zipfile.ZipFile(epub_path) as archive:
                    bad = archive.testzip()
                    names = archive.namelist()
                checks.append({"epub_zip": "ok" if bad is None else f"bad file: {bad}"})
                checks.append({"epub_page_xhtml": sum(1 for name in names if name.startswith("EPUB/pages/page-") and name.endswith(".xhtml"))})
            except zipfile.BadZipFile as exc:
                errors.append(f"Invalid EPUB: {exc}")

    report = {"workdir": str(workdir), "checks": checks, "errors": errors}
    write_json(workdir / "work" / "verification_report.json", report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if errors:
        raise SystemExit(1)


def make_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    prepare_parser = sub.add_parser("prepare", help="Split PDF into page tasks")
    prepare_parser.add_argument("pdf")
    prepare_parser.add_argument("--workdir")
    prepare_parser.add_argument("--title")
    prepare_parser.add_argument("--page-dpi", type=int, default=170)
    prepare_parser.add_argument("--overwrite", action="store_true")
    prepare_parser.set_defaults(func=prepare)

    build_parser = sub.add_parser("build", help="Package completed page Markdown files into EPUB")
    build_parser.add_argument("--workdir", required=True)
    build_parser.add_argument("-o", "--output")
    build_parser.add_argument("--title")
    build_parser.add_argument("--language", default="en")
    build_parser.add_argument("--allow-errors", action="store_true")
    build_parser.set_defaults(func=build)

    verify_parser = sub.add_parser("verify", help="Check page task completion and optional EPUB")
    verify_parser.add_argument("--workdir", required=True)
    verify_parser.add_argument("--epub")
    verify_parser.set_defaults(func=verify)
    return parser


def main() -> None:
    parser = make_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
