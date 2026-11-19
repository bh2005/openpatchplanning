"""Passwörter (scrypt), Sitzungs- und API-Tokens."""
from __future__ import annotations

import hashlib
import hmac
import secrets

_SCRYPT = (2 ** 14, 8, 1)


def hash_password(password: str) -> str:
    n, r, p = _SCRYPT
    salt = secrets.token_bytes(16)
    h = hashlib.scrypt(password.encode(), salt=salt, n=n, r=r, p=p, dklen=32)
    return f"scrypt${n}${r}${p}${salt.hex()}${h.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, n, r, p, salt, h = stored.split("$")
        if scheme != "scrypt":
            return False
        calc = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=int(n), r=int(r), p=int(p), dklen=32)
        return hmac.compare_digest(calc.hex(), h)
    except Exception:
        return False


def new_session_token() -> str:
    return secrets.token_hex(32)


def new_api_token() -> str:
    """API-Token im Format ``opp_<48 Hex-Zeichen>``; nur der SHA-256 wird gespeichert."""
    return "opp_" + secrets.token_hex(24)


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()
