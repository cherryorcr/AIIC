from __future__ import annotations

import base64
import hashlib
import hmac
import secrets


PASSWORD_ALGORITHM = "pbkdf2_sha256"
PASSWORD_ITERATIONS = 390_000


def normalize_email(value: str) -> str:
    return str(value or "").strip().lower()


def hash_password(password: str) -> str:
    """Hash a password with a per-user salt using only the Python stdlib."""
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, PASSWORD_ITERATIONS
    )
    return "$".join(
        (
            PASSWORD_ALGORITHM,
            str(PASSWORD_ITERATIONS),
            base64.urlsafe_b64encode(salt).decode("ascii"),
            base64.urlsafe_b64encode(digest).decode("ascii"),
        )
    )


def verify_password(password: str, encoded: str | None) -> bool:
    if not encoded:
        return False
    try:
        algorithm, iterations, salt_text, digest_text = encoded.split("$", 3)
        if algorithm != PASSWORD_ALGORITHM:
            return False
        salt = base64.urlsafe_b64decode(salt_text.encode("ascii"))
        expected = base64.urlsafe_b64decode(digest_text.encode("ascii"))
        actual = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), salt, int(iterations)
        )
        return hmac.compare_digest(actual, expected)
    except (TypeError, ValueError, UnicodeError):
        return False


def new_session_token() -> str:
    return secrets.token_urlsafe(48)


def hash_session_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
