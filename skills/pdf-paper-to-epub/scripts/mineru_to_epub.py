#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# ///
"""Convert MinerU technical-paper output into EPUB via Pandoc."""

from __future__ import annotations

import argparse
import html
import json
import re
import shutil
import subprocess
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

PANDOC_FROM = "markdown+raw_html+pipe_tables+tex_math_dollars+footnotes"
SKIP_TYPES = {"page_number", "page_footer"}


def fail(message: str) -> None:
    raise SystemExit(f"error: {message}")


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def safe_stem(text: str) -> str:
    stem = re.sub(r"[^A-Za-z0-9._-]+", "-", text).strip("-")
    return stem or "paper"


def resolve_mineru_dir(path: Path) -> Path:
    path = path.expanduser().resolve()
    if not path.exists():
        fail(f"MinerU path does not exist: {path}")
    if path.is_file():
        if path.name.endswith("_content_list_v2.json"):
            return path.parent
        fail(f"Expected a MinerU directory or *_content_list_v2.json file: {path}")
    if list(path.glob("*_content_list_v2.json")):
        return path
    hybrid = path / "hybrid_auto"
    if hybrid.is_dir() and list(hybrid.glob("*_content_list_v2.json")):
        return hybrid.resolve()
    matches = sorted(path.glob("**/*_content_list_v2.json"))
    if len(matches) == 1:
        return matches[0].parent.resolve()
    if not matches:
        fail(f"No *_content_list_v2.json found under {path}")
    fail("Multiple *_content_list_v2.json files found; pass the exact hybrid_auto directory")


def find_single(pattern: str, directory: Path, required: bool = True) -> Path | None:
    matches = sorted(directory.glob(pattern))
    if matches:
        return matches[0]
    if required:
        fail(f"Missing {pattern} in {directory}")
    return None


def infer_stem(mineru_dir: Path) -> str:
    v2 = find_single("*_content_list_v2.json", mineru_dir)
    suffix = "_content_list_v2"
    if v2 and v2.stem.endswith(suffix):
        return v2.stem[: -len(suffix)]
    return mineru_dir.parent.name if mineru_dir.name == "hybrid_auto" else mineru_dir.name


def flatten_pages(data: Any) -> list[tuple[int, int, dict[str, Any]]]:
    flattened: list[tuple[int, int, dict[str, Any]]] = []
    if not isinstance(data, list):
        fail("MinerU v2 JSON root must be a list")
    for page_index, page in enumerate(data, start=1):
        elements = page if isinstance(page, list) else [page]
        for element_index, element in enumerate(elements, start=1):
            if isinstance(element, dict):
                flattened.append((page_index, element_index, element))
    return flattened


def markdown_escape_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    return text.replace("$", r"\$")


def tidy_text(text: str) -> str:
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def formula_id(page: int, element_index: int, fragment_index: int | None = None) -> str:
    base = f"p{page:03d}-e{element_index:03d}"
    return f"{base}-f{fragment_index:03d}" if fragment_index is not None else base


def as_text_fragment(fragment: dict[str, Any], ctx: BuildContext | None = None, page: int | None = None, element_index: int | None = None, fragment_index: int | None = None) -> str:
    kind = fragment.get("type")
    content = str(fragment.get("content", ""))
    if kind in {"equation_inline", "math_inline"}:
        math = content.strip()
        if ctx is not None and page is not None and element_index is not None and fragment_index is not None:
            math = ctx.repairs.get(formula_id(page, element_index, fragment_index), math)
        return f"${math}$"
    return markdown_escape_text(content)


def render_fragments(fragments: Any, ctx: BuildContext | None = None, page: int | None = None, element_index: int | None = None) -> str:
    if isinstance(fragments, str):
        return markdown_escape_text(fragments)
    if not isinstance(fragments, list):
        return ""
    parts: list[str] = []
    for fragment_index, fragment in enumerate(fragments, start=1):
        if isinstance(fragment, dict):
            parts.append(as_text_fragment(fragment, ctx, page, element_index, fragment_index))
    return tidy_text("".join(parts))


def strip_markdown(text: str) -> str:
    text = re.sub(r"\$([^$]+)\$", r"\1", text)
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"[*_`#]+", "", text)
    return html.unescape(re.sub(r"\s+", " ", text)).strip()


def heading_level(title: str, title_count: int) -> int:
    if title_count == 1:
        return 1
    stripped = title.strip()
    match = re.match(r"^(\d+(?:\.\d+)*)\b", stripped)
    if match:
        return min(6, 2 + match.group(1).count("."))
    return 2


def extension_for(path: Path) -> str:
    suffix = path.suffix.lower()
    return suffix if suffix else ".jpg"


def copy_relative_asset(mineru_dir: Path, rel_path: str | None, target_dir: Path, name_hint: str) -> str | None:
    if not rel_path:
        return None
    source = (mineru_dir / rel_path).resolve()
    try:
        source.relative_to(mineru_dir.resolve())
    except ValueError:
        return None
    if not source.exists() or not source.is_file():
        return None
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / f"{safe_stem(name_hint)}{extension_for(source)}"
    counter = 2
    while target.exists():
        target = target_dir / f"{safe_stem(name_hint)}-{counter}{extension_for(source)}"
        counter += 1
    shutil.copy2(source, target)
    return str(target)


def math_warnings(math: str, image_path: str | None, kind: str) -> list[str]:
    warnings: list[str] = []
    if not math.strip():
        warnings.append("empty math content")
    if kind == "display" and not image_path:
        warnings.append("missing formula image crop")
    if count_unescaped(math, "{") != count_unescaped(math, "}"):
        warnings.append("unbalanced braces")
    if "�" in math or "□" in math:
        warnings.append("replacement or unknown character")
    if re.search(r"\b\d(?:\s+\d){1,}\b", math):
        warnings.append("digit-separated OCR artifact")
    if math.count(r"\left") != math.count(r"\right"):
        warnings.append("unbalanced left/right delimiters")
    return warnings


def count_unescaped(text: str, char: str) -> int:
    count = 0
    for index, value in enumerate(text):
        if value == char and (index == 0 or text[index - 1] != "\\"):
            count += 1
    return count


@dataclass
class FormulaAudit:
    formulas: list[dict[str, Any]] = field(default_factory=list)
    pandoc_warnings: list[str] = field(default_factory=list)

    def add(self, entry: dict[str, Any]) -> None:
        self.formulas.append(entry)

    def summary(self) -> dict[str, Any]:
        display = sum(1 for item in self.formulas if item["kind"] == "display")
        inline = sum(1 for item in self.formulas if item["kind"] == "inline")
        warning_count = sum(1 for item in self.formulas if item.get("warnings")) + len(self.pandoc_warnings)
        return {"display": display, "inline": inline, "warning_entries": warning_count}


@dataclass
class BuildContext:
    mineru_dir: Path
    build_dir: Path
    assets_dir: Path
    formula_images_dir: Path
    repairs: dict[str, str] = field(default_factory=dict)
    audit: FormulaAudit = field(default_factory=FormulaAudit)
    title_count: int = 0
    display_formula_count: int = 0
    figure_count: int = 0
    table_count: int = 0


def audit_inline_formulas(ctx: BuildContext, page: int, element_index: int, fragments: Any) -> None:
    if not isinstance(fragments, list):
        return
    for fragment_index, fragment in enumerate(fragments, start=1):
        if not isinstance(fragment, dict) or fragment.get("type") != "equation_inline":
            continue
        source_math = str(fragment.get("content", "")).strip()
        entry_id = formula_id(page, element_index, fragment_index)
        math = ctx.repairs.get(entry_id, source_math)
        ctx.audit.add(
            {
                "id": entry_id,
                "kind": "inline",
                "page": page,
                "element_index": element_index,
                "fragment_index": fragment_index,
                "math": math,
                "source_math": source_math,
                "repaired": math != source_math,
                "warnings": math_warnings(math, None, "inline"),
            }
        )


def render_caption(content: dict[str, Any], keys: tuple[str, ...]) -> str:
    for key in keys:
        caption = render_fragments(content.get(key))
        if caption:
            return caption
    return ""


def render_title(ctx: BuildContext, content: dict[str, Any]) -> str:
    title = render_fragments(content.get("title_content"), ctx)
    if not title:
        title = markdown_escape_text(str(content.get("content", ""))).strip()
    if not title:
        return ""
    ctx.title_count += 1
    level = heading_level(strip_markdown(title), ctx.title_count)
    return f"{'#' * level} {title}"


def render_paragraph(ctx: BuildContext, page: int, element_index: int, content: dict[str, Any], key: str = "paragraph_content") -> str:
    fragments = content.get(key)
    audit_inline_formulas(ctx, page, element_index, fragments)
    return render_fragments(fragments, ctx, page, element_index)


def render_display_equation(ctx: BuildContext, page: int, element_index: int, element: dict[str, Any]) -> str:
    content = element.get("content", {})
    source_math = str(content.get("math_content", "")).strip()
    entry_id = formula_id(page, element_index)
    math = ctx.repairs.get(entry_id, source_math)
    ctx.display_formula_count += 1
    rel_image = ((content.get("image_source") or {}).get("path") if isinstance(content.get("image_source"), dict) else None)
    copied = copy_relative_asset(
        ctx.mineru_dir,
        rel_image,
        ctx.formula_images_dir,
        f"page-{page:03d}-equation-{ctx.display_formula_count:03d}",
    )
    entry = {
        "id": entry_id,
        "kind": "display",
        "page": page,
        "element_index": element_index,
        "bbox": element.get("bbox"),
        "math": math,
        "source_math": source_math,
        "repaired": math != source_math,
        "source_image": rel_image,
        "copied_image": str(Path(copied).relative_to(ctx.build_dir)) if copied else None,
        "warnings": math_warnings(math, copied, "display"),
    }
    ctx.audit.add(entry)
    if not math:
        return "<!-- REVIEW: empty display formula from MinerU -->"
    return f"$$\n{math}\n$$"


def render_table(ctx: BuildContext, page: int, element: dict[str, Any]) -> str:
    content = element.get("content", {})
    ctx.table_count += 1
    caption = render_caption(content, ("table_caption",))
    rel_image = ((content.get("image_source") or {}).get("path") if isinstance(content.get("image_source"), dict) else None)
    copied = copy_relative_asset(ctx.mineru_dir, rel_image, ctx.assets_dir, f"page-{page:03d}-table-{ctx.table_count:03d}")
    html_table = str(content.get("html", "")).strip()
    parts: list[str] = []
    if caption:
        parts.append(f"**{caption}**")
    if html_table:
        parts.append(f'<div class="table-wrap">\n{html_table}\n</div>')
    elif copied:
        parts.append(f"![{strip_markdown(caption) or 'Table'}]({Path(copied).relative_to(ctx.build_dir)})")
    else:
        parts.append("<!-- REVIEW: table has no HTML or copied image asset -->")
    return "\n\n".join(parts)


def render_visual(ctx: BuildContext, page: int, element: dict[str, Any], kind: str) -> str:
    content = element.get("content", {})
    ctx.figure_count += 1
    caption = render_caption(content, ("chart_caption", "image_caption"))
    rel_image = ((content.get("image_source") or {}).get("path") if isinstance(content.get("image_source"), dict) else None)
    copied = copy_relative_asset(ctx.mineru_dir, rel_image, ctx.assets_dir, f"page-{page:03d}-{kind}-{ctx.figure_count:03d}")
    if copied:
        return f"![{strip_markdown(caption) or kind.title()}]({Path(copied).relative_to(ctx.build_dir)})" + (f"\n\n*{caption}*" if caption else "")
    textual = str(content.get("content", "")).strip()
    if textual:
        return textual
    return f"<!-- REVIEW: {kind} has no copied image asset or textual content -->"


def render_list(ctx: BuildContext, page: int, element_index: int, content: dict[str, Any]) -> str:
    items = content.get("list_items") or []
    rendered: list[str] = []
    reference_list = content.get("list_type") == "reference_list"
    for item in items:
        if not isinstance(item, dict):
            continue
        fragments = item.get("item_content") or []
        audit_inline_formulas(ctx, page, element_index, fragments)
        text = render_fragments(fragments, ctx, page, element_index)
        if not text:
            continue
        rendered.append(text if reference_list else f"- {text}")
    return "\n\n".join(rendered) if reference_list else "\n".join(rendered)


def render_element(ctx: BuildContext, page: int, element_index: int, element: dict[str, Any]) -> str:
    element_type = element.get("type")
    content = element.get("content", {})
    if element_type in SKIP_TYPES:
        return ""
    if element_type == "title":
        return render_title(ctx, content)
    if element_type == "paragraph":
        return render_paragraph(ctx, page, element_index, content)
    if element_type == "equation_interline":
        return render_display_equation(ctx, page, element_index, element)
    if element_type == "table":
        return render_table(ctx, page, element)
    if element_type in {"chart", "image"}:
        return render_visual(ctx, page, element, str(element_type))
    if element_type == "list":
        return render_list(ctx, page, element_index, content)
    if element_type == "page_footnote":
        text = render_paragraph(ctx, page, element_index, content, "page_footnote_content")
        return f'<aside class="page-footnote" data-source-page="{page}">{html.escape(text)}</aside>' if text else ""
    if element_type == "page_aside_text":
        text = render_paragraph(ctx, page, element_index, content, "page_aside_text_content")
        return f'<aside class="page-aside" data-source-page="{page}">{html.escape(text)}</aside>' if text else ""
    direct = str(content.get("content", "")).strip() if isinstance(content, dict) else ""
    return markdown_escape_text(direct) if direct else f"<!-- REVIEW: unsupported MinerU element type {element_type!r} on page {page} -->"


def default_css() -> str:
    return """body {
  line-height: 1.45;
}
img {
  max-width: 100%;
  height: auto;
}
.table-wrap {
  display: block;
  overflow-x: auto;
}
table {
  border-collapse: collapse;
  margin: 1em 0;
}
td, th {
  border: 1px solid #ccc;
  padding: 0.25em 0.4em;
  vertical-align: top;
}
math[display="block"] {
  display: block;
  overflow-x: auto;
  margin: 1em 0;
}
.page-footnote, .page-aside {
  font-size: 0.85em;
  color: #444;
  margin: 0.75em 0;
}
"""


def inspect_mineru(mineru_dir: Path) -> dict[str, Any]:
    v2_path = find_single("*_content_list_v2.json", mineru_dir)
    data = read_json(v2_path)
    flattened = flatten_pages(data)
    counts: dict[str, int] = {}
    inline = 0
    display = 0
    missing_assets: list[str] = []
    for _page, _idx, element in flattened:
        element_type = str(element.get("type"))
        counts[element_type] = counts.get(element_type, 0) + 1
        content = element.get("content", {})
        if element_type == "equation_interline":
            display += 1
        for key in ("paragraph_content", "title_content", "page_footnote_content", "page_aside_text_content"):
            fragments = content.get(key) if isinstance(content, dict) else None
            if isinstance(fragments, list):
                inline += sum(1 for fragment in fragments if isinstance(fragment, dict) and fragment.get("type") == "equation_inline")
        rel_image = (content.get("image_source") or {}).get("path") if isinstance(content, dict) and isinstance(content.get("image_source"), dict) else None
        if rel_image and not (mineru_dir / rel_image).exists():
            missing_assets.append(rel_image)
    return {
        "mineru_dir": str(mineru_dir),
        "v2_json": str(v2_path),
        "pages": len(data),
        "elements": len(flattened),
        "counts": dict(sorted(counts.items())),
        "formulas": {"display": display, "inline": inline},
        "missing_assets": sorted(set(missing_assets)),
    }


def load_repairs(path: str | None) -> dict[str, str]:
    if not path:
        return {}
    repair_path = Path(path).expanduser().resolve()
    data = read_json(repair_path)
    repairs: dict[str, str] = {}
    items = data.get("repairs", data) if isinstance(data, dict) else data
    if not isinstance(items, list):
        fail("Formula repair file must be a list or an object with a 'repairs' list")
    for item in items:
        if not isinstance(item, dict):
            continue
        item_id = str(item.get("id") or item.get("formula_id") or "").strip()
        replacement = item.get("replacement")
        if not item_id or replacement is None:
            continue
        repairs[item_id] = str(replacement).strip()
    return repairs


def render_book(mineru_dir: Path, build_dir: Path, repairs: dict[str, str] | None = None) -> tuple[Path, FormulaAudit]:
    v2_path = find_single("*_content_list_v2.json", mineru_dir)
    data = read_json(v2_path)
    if build_dir.exists():
        shutil.rmtree(build_dir)
    build_dir.mkdir(parents=True, exist_ok=True)
    ctx = BuildContext(
        mineru_dir=mineru_dir,
        build_dir=build_dir,
        assets_dir=build_dir / "assets",
        formula_images_dir=build_dir / "formula_images",
        repairs=repairs or {},
    )
    blocks: list[str] = []
    for page, element_index, element in flatten_pages(data):
        block = render_element(ctx, page, element_index, element)
        if block.strip():
            blocks.append(block.strip())
    markdown = "\n\n".join(blocks).strip() + "\n"
    book_md = build_dir / "book.md"
    book_md.write_text(markdown, encoding="utf-8")
    (build_dir / "styles.css").write_text(default_css(), encoding="utf-8")
    write_json(
        build_dir / "audit" / "formula_audit.json",
        {
            "mineru_dir": str(mineru_dir),
            "source_json": str(v2_path),
            "summary": ctx.audit.summary(),
            "repair_count": len(ctx.repairs),
            "formulas": ctx.audit.formulas,
            "pandoc_warnings": ctx.audit.pandoc_warnings,
        },
    )
    if ctx.repairs:
        write_json(
            build_dir / "audit" / "applied_formula_repairs.json",
            {"repairs": [{"id": item_id, "replacement": replacement} for item_id, replacement in sorted(ctx.repairs.items())]},
        )
    write_formula_review(build_dir / "audit" / "formula_review.md", ctx.audit)
    return book_md, ctx.audit


def write_formula_review(path: Path, audit: FormulaAudit) -> None:
    lines = ["# Formula Review", ""]
    warned = [entry for entry in audit.formulas if entry.get("warnings")]
    if not warned and not audit.pandoc_warnings:
        lines.append("No formula warnings detected.")
    for entry in warned:
        location = f"page {entry.get('page')}, element {entry.get('element_index')}"
        if entry.get("fragment_index"):
            location += f", fragment {entry.get('fragment_index')}"
        lines.extend(
            [
                f"## {entry.get('kind', 'formula').title()} Formula: {location}",
                "",
                f"- ID: `{entry.get('id')}`",
                "- Warnings: " + "; ".join(entry.get("warnings", [])),
                f"- Copied image: `{entry.get('copied_image')}`" if entry.get("copied_image") else "- Copied image: none",
                f"- Repaired: `{entry.get('repaired', False)}`",
                "",
                "```tex",
                str(entry.get("math", "")),
                "```",
                "",
            ]
        )
    if audit.pandoc_warnings:
        lines.extend(["## Pandoc Warnings", ""])
        lines.extend(f"- {warning}" for warning in audit.pandoc_warnings)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def pandoc_warning_blocks(warnings: list[str]) -> list[list[str]]:
    blocks: list[list[str]] = []
    current: list[str] = []
    for line in warnings:
        if line.startswith("[WARNING]") and current:
            blocks.append(current)
            current = []
        current.append(line)
    if current:
        blocks.append(current)
    return blocks


def pandoc_formula_failures(warnings: list[str], formulas: list[dict[str, Any]]) -> list[dict[str, Any]]:
    failures: list[dict[str, Any]] = []
    formulas_by_math: dict[str, list[dict[str, Any]]] = {}
    for formula in formulas:
        formulas_by_math.setdefault(str(formula.get("math", "")).strip(), []).append(formula)

    for block in pandoc_warning_blocks(warnings):
        first = block[0] if block else ""
        match = re.match(r"^\[WARNING\] Could not convert TeX math (.*), rendering as TeX:$", first)
        if not match:
            continue
        math = match.group(1).strip()
        matches = formulas_by_math.get(math, [])
        if matches:
            for formula in matches:
                failures.append({**formula, "pandoc_warning": block})
        else:
            failures.append({"id": None, "kind": "unknown", "math": math, "pandoc_warning": block})
    return failures


def write_formula_repair_tasks(build_dir: Path, failures: list[dict[str, Any]]) -> None:
    tasks_path = build_dir / "audit" / "formula_repair_tasks.md"
    template_path = build_dir / "audit" / "formula_repairs.template.json"
    lines = [
        "# Formula Repair Tasks",
        "",
        "Pandoc could not parse these formulas. Inspect the copied formula image when available, then write corrected LaTeX into `formula_repairs.json` using the IDs below.",
        "",
    ]
    template = {"repairs": []}
    for failure in failures:
        location = f"page {failure.get('page')}, element {failure.get('element_index')}"
        if failure.get("fragment_index"):
            location += f", fragment {failure.get('fragment_index')}"
        formula_id_value = failure.get("id")
        lines.extend(
            [
                f"## {formula_id_value or 'unmatched-formula'}",
                "",
                f"- Location: {location}",
                f"- Kind: {failure.get('kind')}",
                f"- Copied image: `{failure.get('copied_image')}`" if failure.get("copied_image") else "- Copied image: none",
                "- Pandoc warning:",
                "",
                "```text",
                "\n".join(str(line) for line in failure.get("pandoc_warning", [])),
                "```",
                "",
                "- Current LaTeX:",
                "",
                "```tex",
                str(failure.get("math", "")),
                "```",
                "",
            ]
        )
        if formula_id_value:
            template["repairs"].append(
                {
                    "id": formula_id_value,
                    "replacement": str(failure.get("math", "")),
                    "note": "Replace this with agent-reviewed LaTeX that Pandoc can parse and that matches the formula crop.",
                }
            )
    tasks_path.parent.mkdir(parents=True, exist_ok=True)
    tasks_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    write_json(template_path, template)


def run_pandoc(book_md: Path, output: Path, build_dir: Path) -> list[str]:
    if not shutil.which("pandoc"):
        fail("pandoc executable not found; install Pandoc or add it to PATH")
    output.parent.mkdir(parents=True, exist_ok=True)
    command = [
        "pandoc",
        str(book_md),
        "--from",
        PANDOC_FROM,
        "--to",
        "epub3",
        "--standalone",
        "--mathml",
        "--wrap=none",
        "--css",
        str(build_dir / "styles.css"),
        "--resource-path",
        str(build_dir),
        "--output",
        str(output),
    ]
    result = subprocess.run(command, text=True, capture_output=True, check=False)
    warnings = [line for line in result.stderr.splitlines() if line.strip()]
    if result.returncode != 0:
        raise SystemExit("error: pandoc failed:\n" + result.stderr.strip())
    return warnings


def update_audit_with_pandoc_warnings(build_dir: Path, warnings: list[str]) -> list[dict[str, Any]]:
    audit_path = build_dir / "audit" / "formula_audit.json"
    audit_data = read_json(audit_path)
    audit_data["pandoc_warnings"] = warnings
    failures = pandoc_formula_failures(warnings, audit_data.get("formulas", []))
    audit_data["pandoc_formula_failures"] = failures
    audit_data["summary"]["pandoc_formula_failures"] = len(failures)
    audit_data["summary"]["warning_entries"] = audit_data["summary"].get("warning_entries", 0) + len(warnings)
    write_json(audit_path, audit_data)
    audit = FormulaAudit(formulas=audit_data["formulas"], pandoc_warnings=warnings)
    write_formula_review(build_dir / "audit" / "formula_review.md", audit)
    if failures:
        write_formula_repair_tasks(build_dir, failures)
    return failures


def default_build_dir(mineru_dir: Path, requested: str | None) -> Path:
    if requested:
        return Path(requested).expanduser().resolve()
    return (Path.cwd() / "build" / safe_stem(infer_stem(mineru_dir))).resolve()


def convert(args: argparse.Namespace) -> None:
    mineru_dir = resolve_mineru_dir(Path(args.mineru_dir))
    build_dir = default_build_dir(mineru_dir, args.build_dir)
    output = Path(args.output).expanduser().resolve() if args.output else (Path.cwd() / f"{safe_stem(infer_stem(mineru_dir))}.epub").resolve()
    repairs = load_repairs(args.repairs)
    book_md, _audit = render_book(mineru_dir, build_dir, repairs)
    warnings = run_pandoc(book_md, output, build_dir)
    failures = update_audit_with_pandoc_warnings(build_dir, warnings)
    result = {
        "epub": str(output),
        "build_dir": str(build_dir),
        "markdown": str(book_md),
        "formula_audit": str(build_dir / "audit" / "formula_audit.json"),
        "formula_review": str(build_dir / "audit" / "formula_review.md"),
        "formula_repair_tasks": str(build_dir / "audit" / "formula_repair_tasks.md") if failures else None,
        "formula_repairs_template": str(build_dir / "audit" / "formula_repairs.template.json") if failures else None,
        "pandoc_warnings": warnings,
        "pandoc_formula_failures": len(failures),
        "repair_count": len(repairs),
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if failures and not args.allow_formula_warnings:
        raise SystemExit(
            "error: Pandoc formula failures require agent repair. "
            f"Review {build_dir / 'audit' / 'formula_repair_tasks.md'} and rerun with --repairs."
        )


def apply_repairs(args: argparse.Namespace) -> None:
    if not args.repairs:
        fail("apply-repairs requires --repairs")
    convert(args)


def verify(args: argparse.Namespace) -> None:
    mineru_dir = resolve_mineru_dir(Path(args.mineru_dir))
    build_dir = default_build_dir(mineru_dir, args.build_dir)
    errors: list[str] = []
    checks: dict[str, Any] = {"mineru_dir": str(mineru_dir), "build_dir": str(build_dir)}
    expected = inspect_mineru(mineru_dir)
    checks["expected_formulas"] = expected["formulas"]
    book_md = build_dir / "book.md"
    if not book_md.exists() or not book_md.read_text(encoding="utf-8").strip():
        errors.append(f"Missing or empty generated Markdown: {book_md}")
    audit_path = build_dir / "audit" / "formula_audit.json"
    if not audit_path.exists():
        errors.append(f"Missing formula audit: {audit_path}")
    else:
        audit = read_json(audit_path)
        summary = audit.get("summary", {})
        checks["audited_formulas"] = {"display": summary.get("display"), "inline": summary.get("inline")}
        if summary.get("display") != expected["formulas"]["display"]:
            errors.append("Display formula count does not match MinerU v2 JSON")
        if summary.get("inline") != expected["formulas"]["inline"]:
            errors.append("Inline formula count does not match MinerU v2 JSON")
        missing_crops = [entry for entry in audit.get("formulas", []) if entry.get("kind") == "display" and not entry.get("copied_image")]
        checks["display_formulas_without_copied_images"] = len(missing_crops)
        pandoc_failures = audit.get("pandoc_formula_failures", [])
        checks["pandoc_formula_failures"] = len(pandoc_failures)
        if pandoc_failures:
            errors.append("Pandoc formula failures remain; apply agent-reviewed repairs before final verification")
    if args.epub:
        epub_path = Path(args.epub).expanduser().resolve()
        if not epub_path.exists():
            errors.append(f"EPUB not found: {epub_path}")
        else:
            try:
                with zipfile.ZipFile(epub_path) as archive:
                    bad_file = archive.testzip()
                    names = archive.namelist()
                checks["epub_zip"] = "ok" if bad_file is None else f"bad file: {bad_file}"
                checks["epub_files"] = len(names)
            except zipfile.BadZipFile as exc:
                errors.append(f"Invalid EPUB zip: {exc}")
    report = {"checks": checks, "errors": errors}
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if errors:
        raise SystemExit(1)


def make_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    inspect_parser = subparsers.add_parser("inspect", help="Summarize a MinerU output directory")
    inspect_parser.add_argument("mineru_dir")
    inspect_parser.set_defaults(func=lambda args: print(json.dumps(inspect_mineru(resolve_mineru_dir(Path(args.mineru_dir))), ensure_ascii=False, indent=2)))

    convert_parser = subparsers.add_parser("convert", help="Convert MinerU output to EPUB")
    convert_parser.add_argument("mineru_dir")
    convert_parser.add_argument("--output", "-o")
    convert_parser.add_argument("--build-dir")
    convert_parser.add_argument("--repairs", help="JSON file containing agent-reviewed formula repairs")
    convert_parser.add_argument("--allow-formula-warnings", action="store_true", help="Write a draft EPUB even when Pandoc reports formula parse failures")
    convert_parser.set_defaults(func=convert)

    repair_parser = subparsers.add_parser("apply-repairs", help="Apply agent-reviewed formula repairs and rebuild the EPUB")
    repair_parser.add_argument("mineru_dir")
    repair_parser.add_argument("--repairs", required=True)
    repair_parser.add_argument("--output", "-o")
    repair_parser.add_argument("--build-dir")
    repair_parser.add_argument("--allow-formula-warnings", action="store_true")
    repair_parser.set_defaults(func=apply_repairs)

    verify_parser = subparsers.add_parser("verify", help="Verify generated Markdown, audit, and optional EPUB")
    verify_parser.add_argument("mineru_dir")
    verify_parser.add_argument("--epub")
    verify_parser.add_argument("--build-dir")
    verify_parser.set_defaults(func=verify)
    return parser


def main() -> None:
    parser = make_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
