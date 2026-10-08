"""Log in to meny.no through Trumf ID and get an API token.

Flow (as performed by the meny.no web frontend):

1. GET  meny.no/api/login?providerHandle=trumf-personal
   -> redirects through id.trumf.no/connect/authorize to the login SPA at
      id.trumf.no/ui/login/start?chain=..&returnUrl=..&correlationId=..
      (or to /ui/login when Trumf already knows the user, see 6.)
2. POST id.trumf.no/trumfid/login/validateUser   {"phoneNumber": ...}
3. POST id.trumf.no/trumfid/login/pwd            {"password": ..., "rememberMe": true}
   -> {"redirect": ...}; back to /connect/authorize/callback, or to the
      SMS one-time-code page.
4. (optional) POST id.trumf.no/trumfid/smsCode   {"otp": ..., "rememberMeSms": true}
5. (optional) /ui/registerbiometric offers passkey setup; declined with
   POST /trumfid/biometri/registration/skip?...&rememberSkipRegistration=true
6. (optional) /ui/login with a context saying `showContinueAsDialog` ("Du er
   allerede logget inn med Trumf"); continued with GET /trumfid/continue.
7. The redirect chain ends at meny.no/api/auth/callback/trumf-personal, which
   sets the Auth.js session cookie on meny.no.
8. GET  meny.no/api/auth/getToken -> JSON string with the access token (JWT),
   used as `Authorization: Bearer <jwt>` against platform-rest-prod.ngdata.no.

All cookies (meny.no session, Trumf session, Trumf "remember this device")
are persisted after every attempt, successful or not, so later runs usually
only call getToken. A password login is only attempted when that no longer
works, and it is never retried automatically, to stay clear of lockouts.
"""

import json
import os
import random
import re
import time
from pathlib import Path
from urllib.parse import parse_qs, urljoin, urlparse

import requests
from dotenv import load_dotenv

MENY = "https://meny.no"
TRUMF_ID = "https://id.trumf.no"

# A browser User-Agent so the site serves its normal pages, with a product
# token at the end saying what is actually making the requests.
CLIENT_NAME = "agenter-paa-menyen/0.1"
USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    f"(KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36 {CLIENT_NAME}"
)

DEFAULT_SESSION_FILE = Path(".session/cookies.json")


class LoginError(RuntimeError):
    pass


class OtpRequired(LoginError):
    """Trumf sent an SMS code; the login has to be finished with it."""


def _new_session() -> requests.Session:
    s = requests.Session()
    s.headers.update(
        {
            "User-Agent": USER_AGENT,
            "Accept-Language": "nb-NO,nb;q=0.9,no;q=0.8,en;q=0.7",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        }
    )
    return s


def _pause() -> None:
    """Small human-ish delay between login steps."""
    time.sleep(random.uniform(0.6, 1.5))


def _path(url: str) -> str:
    return urlparse(url).path.lower()


def _normalize_phone(raw: str) -> str:
    phone = re.sub(r"\D", "", raw)
    if phone.startswith("47") and len(phone) == 10:
        phone = phone[2:]
    if not re.fullmatch(r"[49]\d{7}", phone):
        raise LoginError(
            "TRUMF_USERNAME must be a Norwegian mobile number (8 digits, starting with 4 or 9)"
        )
    return phone


def save_cookies(session: requests.Session, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    cookies = [
        {
            "name": c.name,
            "value": c.value,
            "domain": c.domain,
            "path": c.path,
            "expires": c.expires,
            "secure": c.secure,
        }
        for c in session.cookies
    ]
    path.write_text(json.dumps(cookies, indent=2))
    path.chmod(0o600)


def load_cookies(session: requests.Session, path: Path) -> bool:
    if not path.exists():
        return False
    for c in json.loads(path.read_text()):
        session.cookies.set(
            c["name"],
            c["value"],
            domain=c["domain"],
            path=c["path"],
            expires=c["expires"],
            secure=c["secure"],
        )
    return True


def fetch_token(session: requests.Session) -> str | None:
    """Return the current access token (JWT) or None if not logged in."""
    r = session.get(
        f"{MENY}/api/auth/getToken", headers={"Accept": "application/json"}, timeout=20
    )
    r.raise_for_status()
    token = r.json()
    return token if isinstance(token, str) and token else None


class TrumfLogin:
    """Drives the Trumf ID login pages on behalf of meny.no."""

    def __init__(self, session: requests.Session):
        self.s = session
        self.params: dict[str, str] = {}
        self.trail: list[str] = []  # visited paths, for error messages

    def _visit(self, r: requests.Response) -> requests.Response:
        for h in [*r.history, r]:
            self.trail.append(f"{urlparse(h.url).hostname}{urlparse(h.url).path}")
        return r

    def _fail(self, message: str) -> LoginError:
        return LoginError(f"{message} (via {' -> '.join(self.trail[-8:])})")

    def _set_params_from(self, url: str) -> None:
        # The login SPA appends correlationId and returnUrl from its own URL
        # (matched case-insensitively) to every API call it makes.
        q = {k.lower(): v[0] for k, v in parse_qs(urlparse(url).query).items()}
        for key in ("correlationId", "returnUrl"):
            if key.lower() in q:
                self.params[key] = q[key.lower()]

    def _post_json(self, path: str, body: dict, referer: str) -> requests.Response:
        return self.s.post(
            f"{TRUMF_ID}{path}",
            params=self.params,
            json=body,
            headers={
                "Accept": "application/json",
                "Origin": TRUMF_ID,
                "Referer": referer,
            },
            timeout=30,
        )

    @staticmethod
    def _error_text(r: requests.Response) -> str:
        try:
            body = r.json()
        except ValueError:
            return f"HTTP {r.status_code}"
        kind = body.get("type") or body.get("problemType") or body.get("title")
        return f"HTTP {r.status_code}: {kind}" if kind else f"HTTP {r.status_code}"

    def _redirect_from(self, r: requests.Response, step: str) -> str:
        if not r.ok:
            raise self._fail(f"{step} was not accepted ({self._error_text(r)})")
        redirect = (r.json() or {}).get("redirect")
        if not redirect:
            raise self._fail(f"{step} accepted but no redirect was returned")
        return urljoin(TRUMF_ID, redirect)

    def advance(self, r: requests.Response) -> requests.Response:
        """Get past the pages that need no user input.

        Returns the response for the first page that does need input (password
        or SMS code), or the final meny.no page.
        """
        for _ in range(6):
            r.raise_for_status()
            host = urlparse(r.url).hostname or ""
            path = _path(r.url)
            if host.endswith("meny.no"):
                return r
            if path.startswith("/ui/registerbiometric"):
                _pause()
                self._set_params_from(r.url)
                r = self._visit(
                    self.s.post(
                        f"{TRUMF_ID}/trumfid/biometri/registration/skip",
                        params={**self.params, "rememberSkipRegistration": "true"},
                        headers={"Origin": TRUMF_ID, "Referer": r.url},
                        timeout=30,
                    )
                )
            elif path == "/ui/login":
                self._set_params_from(r.url)
                ctx = self.s.get(
                    f"{TRUMF_ID}/trumfid/login/context",
                    params={
                        "ReturnUrl": self.params.get("returnUrl", ""),
                        "correlationId": self.params.get("correlationId", ""),
                    },
                    headers={"Accept": "application/json", "Referer": r.url},
                    timeout=30,
                )
                ctx.raise_for_status()
                if not ctx.json().get("showContinueAsDialog"):
                    return r  # a real login form
                _pause()
                r = self._visit(
                    self.s.get(
                        f"{TRUMF_ID}/trumfid/continue",
                        params=self.params,
                        headers={"Referer": r.url},
                        timeout=30,
                    )
                )
            else:
                return r
        raise self._fail("Too many steps without reaching meny.no")

    def start(self) -> requests.Response:
        r = self._visit(
            self.s.get(
                f"{MENY}/api/login",
                params={"providerHandle": "trumf-personal"},
                timeout=30,
            )
        )
        return self.advance(r)

    def password_login(
        self, page: requests.Response, phone: str, password: str
    ) -> requests.Response:
        self._set_params_from(page.url)
        if "returnUrl" not in self.params:
            raise self._fail("Login page URL had no returnUrl")
        # The SPA loads its context first; mimic it.
        self.s.get(
            f"{TRUMF_ID}/trumfid/login/context",
            params=self.params,
            headers={"Accept": "application/json", "Referer": page.url},
            timeout=30,
        ).raise_for_status()
        _pause()
        r = self._post_json(
            "/trumfid/login/validateUser", {"phoneNumber": phone}, page.url
        )
        if "/ui/error" in r.url or not r.ok:
            raise self._fail(f"Phone number was not accepted ({self._error_text(r)})")
        _pause()
        nxt = self._redirect_from(
            self._post_json(
                "/trumfid/login/pwd",
                {"password": password, "rememberMe": True},
                page.url,
            ),
            "Password",
        )
        return self.advance(self._visit(self.s.get(nxt, timeout=30)))

    def sms_code(self, otp: str, sms_page_url: str) -> requests.Response:
        self._set_params_from(sms_page_url)
        nxt = self._redirect_from(
            self._post_json(
                "/trumfid/smsCode",
                {"otp": otp.strip(), "rememberMeSms": True},
                sms_page_url,
            ),
            "SMS code",
        )
        _pause()
        return self.advance(self._visit(self.s.get(nxt, timeout=30)))


def _pending_file(session_file: Path) -> Path:
    return session_file.with_name("pending-otp.json")


def _credentials() -> tuple[str, str]:
    load_dotenv()
    username = os.environ.get("TRUMF_USERNAME")
    password = os.environ.get("TRUMF_PASSWORD")
    if not username or not password:
        raise LoginError("TRUMF_USERNAME and TRUMF_PASSWORD must be set (e.g. in .env)")
    return _normalize_phone(username), password


def _conclude(login: TrumfLogin, r: requests.Response, session_file: Path) -> str:
    """Handle where the login ended up; return the token when logged in."""
    path = _path(r.url)
    if (urlparse(r.url).hostname or "").endswith("meny.no"):
        token = fetch_token(login.s)
        if not token:
            raise login._fail("Reached meny.no but it returned no token")
        return token
    if path.startswith("/ui/smscode"):
        pending = _pending_file(session_file)
        pending.parent.mkdir(parents=True, exist_ok=True)
        pending.write_text(json.dumps({"sms_page_url": r.url}))
        pending.chmod(0o600)
        raise OtpRequired(
            "Trumf sent an SMS code; finish with `matlevering login --otp <code>`"
        )
    raise login._fail(f"Login stopped at an unhandled page: {path}")


def login(
    session_file: Path = DEFAULT_SESSION_FILE, otp: str | None = None
) -> tuple[requests.Session, str]:
    """Log in (or finish a login waiting for an SMS code) and save the session."""
    s = _new_session()
    if load_cookies(s, session_file) and not otp:
        token = fetch_token(s)
        if token:
            save_cookies(s, session_file)
            return s, token
    flow = TrumfLogin(s)
    try:
        if otp:
            pending = _pending_file(session_file)
            if not pending.exists():
                raise LoginError(
                    "No login is waiting for an SMS code; run `matlevering login` first"
                )
            r = flow.sms_code(otp, json.loads(pending.read_text())["sms_page_url"])
            pending.unlink()  # the code is spent
        else:
            r = flow.start()
            if _path(r.url).startswith("/ui/login"):
                _pause()
                r = flow.password_login(r, *_credentials())
        return s, _conclude(flow, r, session_file)
    finally:
        save_cookies(s, session_file)


def get_session(
    session_file: Path = DEFAULT_SESSION_FILE,
) -> tuple[requests.Session, str]:
    """Return a requests session logged in to meny.no and a fresh access token.

    Only uses the saved session; run `login` when it has expired.
    """
    s = _new_session()
    if load_cookies(s, session_file):
        token = fetch_token(s)
        if token:
            save_cookies(s, session_file)  # pick up any rotated session cookie
            return s, token
    raise LoginError("Saved session is missing or expired; run `matlevering login`")
