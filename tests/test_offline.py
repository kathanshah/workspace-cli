"""Offline tests: everything that must work before anyone signs in, on every OS."""
import json
import subprocess
import sys

import pytest

from workspace_cli import agents, api, auth, cli


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
    assert cli.read_csv_arg(str(f)) == [["Name", "Amount"], ["राम", "₹5,000"]]


def test_csv_output_has_no_blank_lines(capsys):
    cli.write_csv([["a", "₹1"], ["b", "2"]])
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
    assert cli.read_csv_arg(str(f)) == [["Name", "Amount"], ["राम", "5000"]]


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


def _gid_cli(monkeypatch, rng):
    """Run `read` on a #gid link with a stubbed Sheets API; return the range Google is asked for."""
    asked = {}

    class Req:
        def __init__(self, result): self.result = result
        def execute(self, num_retries=0): return self.result

    class Sheets:
        def spreadsheets(self): return self
        def values(self): return self
        def get(self, spreadsheetId, fields=None, range=None):
            if range is not None:
                asked["range"] = range
                return Req({"values": []})
            return Req({"sheets": [{"properties": {"sheetId": 0, "title": "Sheet1"}},
                                   {"properties": {"sheetId": 77, "title": "Leads 2026"}}]})

    monkeypatch.setattr(api, "sheets_api", lambda: Sheets())
    link = "https://docs.google.com/spreadsheets/d/1AbCdEfGhIjKlMnOpQrStUvWxYz0123456789/edit#gid=77"
    with pytest.raises(SystemExit):
        cli.main(["read", link] + ([rng] if rng else []))
    return asked["range"]


@pytest.mark.parametrize("rng, expected", [
    (None, "'Leads 2026'"),
    ("A1:F20", "'Leads 2026'!A1:F20"),
    ("A:F", "'Leads 2026'!A:F"),
    ("'Other'", "'Other'"),
    ("Other!A1", "Other!A1"),
    ("Leads", "Leads"),
])
def test_gid_link_selects_tab_only_for_bare_cells(monkeypatch, rng, expected):
    assert _gid_cli(monkeypatch, rng) == expected


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
