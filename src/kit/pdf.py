"""`kit pdf`: read, take apart and put together PDF files (pypdf, pdfplumber, pypdfium2, Pillow)."""
from __future__ import annotations

import csv
import io
import re
import sys
from pathlib import Path

from workspace_cli.files import UserError

from .outputs import check_folder, safe_name, save, source, target

TEXT_LIMIT = 60_000  # characters printed by default, so one command cannot flood an agent's context
RENDER_LIMIT = 5     # page images made by default
TABLE_ROWS = 500     # table rows printed by default (-o saves them all)


def reader(path: Path):
    import pypdf
    from pypdf.errors import PdfReadError

    try:
        r = pypdf.PdfReader(path)
        if r.is_encrypted and not r.decrypt(""):  # many "protected" PDFs open with an empty password
            raise UserError(f"{path.name} is password-protected. Open it, enter the password, and save "
                            "or print it as a new PDF without a password; then use that copy.")
        len(r.pages)
        return r
    except PdfReadError as e:
        raise UserError(f"{path.name} is not a readable PDF ({e}).")


def page_list(spec: str | None, count: int) -> list[int]:
    """'1-3,5,8-' or 'last' -> 0-based page numbers, in the order given."""
    if not spec:
        return list(range(count))
    pages: list[int] = []
    for part in spec.replace(" ", "").lower().split(","):
        m = re.fullmatch(r"(\d+|last)?(-)?(\d+|last)?", part)
        if not part or not m or (m.group(1) is None and m.group(3) is None):
            raise UserError(f"Pages {spec!r}: use numbers like 1-3,5,8- (from 1 to {count}).")
        num = lambda x, default: count if x == "last" else int(x) if x else default  # noqa: E731
        start = num(m.group(1), 1)
        end = num(m.group(3), count) if m.group(2) else start
        if not (1 <= start <= count and 1 <= end <= count):
            raise UserError(f"Pages {spec!r}: this PDF has {count} pages.")
        step = 1 if end >= start else -1
        pages += [p - 1 for p in range(start, end + step, step)]
    return pages


def info(path_arg: str) -> None:
    path = source(path_arg, ".pdf")
    r = reader(path)
    box = r.pages[0].mediabox
    mm = lambda pt: round(float(pt) * 25.4 / 72)  # noqa: E731
    meta = r.metadata or {}
    print(f"{path.name}\n  pages: {len(r.pages)}\n  page size: {mm(box.width)} x {mm(box.height)} mm"
          f"\n  file size: {path.stat().st_size / 1024:,.0f} KB")
    for key in ("/Title", "/Author", "/Creator", "/Producer"):
        if meta.get(key):
            print(f"  {key[1:].lower()}: {meta[key]}")
    has_text = any(_page_text(path, i).strip() for i in range(min(3, len(r.pages))))
    print(f"  text layer: {'yes' if has_text else 'no (scanned?) - use kit pdf render to look at the pages'}")


def _page_text(path: Path, index: int) -> str:
    import pypdfium2 as pdfium

    doc = pdfium.PdfDocument(path)
    try:
        return doc[index].get_textpage().get_text_range()
    finally:
        doc.close()


def text(path_arg: str, pages: str | None, show_all: bool) -> None:
    import pypdfium2 as pdfium

    path = source(path_arg, ".pdf")
    reader(path)  # clear message for password-protected files
    doc = pdfium.PdfDocument(path)
    shown, total, cut = 0, 0, False
    try:
        for i in page_list(pages, len(doc)):
            t = doc[i].get_textpage().get_text_range().replace("\r\n", "\n").strip()
            total += len(t)
            block = f"--- page {i + 1} ---\n{t}\n"
            if not show_all and shown + len(block) > TEXT_LIMIT:
                cut = True
                break
            sys.stdout.write(block)
            shown += len(block)
    finally:
        doc.close()
    if cut:
        print(f"(stopped at {TEXT_LIMIT:,} characters; give --pages, or add --all)", file=sys.stderr)
    if total == 0:
        print("(no text found: this looks like a scanned PDF. Use `kit pdf render` to make page images "
              "and read those.)", file=sys.stderr)


def tables(path_arg: str, pages: str | None, out_arg: str | None) -> None:
    import pdfplumber

    path = source(path_arg, ".pdf")
    reader(path)
    found: list[tuple[str, list]] = []
    with pdfplumber.open(path) as pdf:
        for i in page_list(pages, len(pdf.pages)):
            for n, t in enumerate(pdf.pages[i].extract_tables(), 1):
                rows = [[(c or "").replace("\n", " ").strip() for c in row] for row in t]
                if any(any(c for c in row) for row in rows):
                    found.append((f"p{i + 1} table {n}", rows))
    if not found:
        print("No tables found (a table needs ruling lines or clear columns; scanned pages have none). "
              "Try `kit pdf text`.", file=sys.stderr)
        return
    if not out_arg:
        shown = 0
        for name, rows in found:
            if shown + len(rows) > TABLE_ROWS and shown:
                print(f"(stopped after {shown} rows; save every table with -o tables.xlsx)", file=sys.stderr)
                break
            print(f"--- {name} ---")
            csv.writer(sys.stdout, lineterminator="\n").writerows(rows[:TABLE_ROWS])
            shown += len(rows)
        return
    from .sheet import write_rows, write_xlsx

    out = target(path, out_arg, "xlsx")
    if out.suffix.lower() == ".xlsx":
        n = len(found)
        print(f"wrote {save(out, lambda tmp: write_xlsx(tmp, found))} ({n} table{'s, one per tab' if n > 1 else ''})")
    elif out.suffix.lower() == ".csv":
        if len(found) > 1:
            raise UserError(f"Found {len(found)} tables; save as .xlsx (one tab each) or pick --pages.")
        print(f"wrote {save(out, lambda tmp: write_rows(tmp, found[0][1]))}")
    else:
        raise UserError("Save tables as .xlsx or .csv.")


def _write(writer, tmp: Path) -> None:
    with open(tmp, "wb") as fh:
        writer.write(fh)


def merge(inputs: list[str], out_arg: str) -> None:
    import pypdf

    if len(inputs) < 2:
        raise UserError("Give at least two PDFs to merge.")
    paths = [source(p, ".pdf") for p in inputs]
    w = pypdf.PdfWriter()
    for p in paths:
        w.append(reader(p))
    out = target(paths[0], out_arg, "pdf")
    print(f"wrote {save(out, lambda tmp: _write(w, tmp))} ({len(w.pages)} pages)")


def pick(path_arg: str, pages: str, out_arg: str) -> None:
    import pypdf

    path = source(path_arg, ".pdf")
    r = reader(path)
    w = pypdf.PdfWriter()
    chosen = page_list(pages, len(r.pages))
    for i in chosen:
        w.add_page(r.pages[i])
    out = target(path, out_arg, "pdf")
    print(f"wrote {save(out, lambda tmp: _write(w, tmp))} ({len(chosen)} pages)")


def split(path_arg: str, every: int, out_dir: str | None) -> None:
    import pypdf

    if every < 1:
        raise UserError("--every must be 1 or more.")
    path = source(path_arg, ".pdf")
    r = reader(path)
    folder = check_folder(Path(out_dir) if out_dir else path.parent)
    n = len(r.pages)
    for start in range(0, n, every):
        end = min(start + every, n)
        w = pypdf.PdfWriter()
        for i in range(start, end):
            w.add_page(r.pages[i])
        label = f"p{start + 1}" if end - start == 1 else f"p{start + 1}-{end}"
        print(f"wrote {save(folder / f'{safe_name(path.stem)} {label}.pdf', lambda tmp: _write(w, tmp))}")


def rotate(path_arg: str, degrees: int, pages: str | None, out_arg: str | None) -> None:
    import pypdf

    if degrees % 90:
        raise UserError("Rotate by 90, 180 or 270 (or -90).")
    path = source(path_arg, ".pdf")
    r = reader(path)
    w = pypdf.PdfWriter(clone_from=r)
    chosen = page_list(pages, len(w.pages))
    for i in chosen:
        w.pages[i].rotate(degrees)
    out = target(path, out_arg, "pdf") if out_arg else path.with_name(f"{path.stem} rotated.pdf")
    print(f"wrote {save(out, lambda tmp: _write(w, tmp))} ({len(chosen)} pages turned {degrees}°)")


def compress(path_arg: str, quality: int, out_arg: str | None) -> None:
    import pypdf
    from PIL import Image

    if not 10 <= quality <= 95:
        raise UserError("--quality goes from 10 (smallest) to 95 (best).")
    path = source(path_arg, ".pdf")
    r = reader(path)
    w = pypdf.PdfWriter(clone_from=r)
    for page in w.pages:
        for img in page.images:
            try:
                pic = img.image
                if pic.mode not in ("RGB", "L"):
                    continue  # transparency, CMYK, 1-bit scans: left as they are
                if max(pic.size) > 2000:  # beyond print quality for a page
                    pic.thumbnail((2000, 2000), Image.Resampling.LANCZOS)
                img.replace(pic, quality=quality)
            except Exception:
                continue  # an image pypdf cannot re-encode stays untouched
        page.compress_content_streams()
    w.compress_identical_objects(remove_duplicates=True, remove_unreferenced=True)
    buf = io.BytesIO()
    w.write(buf)
    before, after = path.stat().st_size, buf.tell()
    if after > before * 0.95:
        print(f"{path.name} is already compact ({before / 1024:,.0f} KB); no smaller copy made.")
        return
    out = target(path, out_arg, "pdf") if out_arg else path.with_name(f"{path.stem} small.pdf")
    final = save(out, lambda tmp: tmp.write_bytes(buf.getvalue()))
    print(f"wrote {final} ({before / 1024:,.0f} KB -> {after / 1024:,.0f} KB)")


def render(path_arg: str, pages: str | None, dpi: int, out_dir: str | None) -> None:
    import pypdfium2 as pdfium

    if not 50 <= dpi <= 300:
        raise UserError("--dpi goes from 50 to 300 (150 is plenty to read a page).")
    path = source(path_arg, ".pdf")
    reader(path)
    folder = check_folder(Path(out_dir) if out_dir else path.parent)
    doc = pdfium.PdfDocument(path)
    try:
        chosen = page_list(pages, len(doc))
        if pages is None and len(chosen) > RENDER_LIMIT:
            print(f"(first {RENDER_LIMIT} of {len(chosen)} pages; give --pages for others)", file=sys.stderr)
            chosen = chosen[:RENDER_LIMIT]
        for i in chosen:
            pic = doc[i].render(scale=dpi / 72).to_pil()
            print(f"wrote {save(folder / f'{path.stem} p{i + 1}.png', lambda tmp: pic.save(tmp, 'PNG'))}")
    finally:
        doc.close()


def from_images(inputs: list[str], out_arg: str) -> None:
    from PIL import Image, ImageOps, UnidentifiedImageError

    paths = [source(p) for p in inputs]
    pics = []
    for p in paths:
        try:
            pic = ImageOps.exif_transpose(Image.open(p))  # phone photos: upright, as they were taken
        except UnidentifiedImageError:
            hint = " (iPhone HEIC: share it as JPEG, or set Camera > Formats > Most Compatible)" \
                if p.suffix.lower() in (".heic", ".heif") else ""
            raise UserError(f"{p.name} is not an image kit can read{hint}.")
        pics.append(pic.convert("RGB"))
    out = target(paths[0], out_arg, "pdf")
    final = save(out, lambda tmp: pics[0].save(tmp, "PDF", save_all=True, append_images=pics[1:], resolution=150))
    print(f"wrote {final} ({len(pics)} pages)")
