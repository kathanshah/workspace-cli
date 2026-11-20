"""Sign-in: one Google login per person, saved on that person's computer.

The OAuth client in client.json belongs to an Internal Google Cloud app, so only accounts in
DOMAIN can sign in, and the saved login does not expire after 7 days. It stops working only if
the person revokes it, their account is suspended, it goes unused for six months, or the client
secret is reset; every one of those is reported as "sign-in needed" with the fix.
"""
from __future__ import annotations

import base64
import json
import os
from importlib import resources
from pathlib import Path

DOMAIN = os.environ.get("GSUITE_DOMAIN", "spurge.rentals")
SCOPES = [
    "openid",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/spreadsheets",    # read/write sheets the person can open
    "https://www.googleapis.com/auth/documents",       # read/write docs the person can open
    "https://www.googleapis.com/auth/drive.readonly",  # find files, export, read metadata
    "https://www.googleapis.com/auth/drive.file",      # create files of its own
]
LOGIN_TIMEOUT = 300


class SignInNeeded(Exception):
    """No usable saved login; the fix is always `gsuite login`."""


def config_dir() -> Path:
    if env := os.environ.get("GSUITE_HOME"):
        return Path(env)
    if os.name == "nt":
        return Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming") / "gsuite"
    return Path.home() / ".config" / "gsuite"


def token_file() -> Path:
    return config_dir() / "token.json"


def client_config() -> dict:
    override = os.environ.get("GSUITE_CLIENT_FILE")
    text = Path(override).read_text() if override else \
        resources.files("workspace_cli").joinpath("client.json").read_text()
    return json.loads(text)


def _save(c) -> None:
    d = config_dir()
    d.mkdir(parents=True, exist_ok=True)
    tmp = d / f"token.{os.getpid()}.tmp"
    tmp.write_text(c.to_json())
    if os.name != "nt":
        os.chmod(d, 0o700)
        os.chmod(tmp, 0o600)
    os.replace(tmp, token_file())  # atomic: parallel commands never see a half-written file


def _email_from_id_token(id_token: str | None) -> str | None:
    # The id_token came straight from Google's token endpoint over TLS; reading it is enough.
    try:
        payload = id_token.split(".")[1]
        return json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))["email"]
    except Exception:
        return None


def revoke(c) -> None:
    import requests

    token = getattr(c, "refresh_token", None) or getattr(c, "token", None)
    if token:
        try:
            requests.post("https://oauth2.googleapis.com/revoke", data={"token": token}, timeout=10)
        except requests.RequestException:
            pass


DATA_SCOPES = [s for s in SCOPES if "/auth/" in s and not s.endswith("userinfo.email")]
CONSENT_HELP = ("On Google's screen, tick every box (Sheets, Docs, Drive) and click Continue. "
                "Then run: gsuite login")


def login(account: str | None = None) -> str:
    """Open the browser, let the person approve, save the login. Returns the account email."""
    # Report a partial approval ourselves instead of letting oauthlib raise a bare Warning.
    os.environ.setdefault("OAUTHLIB_RELAX_TOKEN_SCOPE", "1")
    from google_auth_oauthlib.flow import InstalledAppFlow
    from oauthlib.oauth2.rfc6749.errors import OAuth2Error

    flow = InstalledAppFlow.from_client_config(client_config(), SCOPES)
    extra = {"hd": DOMAIN, "prompt": "select_account consent"}
    if account:
        extra["login_hint"] = account
    message = (f"Opening your browser. Choose your @{DOMAIN} Google account, tick every box and "
               "click Continue.\nIf the browser does not open, copy this link into it:\n{url}\n")
    try:
        c = flow.run_local_server(
            port=0, open_browser=True, timeout_seconds=LOGIN_TIMEOUT,
            authorization_prompt_message=message,
            success_message="Done. You can close this tab and go back to the terminal.",
            **extra,
        )
    except AttributeError:  # no browser response within LOGIN_TIMEOUT
        raise SystemExit(f"Sign-in timed out after {LOGIN_TIMEOUT // 60} minutes. If Google said the app "
                         f"is blocked, you chose a personal account: use your @{DOMAIN} one. Run: gsuite login")
    except OAuth2Error as e:
        if getattr(e, "error", "") == "access_denied":
            raise SystemExit(f"Sign-in was cancelled. {CONSENT_HELP}")
        raise SystemExit(f"Google sign-in failed ({e.error}). Run: gsuite login")
    granted = c.granted_scopes or []
    granted = set(granted.split() if isinstance(granted, str) else granted)
    if granted and not set(DATA_SCOPES) <= granted:
        # Not saved, not revoked: revoking would also sign the person out on their other computers.
        raise SystemExit(f"Some permissions were not ticked. {CONSENT_HELP}")
    email = _email_from_id_token(getattr(c, "id_token", None)) or "unknown account"
    if not email.lower().endswith("@" + DOMAIN):
        revoke(c)
        raise SystemExit(f"You signed in as {email}. Use your @{DOMAIN} account: run gsuite login again.")
    _save(c)
    return email


def logout() -> bool:
    """Forget the login on this computer only. (Revoking at Google would sign the person out of
    gsuite on every computer, so that is left to myaccount.google.com.)"""
    tf = token_file()
    existed = tf.exists()
    tf.unlink(missing_ok=True)
    return existed


def creds():
    """A valid login, refreshed if needed. Raises SignInNeeded with the reason otherwise."""
    from google.auth.exceptions import RefreshError
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials

    tf = token_file()
    if not tf.exists():
        raise SignInNeeded("this computer is not signed in yet")
    try:
        saved = json.loads(tf.read_text(encoding="utf-8"))
        c = Credentials.from_authorized_user_info(saved, SCOPES)
    except (ValueError, KeyError):
        raise SignInNeeded("the saved sign-in is damaged")
    if not set(SCOPES) <= set(saved.get("scopes") or SCOPES):
        raise SignInNeeded("this version of gsuite needs one more permission")
    if not c.valid:
        try:
            c.refresh(Request())
        except RefreshError as e:
            if getattr(e, "retryable", False):
                raise  # a passing Google problem: reported as "try again", not as "sign in again"
            raise SignInNeeded("the saved sign-in expired, was revoked, or Google wants you to sign in again")
        try:
            _save(c)
        except OSError:
            pass  # e.g. another gsuite or antivirus holds the file; the refreshed token still works now
    return c
