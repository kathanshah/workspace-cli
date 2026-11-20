"""kit: everyday file and web tools. Run `kit guide` for the full guide.

Documents
  kit convert <file> <out-file | format> [--toc]
        md, docx, html, odt, rtf, epub, txt  ->  pdf, docx, html, md, odt, rtf, txt, epub, pptx
        e.g.  kit convert quote.md pdf      kit convert brief.docx md     kit convert notes.md out.docx

PDFs
  kit pdf info    <file.pdf>
  kit pdf text    <file.pdf> [--pages 1-3] [--all]
  kit pdf tables  <file.pdf> [--pages 2] [-o tables.xlsx | table.csv]
  kit pdf render  <file.pdf> [--pages 1] [--dpi 150] [-o folder]    page images (for scans)
  kit pdf merge   <a.pdf> <b.pdf> ... -o <out.pdf>
  kit pdf pick    <file.pdf> <pages> -o <out.pdf>                   keep/reorder pages: 1-3,5,last
  kit pdf split   <file.pdf> [--every N] [-o folder]
  kit pdf rotate  <file.pdf> <90|180|270> [--pages 2] [-o out.pdf]
  kit pdf compress <file.pdf> [--quality 70] [-o out.pdf]
  kit pdf from-images <a.jpg> <b.png> ... -o <out.pdf>

Spreadsheets (.xlsx .xls .csv .tsv)
  kit sheet tabs    <file>
  kit sheet read    <file> [--tab "Name"] [--all]                  prints CSV (first 500 rows)
  kit sheet convert <file> <out-file | csv | xlsx> [--tab "Name"] [--all-tabs] [--text]
  kit sheet combine <a> <b> ... -o <out.xlsx> [--stack]

Web
  kit web read   <url> [--all]               the page's main text as Markdown (also PDFs)
  kit web get    <url> [-o file-or-folder]   download a file
  kit web search "<words>" [--limit 8]       free web search, best effort

Setup
  kit setup    download the document engines (pandoc, Typst); the installer does this
  kit guide    how to use kit, and the rules for AI agents

kit never overwrites a file: if the output name is taken it writes "name (1).ext" and says so.
"""
from __future__ import annotations

import argparse
import os
import sys
import warnings
from importlib import resources

from workspace_cli.files import UserError, utf8_stdio

from . import __version__

EXIT_FAIL, EXIT_NETWORK = 1, 5


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="kit", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--version", action="version", version=f"kit {__version__}")
    sub = p.add_subparsers(dest="cmd", required=True, metavar="<command>")
    sub.add_parser("setup")
    sub.add_parser("guide")

    c = sub.add_parser("convert")
    c.add_argument("file")
    c.add_argument("out", nargs="?", help="output file, or just a format like pdf")
    c.add_argument("--toc", action="store_true", help="add a table of contents")

    pdf = sub.add_parser("pdf").add_subparsers(dest="action", required=True, metavar="<action>")
    a = pdf.add_parser("info"); a.add_argument("file")
    a = pdf.add_parser("text"); a.add_argument("file"); a.add_argument("--pages"); a.add_argument("--all", action="store_true")
    a = pdf.add_parser("tables"); a.add_argument("file"); a.add_argument("--pages"); a.add_argument("-o", "--out")
    a = pdf.add_parser("render"); a.add_argument("file"); a.add_argument("--pages")
    a.add_argument("--dpi", type=int, default=150); a.add_argument("-o", "--out")
    a = pdf.add_parser("merge"); a.add_argument("files", nargs="+"); a.add_argument("-o", "--out", required=True)
    a = pdf.add_parser("pick"); a.add_argument("file"); a.add_argument("pages"); a.add_argument("-o", "--out", required=True)
    a = pdf.add_parser("split"); a.add_argument("file"); a.add_argument("--every", type=int, default=1); a.add_argument("-o", "--out")
    a = pdf.add_parser("rotate"); a.add_argument("file"); a.add_argument("degrees", type=int)
    a.add_argument("--pages"); a.add_argument("-o", "--out")
    a = pdf.add_parser("compress"); a.add_argument("file"); a.add_argument("--quality", type=int, default=70)
    a.add_argument("-o", "--out")
    a = pdf.add_parser("from-images"); a.add_argument("files", nargs="+"); a.add_argument("-o", "--out", required=True)

    sh = sub.add_parser("sheet").add_subparsers(dest="action", required=True, metavar="<action>")
    a = sh.add_parser("tabs"); a.add_argument("file")
    a = sh.add_parser("read"); a.add_argument("file"); a.add_argument("--tab"); a.add_argument("--all", action="store_true")
    a = sh.add_parser("convert"); a.add_argument("file"); a.add_argument("out"); a.add_argument("--tab")
    a.add_argument("--all-tabs", action="store_true", help="each tab to its own .csv")
    a.add_argument("--text", action="store_true", help="keep every value as text in .xlsx (no numbers)")
    a = sh.add_parser("combine"); a.add_argument("files", nargs="+"); a.add_argument("-o", "--out", required=True)
    a.add_argument("--stack", action="store_true", help="one table: rows of all files under one heading row")

    web = sub.add_parser("web").add_subparsers(dest="action", required=True, metavar="<action>")
    a = web.add_parser("read"); a.add_argument("url"); a.add_argument("--all", action="store_true")
    a = web.add_parser("get"); a.add_argument("url"); a.add_argument("-o", "--out")
    a = web.add_parser("search"); a.add_argument("query"); a.add_argument("--limit", type=int, default=8)
    return p


def run(a) -> int:
    if a.cmd == "setup":
        from .engines import setup
        return setup()
    if a.cmd == "guide":
        print(resources.files("kit").joinpath("guide.md").read_text(encoding="utf-8"))
    elif a.cmd == "convert":
        from .convert import convert
        convert(a.file, a.out, a.toc)
    elif a.cmd == "pdf":
        from . import pdf
        {"info": lambda: pdf.info(a.file),
         "text": lambda: pdf.text(a.file, a.pages, a.all),
         "tables": lambda: pdf.tables(a.file, a.pages, a.out),
         "render": lambda: pdf.render(a.file, a.pages, a.dpi, a.out),
         "merge": lambda: pdf.merge(a.files, a.out),
         "pick": lambda: pdf.pick(a.file, a.pages, a.out),
         "split": lambda: pdf.split(a.file, a.every, a.out),
         "rotate": lambda: pdf.rotate(a.file, a.degrees, a.pages, a.out),
         "compress": lambda: pdf.compress(a.file, a.quality, a.out),
         "from-images": lambda: pdf.from_images(a.files, a.out)}[a.action]()
    elif a.cmd == "sheet":
        from . import sheet
        {"tabs": lambda: sheet.tabs(a.file),
         "read": lambda: sheet.read(a.file, a.tab, a.all),
         "convert": lambda: sheet.convert(a.file, a.out, a.tab, a.all_tabs, a.text),
         "combine": lambda: sheet.combine(a.files, a.out, a.stack)}[a.action]()
    elif a.cmd == "web":
        from . import web
        {"read": lambda: web.read(a.url, a.all),
         "get": lambda: web.get(a.url, a.out),
         "search": lambda: web.search(a.query, a.limit)}[a.action]()
    return 0


def main(argv: list[str] | None = None) -> None:
    utf8_stdio()
    warnings.simplefilter("ignore")  # library notices (e.g. urllib3's SOCKS hint) are noise for agents
    a = parser().parse_args(argv)
    from .engines import DownloadFailed
    from .web import NetworkProblem

    try:
        code = run(a)
    except UserError as e:
        print(str(e), file=sys.stderr)
        code = EXIT_FAIL
    except (NetworkProblem, DownloadFailed) as e:
        print(str(e), file=sys.stderr)
        code = EXIT_NETWORK
    except PermissionError as e:
        print(f"Local file {e.filename2 or e.filename} cannot be written or read (open in another program? "
              "close it and retry).", file=sys.stderr)
        code = EXIT_FAIL
    except (FileNotFoundError, IsADirectoryError, NotADirectoryError) as e:
        print(f"Local file {e.filename2 or e.filename}: {e.strerror}.", file=sys.stderr)
        code = EXIT_FAIL
    except KeyboardInterrupt:
        code = 130
    except BrokenPipeError:  # `kit pdf text f.pdf | head`: the reader stopped early, which is fine
        os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())
        code = 0
    except OSError as e:  # disk full, a name Windows refuses, a network drive gone
        print(f"Could not read or write a file: {e}", file=sys.stderr)
        code = EXIT_FAIL
    except Exception as e:  # a file kit's libraries cannot handle: a clear line, not a traceback
        print(f"kit could not process this ({type(e).__name__}: {e}). If it keeps happening, "
              "send this message and the command to Kathan.", file=sys.stderr)
        code = EXIT_FAIL
    sys.exit(code)
