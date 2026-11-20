"""`kit web`: read a page as clean Markdown, download a file, search the web (no API keys)."""
from __future__ import annotations

import re
import sys
import tempfile
import time
import warnings
from pathlib import Path
from urllib.parse import unquote, urlparse

from workspace_cli.files import UserError

from . import __version__
from .outputs import save

TEXT_LIMIT = 40_000
MAX_DOWNLOAD = 1024 ** 3     # 1 GB
MAX_PAGE = 50 * 1024 ** 2    # a page or PDF to read: 50 MB
HEADERS = {"User-Agent": f"Mozilla/5.0 (compatible; kit/{__version__}; +https://github.com/kathanshah/workspace-cli)",
           "Accept-Language": "en-IN,en;q=0.9"}


ADS = re.compile(r"bing\.com/aclick|duckduckgo\.com/y\.js|googleadservices|/aclk\?", re.I)


class NetworkProblem(Exception):
    """Cannot reach the site or service; cli maps it to exit 5."""


def _url(url: str) -> str:
    url = url.strip()
    if not re.match(r"https?://", url, re.I):
        if re.match(r"[\w.-]+\.[a-z]{2,}(/|$)", url, re.I):
            url = "https://" + url
        else:
            raise UserError(f"{url!r} is not a web address (https://...).")
    return url


def _get(url: str, stream: bool = False):
    import requests

    try:
        r = requests.get(url, headers=HEADERS, timeout=(10, 30), stream=stream, allow_redirects=True)
    except requests.RequestException as e:
        raise NetworkProblem(f"Could not reach {urlparse(url).netloc}: {e}") from e
    if r.status_code in (401, 403):
        raise UserError(f"{urlparse(url).netloc} refused (HTTP {r.status_code}): it needs a login or blocks tools. "
                        "Open it in a browser instead.")
    if r.status_code == 404:
        raise UserError(f"Not found (HTTP 404): {url}")
    if r.status_code >= 400:
        raise NetworkProblem(f"{urlparse(url).netloc} answered HTTP {r.status_code}; try again later.")
    return r


def _limit(text: str, show_all: bool) -> str:
    if show_all or len(text) <= TEXT_LIMIT:
        return text
    print(f"(stopped at {TEXT_LIMIT:,} of {len(text):,} characters; add --all for everything)", file=sys.stderr)
    return text[:TEXT_LIMIT]


def read(url: str, show_all: bool) -> None:
    import trafilatura

    url = _url(url)
    r = _get(url, stream=True)
    kind = r.headers.get("content-type", "").split(";")[0].strip().lower()
    readable = (not kind or "html" in kind or kind.startswith("text/") or kind in
                ("application/pdf", "application/json", "application/xml", "application/xhtml+xml"))
    if not readable:
        r.close()
        raise UserError(f"That address is a {kind} file, not a page. Save it with `kit web get {url}`.")
    body = bytearray()
    for chunk in r.iter_content(1024 * 256):
        body += chunk
        if len(body) > MAX_PAGE:
            r.close()
            raise UserError("That page is over 50 MB; save it with `kit web get` instead.")
    body = bytes(body)
    if kind == "application/pdf" or body[:5] == b"%PDF-":
        from . import pdf

        with tempfile.TemporaryDirectory(prefix="kit-") as d:
            f = Path(d) / "page.pdf"
            f.write_bytes(body)
            print(f"# PDF: {r.url}\n")
            pdf.text(str(f), None, show_all)
        return
    if "html" not in kind and "xml" not in kind and kind:
        # Plain text without a declared charset is decoded as UTF-8, not requests' Latin-1 guess.
        enc = r.encoding if "charset" in r.headers.get("content-type", "").lower() else "utf-8"
        print(_limit(body.decode(enc or "utf-8", errors="replace"), show_all))
        return
    # Bytes, not r.text: trafilatura reads the page's own <meta charset> (₹ and Hindi stay intact).
    text = trafilatura.extract(body, url=r.url, output_format="markdown", include_tables=True,
                               include_links=True, include_images=False, favor_recall=True)
    if not text:
        text = trafilatura.html2txt(body) or ""
    meta = trafilatura.extract_metadata(body, default_url=r.url)
    title = (meta.title if meta and meta.title else "").strip()
    head = f"# {title}\n" if title else ""
    print(f"{head}Source: {r.url}\n")
    print(_limit(text.strip(), show_all) or "(this page has no readable text; it may need JavaScript)")


def _filename(r, url: str) -> str:
    cd = r.headers.get("content-disposition", "")
    m = re.search(r"filename\*=UTF-8''([^;]+)", cd, re.I) or re.search(r'filename="?([^";]+)"?', cd, re.I)
    name = unquote(m.group(1)) if m else unquote(Path(urlparse(r.url or url).path).name)
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name).strip(" .")
    if not name:
        name = "download"
    if "." not in name:
        kind = r.headers.get("content-type", "").split(";")[0].strip().lower()
        ext = {"application/pdf": ".pdf", "text/html": ".html", "text/csv": ".csv", "application/json": ".json",
               "image/jpeg": ".jpg", "image/png": ".png"}.get(kind, "")
        name += ext
    return name


def get(url: str, out: str | None) -> None:
    url = _url(url)
    r = _get(url, stream=True)
    size = int(r.headers.get("content-length") or 0)
    if size > MAX_DOWNLOAD:
        raise UserError(f"That file is {size / 1024 ** 2:,.0f} MB; kit downloads up to 1 GB.")
    if out:
        dest = Path(out).expanduser()
        if dest.is_dir():
            dest = dest / _filename(r, url)
        elif out.endswith(("/", "\\")) or not dest.suffix:
            raise UserError(f"Folder {dest} does not exist (to name the file, give it an extension).")
    else:
        dest = Path.cwd() / _filename(r, url)

    def write(tmp: Path) -> None:
        got = 0
        with open(tmp, "wb") as fh:
            for chunk in r.iter_content(1024 * 256):
                got += len(chunk)
                if got > MAX_DOWNLOAD:
                    raise UserError("The download passed 1 GB; stopped.")
                fh.write(chunk)

    import requests

    try:
        final = save(dest, write)
    except requests.RequestException as e:
        raise NetworkProblem(f"The download broke off: {e}") from e
    print(f"wrote {final} ({final.stat().st_size / 1024:,.0f} KB)")


def search(query: str, limit: int) -> None:
    """Free web search through the ddgs library: best effort, no key, can be refused at times."""
    warnings.filterwarnings("ignore")
    from ddgs import DDGS

    last = None
    for attempt in range(2):
        try:
            results = DDGS(timeout=10).text(query, region="in-en", max_results=max(1, min(limit, 25)) + 3)
            results = [x for x in results if not ADS.search(x.get("href", ""))][:limit]  # sponsored links
            if results:
                for n, x in enumerate(results, 1):
                    print(f"{n}. {x.get('title', '').strip()}\n   {x.get('href', '')}\n   {x.get('body', '').strip()}\n")
                return
        except Exception as e:  # the services behind ddgs refuse or time out now and then
            last = e
        time.sleep(2)
    raise NetworkProblem("Web search is not available right now (the free search services refused"
                         + (f": {last}" if last else "") + "). Try again in a minute, or use your own web search tool.")
