"""Offline tests: everything that must work before anyone signs in, on every OS."""
import json
import os
import subprocess
import sys

import pytest

from workspace_cli import agents, api, auth, cli, files, ops


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("GSUITE_HOME", str(tmp_path / "gsuite"))
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "claude"))
    return tmp_path


def test_file_id_from_links_and_ids():
    fid = "1AbCdEfGhIjKlMnOpQrStUvWxYz0123456789"
    assert api.file_id(f"https://docs.google.com/spreadsheets/d/{fid}/edit#gid=0") == fid
    assert api.file_id(f"https://docs.google.com/document/d/{fid}/edit?usp=sharing") == fid
    assert api.file_id(f"  {fid} ") == fid


def test_quote_tab():
    assert api.quote_tab("Sales 2026") == "'Sales 2026'"
    assert api.quote_tab("Kathan's") == "'Kathan''s'"


def test_bundled_client_is_an_installed_app():
    cfg = auth.client_config()["installed"]
    assert cfg["client_id"].endswith(".apps.googleusercontent.com")
    assert cfg["client_secret"]


def test_not_signed_in_is_exit_3(capsys):
    with pytest.raises(SystemExit) as e:
        cli.main(["whoami"])
    assert e.value.code == cli.EXIT_SIGNIN
    assert "gsuite login" in capsys.readouterr().err


def test_damaged_token_is_sign_in_needed(isolated):
    auth.config_dir().mkdir(parents=True)
    auth.token_file().write_text("{not json")
    with pytest.raises(auth.SignInNeeded, match="damaged"):
        auth.creds()


def test_missing_scope_is_sign_in_needed(isolated):
    auth.config_dir().mkdir(parents=True)
    auth.token_file().write_text(json.dumps({
        "refresh_token": "r", "client_id": "c", "client_secret": "s", "token": "t",
        "scopes": auth.SCOPES[:-1], "expiry": "2999-01-01T00:00:00Z"}))
    with pytest.raises(auth.SignInNeeded, match="permission"):
        auth.creds()


def test_csv_input_utf8_bom_and_unicode(tmp_path):
    f = tmp_path / "rows.csv"
    f.write_bytes("﻿Name,Amount\nराम,\"₹5,000\"\n".encode("utf-8"))
    assert files.read_csv_arg(str(f)) == [["Name", "Amount"], ["राम", "₹5,000"]]


def test_csv_output_has_no_blank_lines(capsys):
    files.write_csv([["a", "₹1"], ["b", "2"]])
    assert capsys.readouterr().out == "a,₹1\nb,2\n"


def test_guide_and_help_print():
    assert "Rules for AI agents" in agents.guide_text()
    out = subprocess.run([sys.executable, "-m", "workspace_cli", "--help"], capture_output=True, text=True,
                         encoding="utf-8")
    assert out.returncode == 0 and "gsuite login" in out.stdout


def test_install_claude_writes_skill_and_merges_settings(isolated):
    settings = isolated / "claude" / "settings.json"
    settings.parent.mkdir(parents=True)
    settings.write_text(json.dumps({"model": "x", "permissions": {"allow": ["Bash(ls *)"]}}))
    assert agents.install_claude() == 0
    agents.install_claude()  # idempotent
    data = json.loads(settings.read_text())
    assert data["model"] == "x"
    allow, ask = data["permissions"]["allow"], data["permissions"]["ask"]
    assert allow[0] == "Bash(ls *)"
    assert "Bash(gsuite read *)" in allow and "PowerShell(gsuite read *)" in allow
    assert "Bash(gsuite write *)" in ask and "Bash(gpy *)" in ask
    assert len(allow) == len(set(allow)) and len(ask) == len(set(ask))
    assert not set(allow) & set(ask)
    assert (isolated / "claude" / "settings.json.before-gsuite").exists()
    skill = (isolated / "claude" / "skills" / "gsuite" / "SKILL.md").read_text(encoding="utf-8")
    assert skill.startswith("---\nname: gsuite\n") and "gsuite guide" in skill


def test_install_claude_leaves_broken_settings_alone(isolated, capsys):
    settings = isolated / "claude" / "settings.json"
    settings.parent.mkdir(parents=True)
    settings.write_text("{ // comment\n}")
    agents.install_claude()
    assert settings.read_text() == "{ // comment\n}"
    assert "not valid JSON" in capsys.readouterr().out


def test_write_commands_are_never_auto_allowed():
    allow, ask = agents.rules()
    for cmd in ("write", "append", "append-doc", "add-tab", "create"):
        assert f"Bash(gsuite {cmd} *)" in ask
        assert not any(rule.startswith(f"Bash(gsuite {cmd}") for rule in allow)


def test_export_asks_and_is_not_auto_allowed():
    allow, ask = agents.rules()
    assert "Bash(gsuite export *)" in ask and "PowerShell(gsuite export *)" in ask
    assert not any("export" in rule for rule in allow)


def test_settings_with_bom_is_merged(isolated):
    settings = isolated / "claude" / "settings.json"
    settings.parent.mkdir(parents=True)
    settings.write_bytes("﻿{\"model\": \"x\"}".encode("utf-8"))
    assert agents.install_claude() == 0
    assert agents.claude_rules_ok()


def test_broken_settings_fails_loudly(isolated):
    settings = isolated / "claude" / "settings.json"
    settings.parent.mkdir(parents=True)
    settings.write_text("[]")
    assert agents.install_claude() == 1
    assert not agents.claude_rules_ok()


def test_utf16_csv_from_powershell(tmp_path):
    f = tmp_path / "rows.csv"
    f.write_bytes("Name,Amount\r\nराम,5000\r\n".encode("utf-16"))
    assert files.read_csv_arg(str(f)) == [["Name", "Amount"], ["राम", "5000"]]


def test_ansi_csv_from_excel_is_a_clear_error(tmp_path, capsys):
    f = tmp_path / "rows.csv"
    f.write_bytes("Name\ncaf\xe9\n".encode("cp1252"))
    with pytest.raises(SystemExit) as e:
        cli.main(["write", "1AbCdEfGhIjKlMnOpQrStUvWxYz0123456789", "A1", str(f)])
    assert e.value.code == cli.EXIT_FAIL
    assert "CSV UTF-8" in capsys.readouterr().err


def test_missing_local_file_is_exit_1_not_network(capsys):
    with pytest.raises(SystemExit) as e:
        cli.main(["append-doc", "1AbCdEfGhIjKlMnOpQrStUvWxYz0123456789", "no-such-file.txt"])
    assert e.value.code == cli.EXIT_FAIL
    assert "does not exist" in capsys.readouterr().err


def test_logout_only_forgets_this_computer(isolated, monkeypatch):
    monkeypatch.setattr(auth, "revoke", lambda c: pytest.fail("logout must not revoke at Google"))
    auth.config_dir().mkdir(parents=True)
    auth.token_file().write_text("{}")
    assert auth.logout() is True
    assert not auth.token_file().exists()
    assert auth.logout() is False


def _saved_token():
    auth.config_dir().mkdir(parents=True)
    auth.token_file().write_text(json.dumps({
        "refresh_token": "r", "client_id": "c", "client_secret": "s", "token": "t",
        "scopes": auth.SCOPES, "expiry": "2000-01-01T00:00:00Z"}))


def test_dead_login_means_sign_in(isolated, monkeypatch):
    from google.auth.exceptions import RefreshError
    from google.oauth2.credentials import Credentials

    _saved_token()
    def boom(self, request):
        raise RefreshError("invalid_grant: Token has been expired or revoked.")
    monkeypatch.setattr(Credentials, "refresh", boom)
    with pytest.raises(auth.SignInNeeded, match="expired"):
        auth.creds()


def test_passing_google_error_is_not_sign_in(isolated, monkeypatch, capsys):
    from google.auth.exceptions import RefreshError
    from google.oauth2.credentials import Credentials

    _saved_token()
    def boom(self, request):
        raise RefreshError("internal_failure: backend error", retryable=True)
    monkeypatch.setattr(Credentials, "refresh", boom)
    with pytest.raises(SystemExit) as e:
        cli.main(["whoami"])
    assert e.value.code == cli.EXIT_NETWORK
    assert "Sign-in needed" not in capsys.readouterr().err


def test_failed_export_keeps_existing_file(isolated, monkeypatch, tmp_path):
    import googleapiclient.http

    out = tmp_path / "report.xlsx"
    out.write_bytes(b"previous copy")

    class FakeDrive:
        def files(self):
            return self
        def export_media(self, **kw):
            return object()

    class FailingDownload:
        def __init__(self, fh, req):
            fh.write(b"partial")
        def next_chunk(self, num_retries=0):
            raise ConnectionError("network dropped")

    monkeypatch.setattr(api, "drive", lambda: FakeDrive())
    monkeypatch.setattr(ops, "meta", lambda fid: {"id": fid, "name": "x", "mimeType": ops.MIME["sheet"]})
    monkeypatch.setattr(googleapiclient.http, "MediaIoBaseDownload", FailingDownload)
    with pytest.raises(SystemExit) as e:
        cli.main(["export", "1AbCdEfGhIjKlMnOpQrStUvWxYz0123456789", str(out)])
    assert e.value.code == cli.EXIT_NETWORK
    assert out.read_bytes() == b"previous copy"
    assert [p.name for p in tmp_path.iterdir() if p.name.startswith(".gsuite-")] == []


def test_upgrade_removes_stale_auto_approval(isolated):
    settings = isolated / "claude" / "settings.json"
    settings.parent.mkdir(parents=True)
    settings.write_text(json.dumps({"permissions": {"allow": ["Bash(ls *)", "Bash(gsuite export *)"]}}))
    agents.install_claude()
    allow = json.loads(settings.read_text())["permissions"]["allow"]
    assert "Bash(gsuite export *)" not in allow and "Bash(ls *)" in allow


def _gid_cli(monkeypatch, rng, gid=77):
    """Run `read` on a link with a stubbed Sheets API; return (exit code, range Google is asked for)."""
    asked = {}

    class Req:
        def __init__(self, result): self.result = result
        def execute(self, num_retries=0): return self.result

    class Sheets:
        def spreadsheets(self): return self
        def values(self): return self
        def get(self, spreadsheetId, fields=None, range=None, **kw):
            if range is not None:
                asked["range"] = range
                return Req({"values": []})
            return Req({"sheets": [{"properties": {"sheetId": 0, "title": "Hidden", "hidden": True}},
                                   {"properties": {"sheetId": 5, "title": "Sheet1"}},
                                   {"properties": {"sheetId": 77, "title": "Leads 2026"}},
                                   {"properties": {"sheetId": 9, "title": "Q1"}}]})

    monkeypatch.setattr(api, "sheets_api", lambda: Sheets())
    monkeypatch.setattr(ops, "meta", lambda fid: {"id": fid, "name": "x", "mimeType": ops.MIME["sheet"]})
    link = "https://docs.google.com/spreadsheets/d/1AbCdEfGhIjKlMnOpQrStUvWxYz0123456789/edit"
    if gid is not None:
        link += f"#gid={gid}"
    with pytest.raises(SystemExit) as e:
        cli.main(["read", link] + ([rng] if rng else []))
    return e.value.code, asked.get("range")


@pytest.mark.parametrize("rng, gid, expected", [
    (None, 77, "'Leads 2026'"),
    ("A1:F20", 77, "'Leads 2026'!A1:F20"),
    ("A:F", 77, "'Leads 2026'!A:F"),
    ("Other!A1", 77, "Other!A1"),
    ("Q1", 77, "'Q1'"),              # a tab named like a cell is the tab
    ("'Leads 2026'", None, "'Leads 2026'"),
    ("A1:B2", None, "'Sheet1'!A1:B2"),  # no gid: first VISIBLE tab, named explicitly
    (None, None, "'Sheet1'"),
    ("MyNamedRange", 77, "MyNamedRange"),
])
def test_range_always_names_the_right_tab(monkeypatch, rng, gid, expected):
    assert _gid_cli(monkeypatch, rng, gid) == (0, expected)


@pytest.mark.parametrize("rng, gid", [("A1", 999), ("'Nope'", 77)])
def test_stale_tab_link_or_unknown_tab_refuses(monkeypatch, capsys, rng, gid):
    code, asked = _gid_cli(monkeypatch, rng, gid)
    assert code == cli.EXIT_FAIL and asked is None
    assert "Tabs:" in capsys.readouterr().err


def test_reauth_demand_means_sign_in(isolated, monkeypatch):
    from google.auth.exceptions import RefreshError
    from google.oauth2.credentials import Credentials

    _saved_token()
    def boom(self, request):
        raise RefreshError("Reauthentication is needed. Please run `gcloud auth login`.")
    monkeypatch.setattr(Credentials, "refresh", boom)
    with pytest.raises(auth.SignInNeeded):
        auth.creds()


def test_network_permission_error_is_not_called_a_file_problem(monkeypatch, capsys):
    def blocked():
        raise PermissionError(13, "An attempt was made to access a socket in a way forbidden")
    monkeypatch.setattr(api, "drive", blocked)
    with pytest.raises(SystemExit) as e:
        cli.main(["find", "x"])
    assert e.value.code == cli.EXIT_NETWORK
    assert "Excel" not in capsys.readouterr().err


# ---- edge cases added in 1.1.0 ----------------------------------------------------------------

class _Req:
    def __init__(self, result): self.result = result
    def execute(self, num_retries=0): return self.result


def _sheet_meta(monkeypatch, mime=None, name="x"):
    monkeypatch.setattr(ops, "meta", lambda fid: {"id": fid, "name": name, "mimeType": mime or ops.MIME["sheet"]})


def test_platform_module_matches_os():
    from workspace_cli.platforms import current
    expected = "Windows" if sys.platform == "win32" else "macOS"
    assert current.NAME == expected
    assert current.INSTALLER_URL.endswith(".ps1" if expected == "Windows" else ".sh")
    assert current.config_dir().name == "gsuite"


def test_trailing_blank_csv_rows_are_dropped(tmp_path):
    f = tmp_path / "rows.csv"
    f.write_text("a,b\n1,2\n,\n\n", encoding="utf-8")
    assert files.read_csv_arg(str(f)) == [["a", "b"], ["1", "2"]]


def test_empty_csv_is_exit_1(tmp_path, capsys):
    f = tmp_path / "rows.csv"
    f.write_text("\n", encoding="utf-8")
    with pytest.raises(SystemExit) as e:
        cli.main(["append", "1AbCdEfGhIjKlMnOpQrStUvWxYz0123456789", "A1", str(f)])
    assert e.value.code == cli.EXIT_FAIL and "empty" in capsys.readouterr().err


@pytest.mark.parametrize("flag, expected", [([], "USER_ENTERED"), (["--raw"], "RAW")])
def test_raw_flag_controls_value_input(monkeypatch, tmp_path, flag, expected):
    seen = {}

    class Vals:
        def update(self, **kw):
            seen.update(kw)
            return _Req({"updatedCells": 1, "updatedRange": "A1"})

    class Sheets:
        def spreadsheets(self): return self
        def values(self): return Vals()
        def get(self, **kw): return _Req({"sheets": [{"properties": {"sheetId": 0, "title": "Sheet1"}}]})

    _sheet_meta(monkeypatch)
    monkeypatch.setattr(api, "sheets_api", lambda: Sheets())
    f = tmp_path / "rows.csv"
    f.write_text("+919876543210,00123\n", encoding="utf-8")
    with pytest.raises(SystemExit) as e:
        cli.main(["write", "1AbCdEfGhIjKlMnOpQrStUvWxYz0123456789", "A1", str(f)] + flag)
    assert e.value.code == 0
    assert seen["range"] == "'Sheet1'!A1"
    assert seen["valueInputOption"] == expected
    assert seen["body"]["values"] == [["+919876543210", "00123"]]


def test_read_is_capped_unless_all(monkeypatch, capsys):
    rows = [[str(i)] for i in range(ops.READ_LIMIT + 7)]

    class Sheets:
        def spreadsheets(self): return self
        def values(self): return self
        def get(self, **kw):
            return _Req({"values": rows} if "range" in kw else {"sheets": [{"properties": {"sheetId": 0, "title": "S"}}]})

    _sheet_meta(monkeypatch)
    monkeypatch.setattr(api, "sheets_api", lambda: Sheets())
    with pytest.raises(SystemExit):
        cli.main(["read", "1AbCdEfGhIjKlMnOpQrStUvWxYz0123456789"])
    out = capsys.readouterr()
    assert out.out.count("\n") == ops.READ_LIMIT and f"of {len(rows)} rows" in out.err
    with pytest.raises(SystemExit):
        cli.main(["read", "1AbCdEfGhIjKlMnOpQrStUvWxYz0123456789", "--all"])
    assert capsys.readouterr().out.count("\n") == len(rows)


def test_find_escapes_quotes_and_backslashes(monkeypatch):
    seen = {}

    class Drive:
        def files(self): return self
        def list(self, **kw):
            seen.update(kw)
            return _Req({"files": []})

    monkeypatch.setattr(api, "drive", lambda: Drive())
    ops.find("Kathan's a\\b", None, 5)
    assert "name contains 'Kathan\\'s'" in seen["q"] and "name contains 'a\\\\b'" in seen["q"]


def test_uploaded_xlsx_is_read_not_written(monkeypatch, tmp_path, capsys):
    import io as _io
    import pandas as pd

    buf = _io.BytesIO()
    pd.DataFrame([["Model", "Rent"], ["MacBook Air", "3500"]]).to_excel(buf, header=False, index=False)

    class Drive:
        def files(self): return self
        def get_media(self, **kw): return _Req(buf.getvalue())

    _sheet_meta(monkeypatch, ops.XLSX, "rates.xlsx")
    monkeypatch.setattr(api, "drive", lambda: Drive())
    with pytest.raises(SystemExit) as e:
        cli.main(["read", "1AbCdEfGhIjKlMnOpQrStUvWxYz0123456789"])
    assert e.value.code == 0
    assert capsys.readouterr().out == "Model,Rent\nMacBook Air,3500\n"

    f = tmp_path / "rows.csv"
    f.write_text("a\n", encoding="utf-8")
    with pytest.raises(SystemExit) as e:
        cli.main(["write", "1AbCdEfGhIjKlMnOpQrStUvWxYz0123456789", "A1", str(f)])
    assert e.value.code == cli.EXIT_FAIL and "Save as Google Sheets" in capsys.readouterr().err


def test_uploaded_file_export_keeps_its_own_format(monkeypatch, tmp_path, capsys):
    _sheet_meta(monkeypatch, ops.XLSX, "rates.xlsx")
    with pytest.raises(SystemExit) as e:
        cli.main(["export", "1AbCdEfGhIjKlMnOpQrStUvWxYz0123456789", str(tmp_path / "rates.csv")])
    assert e.value.code == cli.EXIT_FAIL and "save it as .xlsx" in capsys.readouterr().err


def test_remove_claude_takes_out_only_gsuite(isolated):
    settings = isolated / "claude" / "settings.json"
    settings.parent.mkdir(parents=True)
    settings.write_text(json.dumps({"model": "x", "permissions": {"allow": ["Bash(ls *)"], "ask": ["Bash(rm *)"]}}))
    agents.install_claude()
    assert agents.remove_claude() == 0
    data = json.loads(settings.read_text())
    assert data == {"model": "x", "permissions": {"allow": ["Bash(ls *)"], "ask": ["Bash(rm *)"]}}
    assert not (isolated / "claude" / "skills" / "gsuite").exists()


def test_server_error_is_retry_not_refusal(monkeypatch, capsys):
    from googleapiclient.errors import HttpError
    from httplib2 import Response

    def boom(fid):
        raise HttpError(Response({"status": 503}), b'{"error": {"message": "backend"}}')
    monkeypatch.setattr(ops, "meta", boom)
    with pytest.raises(SystemExit) as e:
        cli.main(["tabs", "1AbCdEfGhIjKlMnOpQrStUvWxYz0123456789"])
    assert e.value.code == cli.EXIT_NETWORK and "Try again" in capsys.readouterr().err


def test_append_is_never_sent_twice(monkeypatch):
    calls = []

    class Req:
        def execute(self, num_retries=0):
            calls.append(num_retries)
            raise TimeoutError("read timed out")

    with pytest.raises(api.MaybeApplied):
        api.run_once(Req())
    assert calls == [0]  # one attempt, and googleapiclient's own retries switched off


def test_append_retries_only_a_rate_limit(monkeypatch):
    from googleapiclient.errors import HttpError
    from httplib2 import Response

    calls = []
    monkeypatch.setattr(api.time, "sleep", lambda s: None)

    class Req:
        def execute(self, num_retries=0):
            calls.append(1)
            if len(calls) < 3:
                raise HttpError(Response({"status": 429}), b"{}")
            return {"ok": True}

    assert api.run_once(Req()) == {"ok": True} and len(calls) == 3


def test_unsure_change_is_exit_6(monkeypatch, tmp_path, capsys):
    class Vals:
        def append(self, **kw):
            class R:
                def execute(self, num_retries=0): raise ConnectionResetError("reset")
            return R()

    class Sheets:
        def spreadsheets(self): return self
        def values(self): return Vals()
        def get(self, **kw): return _Req({"sheets": [{"properties": {"sheetId": 0, "title": "Sheet1"}}]})

    _sheet_meta(monkeypatch)
    monkeypatch.setattr(api, "sheets_api", lambda: Sheets())
    f = tmp_path / "rows.csv"
    f.write_text("a\n", encoding="utf-8")
    with pytest.raises(SystemExit) as e:
        cli.main(["append", "1AbCdEfGhIjKlMnOpQrStUvWxYz0123456789", "'Sheet1'!A:A", str(f)])
    assert e.value.code == cli.EXIT_UNSURE and "Check the file" in capsys.readouterr().err


@pytest.mark.parametrize("perms", [None, {"allow": None}, {"ask": "Bash(rm *)"}, {"allow": "Bash(ls *)", "ask": None}])
def test_odd_settings_shapes_are_handled(isolated, perms):
    settings = isolated / "claude" / "settings.json"
    settings.parent.mkdir(parents=True)
    settings.write_text(json.dumps({"permissions": perms}))
    assert agents.install_claude() == 0
    assert agents.remove_claude() == 0
    after = json.loads(settings.read_text())["permissions"]
    kept = [r for v in (perms or {}).values() if v for r in ([v] if isinstance(v, str) else v)]
    assert sorted(after["allow"] + after["ask"]) == sorted(kept)


def test_output_is_utf8_even_on_a_legacy_windows_code_page():
    out = subprocess.run([sys.executable, "-c", "from workspace_cli.files import utf8_stdio; utf8_stdio(); print('₹ राम')"],
                         capture_output=True, env={**os.environ, "PYTHONIOENCODING": "cp1252"})
    assert out.returncode == 0 and out.stdout.decode("utf-8").strip() == "₹ राम"


def test_wrong_google_type_names_the_right_command(monkeypatch, capsys):
    _sheet_meta(monkeypatch, ops.MIME["doc"], "Notes")
    with pytest.raises(SystemExit) as e:
        cli.main(["read", "1AbCdEfGhIjKlMnOpQrStUvWxYz0123456789"])
    assert e.value.code == cli.EXIT_FAIL and "gsuite doc" in capsys.readouterr().err


def test_export_refuses_impossible_conversion(monkeypatch, tmp_path, capsys):
    _sheet_meta(monkeypatch, ops.MIME["doc"], "Notes")
    with pytest.raises(SystemExit) as e:
        cli.main(["export", "1AbCdEfGhIjKlMnOpQrStUvWxYz0123456789", str(tmp_path / "x.xlsx")])
    assert e.value.code == cli.EXIT_FAIL and ".docx" in capsys.readouterr().err


def test_uploaded_csv_in_legacy_encoding_is_a_clear_error(monkeypatch, capsys):
    class Drive:
        def files(self): return self
        def get_media(self, **kw): return _Req("Name\ncaf\xe9\n".encode("cp1252"))

    _sheet_meta(monkeypatch, "text/csv", "old.csv")
    monkeypatch.setattr(api, "drive", lambda: Drive())
    with pytest.raises(SystemExit) as e:
        cli.main(["read", "1AbCdEfGhIjKlMnOpQrStUvWxYz0123456789"])
    assert e.value.code == cli.EXIT_FAIL and "UTF-8" in capsys.readouterr().err


def test_logout_removes_leftover_token_copies(isolated):
    auth.config_dir().mkdir(parents=True)
    auth.token_file().write_text("{}")
    (auth.config_dir() / "token.1234.tmp").write_text("{}")
    auth.logout()
    assert list(auth.config_dir().iterdir()) == []
