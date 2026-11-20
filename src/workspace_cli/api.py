"""Signed-in Google API clients. Every request retries on rate limits and server errors."""
from __future__ import annotations

import random
import re
import time

from .auth import creds

RETRIES = 5  # googleapiclient backs off exponentially on 429, 5xx and dropped connections


class MaybeApplied(Exception):
    """A change was sent but the reply was lost: Google may or may not have applied it."""


def file_id(url_or_id: str) -> str:
    m = re.search(r"/d/([A-Za-z0-9_-]{20,})", url_or_id)
    return m.group(1) if m else url_or_id.strip()


def run(request):
    """For reads and for changes that are safe to repeat (overwriting the same cells)."""
    return request.execute(num_retries=RETRIES)


def run_once(request):
    """For changes that must not happen twice (append rows, add text, create, add tab).

    googleapiclient would also retry these after a 5xx or a dropped connection, when Google may
    already have applied them, so only a 429 (refused, nothing applied) is retried here."""
    from googleapiclient.errors import HttpError

    for attempt in range(RETRIES + 1):
        try:
            return request.execute(num_retries=0)
        except HttpError as e:
            if getattr(e.resp, "status", 0) == 429 and attempt < RETRIES:
                time.sleep(min(60, 2 ** attempt + random.random()))
                continue
            if getattr(e.resp, "status", 0) >= 500:
                raise MaybeApplied(f"Google answered with an error ({e.resp.status})") from e
            raise
        except (OSError, TimeoutError) as e:
            raise MaybeApplied(f"the connection dropped ({e})") from e


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
    """gspread client. (gspread's BackOffHTTPClient is documented as not production ready and
    retries "no access" errors for minutes, so the plain client is used: problems fail fast.)"""
    import gspread

    return gspread.authorize(creds())


def sheet(url_or_id: str):
    """Open a spreadsheet (gspread) by URL or id."""
    return gc().open_by_key(file_id(url_or_id))


def quote_tab(title: str) -> str:
    return "'" + title.replace("'", "''") + "'"
