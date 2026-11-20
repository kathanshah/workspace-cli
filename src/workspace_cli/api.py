"""Signed-in Google API clients. Every request retries on rate limits and server errors."""
from __future__ import annotations

import re

from .auth import creds

RETRIES = 5  # googleapiclient backs off exponentially on 429 and 5xx


def file_id(url_or_id: str) -> str:
    m = re.search(r"/d/([A-Za-z0-9_-]{20,})", url_or_id)
    return m.group(1) if m else url_or_id.strip()


def run(request):
    return request.execute(num_retries=RETRIES)


def _build(name: str, version: str):
    from googleapiclient.discovery import build

    return build(name, version, credentials=creds(), cache_discovery=False)


def sheets_api():
    return _build("sheets", "v4")


def drive():
    return _build("drive", "v3")


def docs():
    return _build("docs", "v1")


def gc():
    """gspread client that backs off on rate limits."""
    import gspread
    from gspread.http_client import BackOffHTTPClient

    return gspread.authorize(creds(), http_client=BackOffHTTPClient)


def sheet(url_or_id: str):
    """Open a spreadsheet (gspread) by URL or id."""
    return gc().open_by_key(file_id(url_or_id))


def quote_tab(title: str) -> str:
    return "'" + title.replace("'", "''") + "'"
