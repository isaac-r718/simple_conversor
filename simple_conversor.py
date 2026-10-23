"""Convert documents to compact, readable Markdown for language models."""

from __future__ import annotations

import argparse
import re
import sys
import zipfile
from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path
from typing import Callable
from xml.etree import ElementTree


ROOT = Path(__file__).resolve().parent
SUPPORTED_EXTENSIONS = {
    ".docx",
    ".html",
    ".htm",
    ".md",
    ".odt",
    ".pdf",
    ".rtf",
    ".txt",
}
WORD_NS = {
    "w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main",
}
ODT_NS = {
    "office": "urn:oasis:names:tc:opendocument:xmlns:office:1.0",
    "table": "urn:oasis:names:tc:opendocument:xmlns:table:1.0",
    "text": "urn:oasis:names:tc:opendocument:xmlns:text:1.0",
}


class ConversionError(Exception):
    """An expected error that can be reported without a traceback."""


def normalize_markdown(text: str) -> str:
    """Trim excess whitespace without changing the document's wording."""
    lines = [line.rstrip() for line in text.replace("\r\n", "\n").split("\n")]
    text = "\n".join(lines)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _word_text(element: ElementTree.Element) -> str:
    parts: list[str] = []
    for node in element.iter():
        if node.tag == f"{{{WORD_NS['w']}}}t":
            parts.append(node.text or "")
        elif node.tag == f"{{{WORD_NS['w']}}}tab":
            parts.append("\t")
        elif node.tag == f"{{{WORD_NS['w']}}}br":
            parts.append("\n")
    return "".join(parts).strip()


def _word_paragraph(paragraph: ElementTree.Element) -> str:
    text = _word_text(paragraph)
    if not text:
        return ""

    properties = paragraph.find("w:pPr", WORD_NS)
    style = ""
    is_list = False
    if properties is not None:
        style_node = properties.find("w:pStyle", WORD_NS)
        if style_node is not None:
            style = style_node.get(f"{{{WORD_NS['w']}}}val", "")
        is_list = properties.find("w:numPr", WORD_NS) is not None

    heading = re.fullmatch(r"Heading([1-6])", style, re.IGNORECASE)
    if heading:
        return f"{'#' * int(heading.group(1))} {text}"
    if style.lower() == "title":
        return f"# {text}"
    if is_list:
        return f"- {text}"
    return text


def _word_table(table: ElementTree.Element) -> str:
    rows: list[list[str]] = []
    for row in table.findall("w:tr", WORD_NS):
        cells = []
        for cell in row.findall("w:tc", WORD_NS):
            paragraphs = [
                _word_paragraph(paragraph)
                for paragraph in cell.findall("w:p", WORD_NS)
            ]
            content = "<br>".join(part for part in paragraphs if part)
            cells.append(content.replace("|", r"\|"))
        if cells:
            rows.append(cells)

    if not rows:
        return ""

    width = max(map(len, rows))
    rows = [row + [""] * (width - len(row)) for row in rows]
    separator = ["---"] * width
    return "\n".join(
        "| " + " | ".join(row) + " |"
        for row in [rows[0], separator, *rows[1:]]
    )


def extract_docx(path: Path) -> str:
    try:
        with zipfile.ZipFile(path) as archive:
            with archive.open("word/document.xml") as document:
                root = ElementTree.parse(document).getroot()
    except KeyError as error:
        raise ConversionError("El DOCX no contiene word/document.xml.") from error

    body = root.find(".//w:body", WORD_NS)
    if body is None:
        raise ConversionError("No se encontró el contenido principal del DOCX.")

    blocks: list[str] = []
    for element in body:
        if element.tag == f"{{{WORD_NS['w']}}}p":
            block = _word_paragraph(element)
        elif element.tag == f"{{{WORD_NS['w']}}}tbl":
            block = _word_table(element)
        else:
            continue
        if block:
            blocks.append(block)
    return "\n\n".join(blocks)


def _odt_block(element: ElementTree.Element) -> str:
    if element.tag == f"{{{ODT_NS['text']}}}list":
        items = [
            "".join(item.itertext()).strip()
            for item in element.findall("text:list-item", ODT_NS)
        ]
        return "\n".join(f"- {item}" for item in items if item)

    text = "".join(element.itertext()).strip()
    if not text:
        return ""
    if element.tag == f"{{{ODT_NS['text']}}}h":
        level = element.get(f"{{{ODT_NS['text']}}}outline-level", "1")
        try:
            level = str(min(max(int(level), 1), 6))
        except ValueError:
            level = "1"
        return f"{'#' * int(level)} {text}"
    if element.tag == f"{{{ODT_NS['text']}}}list-item":
        return f"- {text}"
    return text


def _odt_table(table: ElementTree.Element) -> str:
    rows: list[list[str]] = []
    cell_tags = {
        f"{{{ODT_NS['table']}}}table-cell",
        f"{{{ODT_NS['table']}}}covered-table-cell",
    }
    paragraph_tags = {
        f"{{{ODT_NS['text']}}}p",
        f"{{{ODT_NS['text']}}}h",
    }
    for row in table.iter(f"{{{ODT_NS['table']}}}table-row"):
        cells = []
        for cell in row:
            if cell.tag not in cell_tags:
                continue
            paragraphs = [
                "".join(paragraph.itertext()).strip()
                for paragraph in cell
                if paragraph.tag in paragraph_tags
            ]
            content = "<br>".join(part for part in paragraphs if part)
            cells.append(content.replace("|", r"\|"))
        if cells:
            rows.append(cells)

    if not rows:
        return ""

    width = max(map(len, rows))
    rows = [row + [""] * (width - len(row)) for row in rows]
    return "\n".join(
        "| " + " | ".join(row) + " |"
        for row in [rows[0], ["---"] * width, *rows[1:]]
    )


def extract_odt(path: Path) -> str:
    try:
        with zipfile.ZipFile(path) as archive:
            with archive.open("content.xml") as content:
                root = ElementTree.parse(content).getroot()
    except KeyError as error:
        raise ConversionError("El ODT no contiene content.xml.") from error

    document_text = root.find(".//office:text", ODT_NS)
    if document_text is None:
        raise ConversionError("No se encontró el contenido principal del ODT.")

    blocks: list[str] = []
    for element in document_text:
        if element.tag in {
            f"{{{ODT_NS['text']}}}p",
            f"{{{ODT_NS['text']}}}h",
            f"{{{ODT_NS['text']}}}list",
        }:
            block = _odt_block(element)
            if block:
                blocks.append(block)
        elif element.tag == f"{{{ODT_NS['table']}}}table":
            block = _odt_table(element)
            if block:
                blocks.append(block)
    return "\n\n".join(blocks)


def extract_pdf(path: Path) -> str:
    try:
        from pypdf import PdfReader
        from pypdf.errors import PdfReadError
    except ImportError as error:
        raise ConversionError(
            "Para convertir PDF, instala las dependencias con "
            "'python -m pip install -r requirements.txt'."
        ) from error

    try:
        reader = PdfReader(path)
        if reader.is_encrypted:
            raise ConversionError("El PDF está cifrado y no se puede leer.")
        pages = [page.extract_text() or "" for page in reader.pages]
    except (OSError, ValueError, PdfReadError) as error:
        raise ConversionError(f"No se pudo leer el PDF: {error}") from error

    text = "\n\n".join(page.strip() for page in pages if page.strip())
    if not text:
        raise ConversionError(
            "El PDF no contiene texto extraíble; si es un escaneo, necesita OCR."
        )
    return text


class _MarkdownHTMLParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.ignored_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style"}:
            self.ignored_depth += 1
            return
        if self.ignored_depth:
            return
        heading = re.fullmatch(r"h([1-6])", tag)
        if heading:
            self.parts.append("\n\n" + "#" * int(heading.group(1)) + " ")
        elif tag == "li":
            self.parts.append("\n- ")
        elif tag in {"p", "div", "tr"}:
            self.parts.append("\n\n")
        elif tag == "br":
            self.parts.append("\n")
        elif tag in {"td", "th"}:
            self.parts.append(" | ")

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style"} and self.ignored_depth:
            self.ignored_depth -= 1
        elif not self.ignored_depth and tag in {
            "h1", "h2", "h3", "h4", "h5", "h6", "li", "p", "div", "tr"
        }:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self.ignored_depth:
            self.parts.append(data)


def extract_html(path: Path) -> str:
    parser = _MarkdownHTMLParser()
    parser.feed(path.read_text(encoding="utf-8-sig", errors="replace"))
    parser.close()
    return "".join(parser.parts)


def extract_rtf(path: Path) -> str:
    text = path.read_text(encoding="utf-8", errors="replace")
    text = re.sub(r"\\'[0-9a-fA-F]{2}", lambda match: bytes.fromhex(match[2:]).decode(
        "cp1252", errors="replace"
    ), text)
    text = re.sub(r"\\(par|line)\b", "\n", text)
    text = re.sub(r"\\tab\b", "\t", text)
    text = re.sub(r"\\[a-zA-Z]+-?\d* ?", "", text)
    text = re.sub(r"\\([\\{}])", r"\1", text)
    return text.replace("{", "").replace("}", "")


def convert_document(path: Path) -> str:
    extension = path.suffix.lower()
    if extension == ".pdf":
        text = extract_pdf(path)
    elif extension == ".docx":
        text = extract_docx(path)
    elif extension == ".odt":
        text = extract_odt(path)
    elif extension in {".html", ".htm"}:
        text = extract_html(path)
    elif extension == ".rtf":
        text = extract_rtf(path)
    elif extension in {".txt", ".md"}:
        text = path.read_text(encoding="utf-8-sig", errors="replace")
    else:
        raise ConversionError(f"Formato no compatible: {extension or '(sin extensión)'}")

    result = normalize_markdown(text)
    if not result:
        raise ConversionError("No se encontró texto para convertir.")
    return result + "\n"


def _destination_for(
    source: Path, input_path: Path, output_path: Path, is_directory: bool
) -> Path:
    if not is_directory and output_path.suffix.lower() == ".md":
        return output_path
    relative = source.relative_to(input_path) if is_directory else Path(source.name)
    return output_path / relative.with_suffix(".md")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Convierte PDF, DOCX y otros documentos a Markdown."
    )
    parser.add_argument(
        "input",
        nargs="?",
        type=Path,
        default=ROOT / "not_md",
        help="archivo o carpeta de entrada (por defecto: not_md)",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=ROOT / "md",
        help="archivo .md de salida o carpeta de destino (por defecto: md)",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="reemplaza los Markdown que ya existan",
    )
    return parser


@dataclass
class ConversionSummary:
    converted: int = 0
    skipped: int = 0
    failures: int = 0
    messages: list[tuple[str, bool]] = field(default_factory=list)

    @property
    def exit_code(self) -> int:
        return 1 if self.failures else 0


def convert_path(
    input_path: Path,
    output_path: Path,
    overwrite: bool = False,
    on_message: Callable[[str, bool], None] | None = None,
) -> ConversionSummary:
    """Convert supported files in a file or folder into Markdown."""
    input_path = input_path.expanduser().resolve()
    output_path = output_path.expanduser().resolve()
    summary = ConversionSummary()

    def report(message: str, is_error: bool = False) -> None:
        summary.messages.append((message, is_error))
        if on_message is not None:
            on_message(message, is_error)

    if not input_path.exists():
        report(f"No existe la entrada: {input_path}", True)
        summary.failures += 1
        return summary

    is_directory = input_path.is_dir()
    if is_directory:
        sources = sorted(
            path
            for path in input_path.rglob("*")
            if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS
        )
    elif input_path.is_file():
        sources = [input_path]
    else:
        report(f"La entrada no es un archivo ni una carpeta: {input_path}", True)
        summary.failures += 1
        return summary

    if not sources:
        report("No se encontraron archivos compatibles.", True)
        summary.failures += 1
        return summary

    for source in sources:
        target = _destination_for(source, input_path, output_path, is_directory)
        if source.resolve() == target.resolve():
            report(f"Omitido (origen y destino iguales): {source.name}")
            summary.skipped += 1
            continue
        if target.exists() and not overwrite:
            report(f"Omitido (ya existe; activa sobrescritura): {target}")
            summary.skipped += 1
            continue
        try:
            markdown = convert_document(source)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(markdown, encoding="utf-8")
        except (
            ConversionError,
            OSError,
            ValueError,
            zipfile.BadZipFile,
            ElementTree.ParseError,
        ) as error:
            report(f"Error al convertir {source.name}: {error}", True)
            summary.failures += 1
            continue
        report(f"Convertido: {source.name} -> {target}")
        summary.converted += 1

    report(
        f"Resultado: {summary.converted} convertido(s), "
        f"{summary.skipped} omitido(s), {summary.failures} error(es)."
    )
    return summary


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    summary = convert_path(
        args.input,
        args.output,
        overwrite=args.overwrite,
        on_message=lambda message, is_error: print(
            message, file=sys.stderr if is_error else sys.stdout
        ),
    )
    return summary.exit_code


if __name__ == "__main__":
    raise SystemExit(main())