"""`kit convert`: documents between Markdown, Word, HTML, PDF and friends, with pandoc.

PDF is made in two steps, Markdown -> Typst -> PDF, in a private work folder: pandoc copies every
image the document uses into that folder, so Typst (which reads only inside its root folder) finds
them all.

kit convert runs without an approval prompt in Claude Code, so it must not reach anything the user
did not hand it: safe-media.lua drops images from the web or outside the document's folder, and
readers with include directives (LaTeX, reST, Org) are not offered.
"""
from __future__ import annotations

import subprocess
import sys
import tempfile
from importlib import resources
from pathlib import Path

from workspace_cli.files import UserError

from . import engines
from .outputs import free_name, save, source, target

# Pandoc reader per input extension. Markdown as AI agents write it: GitHub tables, bare links,
# and a lone image stays an image (no numbered "Figure 1" caption).
# Plain .txt keeps its line breaks (addresses, lists typed without Markdown).
READERS = {".md": "markdown", ".markdown": "markdown", ".txt": "markdown", ".docx": "docx", ".odt": "odt",
           ".rtf": "rtf", ".html": "html", ".htm": "html", ".epub": "epub", ".ipynb": "ipynb", ".csv": "csv",
           ".tsv": "tsv"}
MD_EXT = "-implicit_figures+autolink_bare_uris"
# gfm-raw_html: images as ![](...) (raw <img> tags would be lost on the way to PDF).
WRITERS = {".pdf": None, ".docx": "docx", ".html": "html", ".md": "gfm-raw_html", ".odt": "odt", ".rtf": "rtf",
           ".txt": "plain", ".epub": "epub", ".pptx": "pptx"}
NOT_HERE = {".pdf": "PDF files are read with `kit pdf text` (or `kit pdf tables`), not converted.",
            ".xlsx": "Spreadsheets: use `kit sheet`.", ".xls": "Spreadsheets: use `kit sheet`.",
            ".pptx": "pandoc cannot read PowerPoint files; it can only write them.",
            ".doc": "Old .doc files: open in Word and Save As .docx first.",
            ".pages": "Pages files: export to Word (.docx) first."}
# Fonts per OS: Arial for Latin text, then the system font that has Indian scripts and ₹.
FONTS = {"win32": ["Arial", "Nirmala UI", "Segoe UI Emoji"],
         "darwin": ["Arial", "Kohinoor Devanagari", "Kohinoor Gujarati", "Apple Color Emoji"]}


def _run(cmd: list, cwd: Path | None = None, what: str = "pandoc") -> None:
    try:
        p = subprocess.run([str(c) for c in cmd], cwd=cwd, capture_output=True)
    except OSError as e:
        raise UserError(f"Could not start {what} ({e}). On Windows 10 with an ARM processor kit cannot convert "
                        "documents (Windows 11 can); otherwise run `kit setup` and try again.")
    err = p.stderr.decode("utf-8", "replace")
    noise = ("unknown font family", "Could not fetch resource")
    shown = "\n".join(line for line in err.splitlines() if line.strip() and not any(n in line for n in noise))
    if p.returncode != 0:
        raise UserError(f"{what} could not convert this file:\n{shown or err}".rstrip())
    for line in err.splitlines():
        if line.startswith("kit: "):
            print(f"({line[5:]})", file=sys.stderr)
    if "Could not fetch resource" in err:
        print("(some images could not be loaded and were left out)", file=sys.stderr)


def convert(src_arg: str, out_arg: str | None, toc: bool = False) -> None:
    src = source(src_arg)
    ext_in = src.suffix.lower()
    if ext_in not in READERS:
        raise UserError(NOT_HERE.get(ext_in) or f"Cannot convert {src.name}: kit reads {', '.join(READERS)}.")
    if out_arg is None:
        raise UserError("Say what to make, e.g. `kit convert notes.md pdf` or `kit convert notes.md out.docx`.")
    ext_out = "." + out_arg.rsplit(".", 1)[-1].lower() if "." in out_arg else "." + out_arg.lower()
    if ext_out not in WRITERS:
        raise UserError(f"kit converts to {', '.join(WRITERS)}; not {ext_out}.")
    out = free_name(target(src, out_arg, ext_out))  # decided now: Word images go in "<this name>-media"
    if out.resolve() == src.resolve():
        raise UserError("The output would be the input file itself; give another name.")
    pandoc = engines.install("pandoc")
    reader = READERS[ext_in] + (MD_EXT if READERS[ext_in] == "markdown" else "")
    if ext_in == ".txt":
        reader += "+hard_line_breaks"
    with resources.as_file(resources.files("kit").joinpath("safe-media.lua")) as lua:
        guard = Path(lua).resolve()
    common = [pandoc, src.resolve(), "-f", reader, f"--resource-path={src.resolve().parent}", f"--lua-filter={guard}"]
    if toc:
        common.append("--toc")

    if ext_out == ".pdf":
        typst = engines.install("typst")

        def write(tmp: Path) -> None:
            with tempfile.TemporaryDirectory(prefix="kit-") as work:
                header = Path(work) / "kit-header.typ"
                style = Path(work) / "kit-style.yaml"
                fonts = ", ".join(f'"{f}"' for f in FONTS.get(sys.platform, ["Arial"]))
                header.write_text(f"#set text(font: ({fonts}))\n" +
                                  resources.files("kit").joinpath("pdf-header.typ").read_text(encoding="utf-8"),
                                  encoding="utf-8")
                style.write_text(resources.files("kit").joinpath("pdf-style.yaml").read_text(encoding="utf-8"),
                                 encoding="utf-8")
                _run(common + ["-t", "typst", "-s", "--extract-media=media", f"--metadata-file={style}",
                               f"--include-in-header={header}", "-o", "doc.typ"], cwd=Path(work))
                _run([typst, "compile", "--root", work, Path(work) / "doc.typ", tmp], what="Typst")
    else:
        writer = WRITERS[ext_out]
        extra = []
        if ext_out == ".html":
            extra = ["-s", "--embed-resources", f"--metadata=pagetitle:{src.stem}"]
        elif ext_out in (".docx", ".odt", ".epub", ".pptx", ".rtf"):
            extra = ["-s"]
        elif ext_out == ".md" and ext_in in (".docx", ".odt", ".epub", ".html", ".htm"):
            # Images inside a Word file go in a new folder next to the Markdown file (never an
            # existing one: pandoc's image names repeat, and it would overwrite them).
            extra = [f"--extract-media={free_name(out.resolve().parent / (out.stem + '-media')).name}"]

        def write(tmp: Path) -> None:
            # Run in the output folder, so extracted image links are relative to the new file.
            _run(common + ["-t", writer, *extra, "-o", tmp], cwd=out.resolve().parent)

    print(f"wrote {save(out, write)}")
