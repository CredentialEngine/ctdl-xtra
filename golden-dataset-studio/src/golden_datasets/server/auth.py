"""One shared password for the Studio (the "Who are you?" screen asks for it before the profile).

The password comes from the environment when the server starts: `GOLDEN_DATASETS_PASSWORD_HASH` (preferred; made
by `golden-datasets hash-password`, so the plain password is never stored) or `GOLDEN_DATASETS_PASSWORD`, which is
salted and hashed at startup and not kept. With neither set, there is no password (local use, tests).

Hashes are scrypt with a random 16-byte salt: `scrypt$<n>$<r>$<p>$<salt hex>$<hash hex>`. Signing in sets an
HttpOnly cookie, `<expiry>.<HMAC>`, keyed from the stored hash (or, given the plain password, from a fixed-salt
scrypt of it, since its startup hash gets a new salt each time): it survives restarts and stops working when the
password changes. Every /api route except the ones in `OPEN` needs it.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import time
from typing import Annotated

from fastapi import APIRouter, Body, HTTPException, Request, Response
from fastapi.responses import JSONResponse

ENV_PASSWORD = "GOLDEN_DATASETS_PASSWORD"
ENV_HASH = "GOLDEN_DATASETS_PASSWORD_HASH"
COOKIE = "studio_session"
MAX_AGE = 30 * 24 * 3600
N, R, P = 2**14, 8, 1
OPEN = {"/api/health", "/api/session", "/api/login", "/api/logout"}

router = APIRouter(prefix="/api")


def _scrypt(password: str, salt: bytes, n: int, r: int, p: int) -> bytes:
    return hashlib.scrypt(password.encode(), salt=salt, n=n, r=r, p=p, maxmem=2**26, dklen=32)


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    return f"scrypt${N}${R}${P}${salt.hex()}${_scrypt(password, salt, N, R, P).hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, n, r, p, salt, digest = stored.split("$")
        if scheme != "scrypt":
            return False
        got = _scrypt(password, bytes.fromhex(salt), int(n), int(r), int(p))
    except ValueError:
        return False
    return hmac.compare_digest(got, bytes.fromhex(digest))


class Gate:
    """The stored hash (None: no password) and the session cookies made from it."""

    def __init__(self, stored: str | None, key: bytes | None = None):
        self.stored = stored
        self._key = key or (hashlib.sha256(b"studio-session\0" + stored.encode()).digest() if stored else b"")

    @classmethod
    def from_env(cls) -> "Gate":
        stored = os.environ.get(ENV_HASH) or None
        if stored is not None:
            if stored.count("$") != 5:
                raise SystemExit(f"{ENV_HASH} is not a hash from `golden-datasets hash-password`")
            return cls(stored)
        password = os.environ.get(ENV_PASSWORD)
        if not password:
            return cls(None)
        return cls(hash_password(password), _scrypt(password, b"studio-session-key", N, R, P))

    def _sign(self, expires: int) -> str:
        return hmac.new(self._key, str(expires).encode(), hashlib.sha256).hexdigest()

    def cookie(self) -> str:
        expires = int(time.time()) + MAX_AGE
        return f"{expires}.{self._sign(expires)}"

    def allows(self, request: Request) -> bool:
        if self.stored is None:
            return True
        expires, _, sig = (request.cookies.get(COOKIE) or "").partition(".")
        return expires.isdigit() and int(expires) > time.time() and hmac.compare_digest(sig, self._sign(int(expires)))


def install(app) -> None:
    app.state.gate = Gate.from_env()

    @app.middleware("http")
    async def require_session(request: Request, call_next):
        path = request.url.path
        if path.startswith("/api/") and path not in OPEN and not app.state.gate.allows(request):
            return JSONResponse({"detail": "sign in first"}, status_code=401)
        return await call_next(request)

    app.include_router(router)


@router.get("/session")
def session(request: Request) -> dict:
    gate: Gate = request.app.state.gate
    return {"password_required": gate.stored is not None, "signed_in": gate.allows(request)}


@router.post("/login")
def login(request: Request, response: Response, body: Annotated[dict, Body()]) -> dict:
    gate: Gate = request.app.state.gate
    if gate.stored is not None:
        if not verify_password(str(body.get("password") or ""), gate.stored):
            time.sleep(0.5)  # scrypt is already slow; this makes guessing slower still
            raise HTTPException(401, "wrong password")
        https = request.headers.get("x-forwarded-proto", request.url.scheme) == "https"
        response.set_cookie(COOKIE, gate.cookie(), max_age=MAX_AGE, httponly=True, samesite="lax", secure=https)
    return {"signed_in": True}


@router.post("/logout")
def logout(response: Response) -> dict:
    response.delete_cookie(COOKIE)
    return {"signed_in": False}


def cmd_hash_password(args) -> int:
    import getpass
    import sys

    password = sys.stdin.readline().rstrip("\n") if not sys.stdin.isatty() else getpass.getpass("Password: ")
    if not password:
        print("golden-datasets: an empty password", file=sys.stderr)
        return 2
    print(hash_password(password))
    return 0
