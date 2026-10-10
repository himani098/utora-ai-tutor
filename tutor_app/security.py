from __future__ import annotations

import base64
import hashlib
import re

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

KDF_ITERATIONS = 600_000
VERIFIER_TEXT = b"utora-learning-vault-v1"
HANDLE_PATTERN = re.compile(r"^[A-Za-z0-9_.-]{2,32}$")


class ProfileError(ValueError):
    """Raised when a local learning profile cannot be opened safely."""


def normalize_handle(handle: str) -> str:
    value = handle.strip()
    if not HANDLE_PATTERN.fullmatch(value):
        raise ProfileError(
            "Use 2–32 letters, numbers, dots, dashes, or underscores for your nickname. Do not use an email."
        )
    return value.casefold()


def profile_id_for_handle(handle: str) -> str:
    return hashlib.sha256(normalize_handle(handle).encode("utf-8")).hexdigest()


def validate_passphrase(passphrase: str) -> None:
    if len(passphrase) < 12:
        raise ProfileError("Choose a passphrase of at least 12 characters.")
    if len(passphrase) > 256:
        raise ProfileError("Keep the passphrase under 256 characters.")


def derive_key(passphrase: str, salt: bytes, iterations: int = KDF_ITERATIONS) -> bytes:
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=iterations,
    )
    return base64.urlsafe_b64encode(kdf.derive(passphrase.encode("utf-8")))


def encrypt(key: bytes, value: bytes) -> bytes:
    return Fernet(key).encrypt(value)


def decrypt(key: bytes, value: bytes) -> bytes:
    try:
        return Fernet(key).decrypt(value)
    except (InvalidToken, ValueError) as exc:
        raise ProfileError("The passphrase is incorrect or the encrypted learning data is damaged.") from exc


def make_verifier(key: bytes) -> bytes:
    return encrypt(key, VERIFIER_TEXT)


def verify_key(key: bytes, verifier: bytes) -> None:
    if decrypt(key, verifier) != VERIFIER_TEXT:
        raise ProfileError("The passphrase is incorrect.")
