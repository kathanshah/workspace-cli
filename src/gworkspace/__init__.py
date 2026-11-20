"""Signed-in Google Sheets / Docs / Drive clients for scripts run with `gpy`.

    from gworkspace import sheet, gc, drive, docs, sheets_api

    sh = sheet("https://docs.google.com/spreadsheets/d/<id>/edit")   # gspread Spreadsheet
    rows = sh.worksheet("Sheet1").get_all_records()                 # list of dicts
    from gspread_dataframe import get_as_dataframe, set_with_dataframe
"""
from workspace_cli.api import docs, drive, file_id, gc, run, sheet, sheets_api
from workspace_cli.auth import creds

__all__ = ["creds", "docs", "drive", "file_id", "gc", "run", "sheet", "sheets_api"]
