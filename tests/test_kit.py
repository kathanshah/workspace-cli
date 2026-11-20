"""Offline tests for kit: everything except the downloaded engines and the network."""
import csv
import io
import json

import pytest

from kit import cli, engines, outputs, pdf, sheet, web
from workspace_cli import agents


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("KIT_TOOLS", str(tmp_path / "tools"))
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "claude"))
    monkeypatch.chdir(tmp_path)
    return tmp_path


def run(*args):
    with pytest.raises(SystemExit) as e:
        cli.main(list(args))
    return e.value.code


def blank_pdf(path, pages=3):
    import pypdf

    w = pypdf.PdfWriter()
    for i in range(pages):
        w.add_blank_page(width=200 + i, height=300)
    with open(path, "wb") as fh:
        w.write(fh)
    return path


# outputs -------------------------------------------------------------------------------------

def test_never_overwrites(tmp_path):
    (tmp_path / "a.pdf").write_text("x")
    (tmp_path / "a (1).pdf").write_text("x")
    assert outputs.free_name(tmp_path / "a.pdf").name == "a (2).pdf"
    final = outputs.save(tmp_path / "a.pdf", lambda t: t.write_text("new"))
    assert final.name == "a (2).pdf" and (tmp_path / "a.pdf").read_text() == "x"
    assert not list(tmp_path.glob(".kit-*"))


def test_failed_write_leaves_nothing(tmp_path):
    def boom(t):
        t.write_text("half")
        raise RuntimeError("disk full")

    with pytest.raises(RuntimeError):
        outputs.save(tmp_path / "out.pdf", boom)
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("out, expected", [(None, "notes.pdf"), ("pdf", "notes.pdf"), (".pdf", "notes.pdf"),
                                           ("Quote.pdf", "Quote.pdf")])
def test_output_names(tmp_path, out, expected):
    assert outputs.target(tmp_path / "notes.md", out, "pdf").name == expected


def test_output_needs_extension_and_folder(tmp_path):
    with pytest.raises(outputs.UserError, match="extension"):
        outputs.target(tmp_path / "n.md", "report", "pdf")
    with pytest.raises(outputs.UserError, match="does not exist"):
        outputs.target(tmp_path / "n.md", str(tmp_path / "nope" / "r.pdf"), "pdf")


# pdf -----------------------------------------------------------------------------------------

@pytest.mark.parametrize("spec, expected", [("1-3", [0, 1, 2]), ("2,1", [1, 0]), ("4-", [3, 4]), ("last", [4]),
                                            ("3-1", [2, 1, 0]), (None, [0, 1, 2, 3, 4]), ("1, 5", [0, 4])])
def test_page_lists(spec, expected):
    assert pdf.page_list(spec, 5) == expected


@pytest.mark.parametrize("spec", ["0", "6", "a", "1-9", "-", ""])
def test_bad_page_lists(spec):
    with pytest.raises(outputs.UserError):
        pdf.page_list(spec or ",", 5)


def test_merge_pick_split_rotate(tmp_path):
    import pypdf

    blank_pdf(tmp_path / "a.pdf", 3)
    blank_pdf(tmp_path / "b.pdf", 2)
    assert run("pdf", "merge", "a.pdf", "b.pdf", "-o", "all.pdf") == 0
    assert len(pypdf.PdfReader(tmp_path / "all.pdf").pages) == 5
    assert run("pdf", "pick", "all.pdf", "last,1", "-o", "two.pdf") == 0
    widths = [float(p.mediabox.width) for p in pypdf.PdfReader(tmp_path / "two.pdf").pages]
    assert widths == [201, 200]  # b's second page, then a's first
    assert run("pdf", "split", "a.pdf", "--every", "2") == 0
    assert sorted(p.name for p in tmp_path.glob("a p*.pdf")) == ["a p1-2.pdf", "a p3.pdf"]
    assert run("pdf", "rotate", "a.pdf", "90", "--pages", "2") == 0
    assert [p.rotation for p in pypdf.PdfReader(tmp_path / "a rotated.pdf").pages] == [0, 90, 0]
    assert run("pdf", "rotate", "a.pdf", "45") == 1


def test_password_protected_pdf_is_a_clear_error(tmp_path, capsys):
    import pypdf

    w = pypdf.PdfWriter()
    w.add_blank_page(width=100, height=100)
    w.encrypt("secret")
    with open(tmp_path / "locked.pdf", "wb") as fh:
        w.write(fh)
    assert run("pdf", "text", "locked.pdf") == 1
    assert "password-protected" in capsys.readouterr().err


def test_scanned_pdf_says_so(tmp_path, capsys):
    blank_pdf(tmp_path / "scan.pdf", 1)
    assert run("pdf", "text", "scan.pdf") == 0
    assert "kit pdf render" in capsys.readouterr().err


def test_not_a_pdf(tmp_path, capsys):
    (tmp_path / "x.pdf").write_text("hello")
    assert run("pdf", "info", "x.pdf") == 1


def test_images_to_pdf_and_render(tmp_path):
    from PIL import Image

    Image.new("RGB", (40, 20), "red").save(tmp_path / "1.jpg")
    Image.new("RGBA", (20, 40), "blue").save(tmp_path / "2.png")
    assert run("pdf", "from-images", "1.jpg", "2.png", "-o", "pics.pdf") == 0
    assert run("pdf", "render", "pics.pdf", "--pages", "2", "--dpi", "72") == 0
    assert (tmp_path / "pics p2.png").exists()
    (tmp_path / "x.heic").write_bytes(b"not really")
    assert run("pdf", "from-images", "x.heic", "-o", "h.pdf") == 1


# sheet ---------------------------------------------------------------------------------------

def test_csv_to_xlsx_keeps_ids_text_and_formulas_inert(tmp_path):
    import openpyxl

    (tmp_path / "a.csv").write_text("Phone,Pin,Amount,Big,F\n+919876543210,00123,12.50,1234567890123456,=1+1\n",
                                    encoding="utf-8")
    assert run("sheet", "convert", "a.csv", "xlsx") == 0
    ws = openpyxl.load_workbook(tmp_path / "a.xlsx").active
    phone, pin, amount, big, f = (c for c in next(ws.iter_rows(min_row=2)))
    assert phone.value == "+919876543210" and pin.value == "00123" and big.value == "1234567890123456"
    assert amount.value == 12.5 and amount.number_format == "0.00"
    assert f.value == "=1+1" and f.data_type == "s"  # text, never a formula


def test_ansi_csv_is_read_with_a_note(tmp_path, capsys):
    (tmp_path / "old.csv").write_bytes("Name;City\ncafé;Pune\n".encode("cp1252"))
    assert run("sheet", "read", "old.csv") == 0
    out = capsys.readouterr()
    assert "café,Pune" in out.out and "CSV UTF-8" in out.err  # ';' was sniffed too


def test_written_csv_has_bom_for_excel(tmp_path):
    (tmp_path / "a.csv").write_text("₹,राम\n1,2\n", encoding="utf-8")
    (tmp_path / "b.csv").write_text("₹,राम\n3,4\n", encoding="utf-8")
    assert run("sheet", "combine", "a.csv", "b.csv", "-o", "all.csv", "--stack") == 0
    data = (tmp_path / "all.csv").read_bytes()
    assert data.startswith(b"\xef\xbb\xbf")
    assert list(csv.reader(io.StringIO(data.decode("utf-8-sig")))) == [["₹", "राम"], ["1", "2"], ["3", "4"]]


def test_xlsx_tabs_hidden_and_pick(tmp_path, capsys):
    import openpyxl

    wb = openpyxl.Workbook()
    wb.active.title = "Old"
    wb.active.sheet_state = "hidden"
    ws = wb.create_sheet("Nov 2026")
    ws.append(["a", 1.0, None])
    ws.append([None, None, None])  # trailing empty row and column are trimmed
    wb.save(tmp_path / "f.xlsx")
    assert run("sheet", "read", "f.xlsx") == 0
    assert capsys.readouterr().out == "a,1\n"  # first VISIBLE tab
    assert run("sheet", "read", "f.xlsx", "--tab", "'Nope'") == 1
    assert "Tabs: Old, Nov 2026" in capsys.readouterr().err
    assert run("sheet", "combine", "f.xlsx", "f.xlsx", "-o", "c.xlsx") == 0
    assert openpyxl.load_workbook(tmp_path / "c.xlsx").sheetnames == ["f - Old", "f - Nov 2026", "f - Old 2",
                                                                       "f - Nov 2026 2"]


def test_long_tab_names_are_cut_and_unique(tmp_path):
    import openpyxl

    tables = [("A very long tab name that goes past thirty-one", [["1"]])] * 2 + [("bad/name?", [["2"]])]
    sheet.write_xlsx(tmp_path / "t.xlsx", tables)
    names = openpyxl.load_workbook(tmp_path / "t.xlsx").sheetnames
    assert len(set(n.lower() for n in names)) == 3 and all(len(n) <= 31 for n in names) and "bad name" in names


# web, engines, agents -----------------------------------------------------------------------

class _Resp:
    def __init__(self, headers, url="https://x.test/files/report"):
        self.headers, self.url = headers, url


@pytest.mark.parametrize("headers, url, expected", [
    ({"content-disposition": 'attachment; filename="Q3 Report.pdf"'}, "https://x.test/d", "Q3 Report.pdf"),
    ({"content-disposition": "attachment; filename*=UTF-8''%E0%A4%B0%E0%A4%BE%E0%A4%AE.pdf"}, "https://x.test/d", "राम.pdf"),
    ({"content-type": "application/pdf"}, "https://x.test/files/report", "report.pdf"),
    ({}, "https://x.test/a%20b:c.xlsx", "a b_c.xlsx"),
    ({}, "https://x.test/", "download"),
])
def test_download_names(headers, url, expected):
    assert web._filename(_Resp(headers, url), url) == expected


def test_urls():
    assert web._url("example.com/page") == "https://example.com/page"
    with pytest.raises(outputs.UserError):
        web._url("not a url")


def test_every_machine_has_a_pinned_download():
    for name in engines.VERSIONS:
        for machine in ("mac-arm64", "mac-x64", "win-x64", "win-arm64"):
            url, sha = engines.DOWNLOADS[(name, machine)]
            assert url.startswith("https://github.com/") and len(sha) == 64


def test_damaged_download_is_refused(monkeypatch):
    import requests

    class R:
        content = b"tampered"
        def raise_for_status(self): pass

    monkeypatch.setattr(requests, "get", lambda *a, **k: R())
    with pytest.raises(engines.DownloadFailed, match="checksum"):
        engines._download("https://example.test/x.zip", "0" * 64)


def test_kit_skill_and_rules(isolated):
    assert agents.install_claude() == 0
    base = isolated / "claude"
    assert (base / "skills" / "kit" / "SKILL.md").exists()
    data = json.loads((base / "settings.json").read_text())
    assert "Bash(kit pdf *)" in data["permissions"]["allow"] and "PowerShell(kit sheet *)" in data["permissions"]["allow"]
    assert not any("kit web" in r for r in data["permissions"]["allow"] + data["permissions"]["ask"])
    assert agents.claude_rules_ok()
    assert agents.remove_claude() == 0
    data = json.loads((base / "settings.json").read_text())
    assert not any("kit" in r for r in data["permissions"]["allow"]) and not (base / "skills" / "kit").exists()


def test_guide_and_help_print():
    assert run("guide") == 0
    assert run("--version") == 0


# review fixes ----------------------------------------------------------------------------------

def test_xlsx_with_wrong_stored_size_reads_every_row(tmp_path, capsys):
    import zipfile

    import openpyxl

    wb = openpyxl.Workbook()
    for i in range(50):
        wb.active.append([f"r{i}", i])
    wb.save(tmp_path / "ok.xlsx")
    with zipfile.ZipFile(tmp_path / "ok.xlsx") as src, zipfile.ZipFile(tmp_path / "bad.xlsx", "w") as dst:
        for item in src.infolist():
            data = src.read(item)
            if item.filename == "xl/worksheets/sheet1.xml":
                data = data.replace(b'<dimension ref="A1:B50"/>', b'<dimension ref="A1"/>')
            dst.writestr(item, data)
    assert run("sheet", "read", "bad.xlsx") == 0
    assert len(capsys.readouterr().out.splitlines()) == 50


def test_bank_xls_that_is_really_html(tmp_path, capsys):
    (tmp_path / "statement.xls").write_text(
        "<html><body><table><tr><td>Date</td><td>Amount</td></tr><tr><td>01-11-2026</td><td>₹500</td></tr>"
        "</table></body></html>", encoding="utf-8")
    assert run("sheet", "read", "statement.xls") == 0
    out = capsys.readouterr()
    assert "01-11-2026,₹500" in out.out and "web page" in out.err


def test_mostly_utf8_csv_keeps_rupee(tmp_path, capsys):
    (tmp_path / "a.csv").write_bytes("Name,Amount\nराम,₹500\n".encode() + b"bad\xff,1\n")
    assert run("sheet", "read", "a.csv") == 0
    out = capsys.readouterr()
    assert "राम,₹500" in out.out and "damaged" in out.err


def test_tab_names_become_safe_file_names_and_control_chars_are_dropped(tmp_path):
    import openpyxl

    sheet.write_xlsx(tmp_path / "t.xlsx", [("Q1 - North", [["a\x0cb"]]), ("Rates draft", [["1"]])])
    wb = openpyxl.load_workbook(tmp_path / "t.xlsx")
    assert wb["Q1 - North"]["A1"].value == "ab"
    assert outputs.safe_name('tabs - Q1 | North "draft" <old>') == "tabs - Q1 _ North _draft_ _old_"


def test_never_writes_into_hidden_folders(tmp_path):
    (tmp_path / ".claude").mkdir()
    (tmp_path / "a.csv").write_text("x\n1\n", encoding="utf-8")
    assert run("sheet", "convert", "a.csv", str(tmp_path / ".claude" / "CLAUDE.xlsx")) == 1
    assert not list((tmp_path / ".claude").iterdir())


def test_publish_never_replaces_a_file_taken_meanwhile(tmp_path, monkeypatch):
    real = outputs.free_name
    calls = []

    def racing(path):  # the name is free when checked, then someone else takes it
        name = real(path)
        if not calls:
            name.write_text("theirs")
        calls.append(name)
        return name

    monkeypatch.setattr(outputs, "free_name", racing)
    final = outputs.save(tmp_path / "r.pdf", lambda t: t.write_text("mine"))
    assert (tmp_path / "r.pdf").read_text() == "theirs" and final.name == "r (1).pdf" and final.read_text() == "mine"


def test_render_asks_first(isolated):
    agents.install_claude()
    data = json.loads((isolated / "claude" / "settings.json").read_text())
    assert "Bash(kit pdf render *)" in data["permissions"]["ask"]


def test_web_page_charset_from_meta_tag(monkeypatch, capsys):
    import requests

    page = '<html><head><meta charset="utf-8"><title>Rates</title></head><body><article><p>Monthly rent ' \
           '₹1,200 per laptop for the whole team, किराया, delivered across Bangalore.</p></article></body></html>'

    class R:
        status_code, url = 200, "https://x.test/rates"
        headers = {"content-type": "text/html"}  # no charset: requests alone would guess Latin-1
        def iter_content(self, n): yield page.encode("utf-8")
        def close(self): pass

    monkeypatch.setattr(requests, "get", lambda *a, **k: R())
    assert run("web", "read", "https://x.test/rates") == 0
    assert "₹1,200" in capsys.readouterr().out


def test_unexpected_errors_are_one_line(monkeypatch, capsys):
    monkeypatch.setattr(pdf, "info", lambda f: (_ for _ in ()).throw(RuntimeError("boom")))
    assert run("pdf", "info", "x.pdf") == 1
    assert "boom" in capsys.readouterr().err
