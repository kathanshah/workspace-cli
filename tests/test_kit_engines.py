"""kit convert with the real pandoc and Typst. Runs when KIT_TEST_TOOLS names a folder holding them
(scripts/release.sh sets it up); skipped otherwise, so plain `uv run pytest` stays offline."""
import os
import zipfile

import pytest

from kit import cli, engines

TOOLS = os.environ.get("KIT_TEST_TOOLS")
pytestmark = pytest.mark.skipif(not TOOLS or not all(
    (__import__("pathlib").Path(TOOLS) / f"{n}-{v}").is_dir() for n, v in engines.VERSIONS.items()),
    reason="set KIT_TEST_TOOLS to a folder with kit's engines (kit setup)")


@pytest.fixture(autouse=True)
def tools(tmp_path, monkeypatch):
    monkeypatch.setenv("KIT_TOOLS", TOOLS or "")
    monkeypatch.chdir(tmp_path)


def run(*args):
    with pytest.raises(SystemExit) as e:
        cli.main(list(args))
    return e.value.code


def test_long_tables_break_across_pages(tmp_path):
    import pypdf

    rows = "\n".join(f"| item {i} | ₹{i * 100} |" for i in range(100))
    (tmp_path / "t.md").write_text(f"# Price list\n\n| Item | Price |\n|---|--:|\n{rows}\n", encoding="utf-8")
    assert run("convert", "t.md", "pdf") == 0
    r = pypdf.PdfReader(tmp_path / "t.pdf")
    text = "".join(p.extract_text() for p in r.pages)
    assert len(r.pages) >= 3 and "item 99" in text
    last = r.pages[-1].extract_text()
    assert "item 99" in last and "item 0 " not in last  # rows flow on, not piled onto one page


def test_images_from_the_web_or_other_folders_are_left_out(tmp_path, capsys):
    (tmp_path / "secret.txt").write_text("private")
    doc = tmp_path / "docs"
    doc.mkdir()
    (doc / "n.md").write_text(f"![](http://127.0.0.1:9/leak?d=1)\n\n![]({tmp_path / 'secret.txt'})\n\n![](../secret.txt)\n",
                              encoding="utf-8")
    assert run("convert", "docs/n.md", "docx") == 0
    with zipfile.ZipFile(doc / "n.docx") as z:
        assert not [n for n in z.namelist() if n.startswith("word/media/")]
    assert "left out 3 image" in capsys.readouterr().err


def test_word_images_never_overwrite_an_earlier_media_folder(tmp_path):
    from PIL import Image

    for colour in ("red", "blue"):
        Image.new("RGB", (10, 10), colour).save(tmp_path / "pic.png")
        (tmp_path / "brief.md").write_text("![](pic.png)\n", encoding="utf-8")
        assert run("convert", "brief.md", f"{colour}.docx") == 0
    assert run("convert", "red.docx", "out.md") == 0
    first = sorted((tmp_path / "out-media").rglob("*.png"))
    before = first[0].read_bytes()
    assert run("convert", "blue.docx", "out.md") == 0
    assert first[0].read_bytes() == before  # the second conversion is "out (1).md" with "out (1)-media"
    assert (tmp_path / "out (1)-media").is_dir()
    assert "![](" in (tmp_path / "out (1).md").read_text(encoding="utf-8")  # Markdown image, not <img>
