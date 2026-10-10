from __future__ import annotations

import json
import os
import secrets
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from tutor_app.security import (
    KDF_ITERATIONS,
    ProfileError,
    decrypt,
    derive_key,
    encrypt,
    make_verifier,
    profile_id_for_handle,
    validate_passphrase,
    verify_key,
)


class DataStoreError(RuntimeError):
    """A local learning-data operation failed."""


def database_path() -> Path:
    override = os.getenv("UTORAI_DATA_DIR", "").strip()
    base = Path(override).expanduser() if override else Path.home() / ".utora"
    return base / "learning.sqlite3"


class Repository:
    def __init__(self, path: Path | str):
        self.path = Path(path)
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self._connect() as db:
                db.execute("PRAGMA journal_mode = WAL")
                db.execute(
                    """CREATE TABLE IF NOT EXISTS vaults (
                        profile_id TEXT PRIMARY KEY,
                        salt BLOB NOT NULL,
                        iterations INTEGER NOT NULL,
                        verifier BLOB NOT NULL
                    )"""
                )
                db.execute(
                    """CREATE TABLE IF NOT EXISTS records (
                        profile_id TEXT NOT NULL REFERENCES vaults(profile_id) ON DELETE CASCADE,
                        kind TEXT NOT NULL,
                        record_key TEXT NOT NULL,
                        payload BLOB NOT NULL,
                        PRIMARY KEY (profile_id, kind, record_key)
                    )"""
                )
        except (OSError, sqlite3.Error) as exc:
            raise DataStoreError("The private learning database could not be opened.") from exc

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        db = sqlite3.connect(self.path, timeout=15)
        try:
            db.execute("PRAGMA foreign_keys = ON")
            db.execute("PRAGMA busy_timeout = 15000")
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def _get_vault(self, profile_id: str) -> tuple[bytes, int, bytes] | None:
        try:
            with self._connect() as db:
                row = db.execute(
                    "SELECT salt, iterations, verifier FROM vaults WHERE profile_id = ?",
                    (profile_id,),
                ).fetchone()
            if row is None:
                return None
            return bytes(row[0]), int(row[1]), bytes(row[2])
        except sqlite3.Error as exc:
            raise DataStoreError("The private profile could not be checked.") from exc

    def unlock_or_create(
        self, handle: str, passphrase: str, confirmation: str
    ) -> tuple[str, bytes, bool]:
        profile_id = profile_id_for_handle(handle)
        existing = self._get_vault(profile_id)
        if existing is not None:
            salt, iterations, verifier = existing
            key = derive_key(passphrase, salt, iterations)
            verify_key(key, verifier)
            return profile_id, key, False

        validate_passphrase(passphrase)
        if passphrase != confirmation:
            raise ProfileError("The two passphrases do not match.")
        salt = secrets.token_bytes(16)
        key = derive_key(passphrase, salt)
        try:
            with self._connect() as db:
                db.execute(
                    "INSERT INTO vaults(profile_id, salt, iterations, verifier) VALUES (?, ?, ?, ?)",
                    (profile_id, salt, KDF_ITERATIONS, make_verifier(key)),
                )
        except sqlite3.IntegrityError as exc:
            raise ProfileError("This profile was just created. Enter its passphrase to unlock it.") from exc
        except sqlite3.Error as exc:
            raise DataStoreError("The private profile could not be created.") from exc
        return profile_id, key, True

    def put(self, profile_id: str, key: bytes, kind: str, record_key: str, value: Any) -> None:
        if not kind or len(kind) > 32 or not record_key or len(record_key) > 200:
            raise DataStoreError("The learning record has an invalid identifier.")
        try:
            raw = json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
            if len(raw) > 2_000_000:
                raise DataStoreError("This learning record is larger than the 2 MB limit.")
            ciphertext = encrypt(key, raw)
            with self._connect() as db:
                db.execute(
                    """INSERT INTO records(profile_id, kind, record_key, payload)
                       VALUES (?, ?, ?, ?)
                       ON CONFLICT(profile_id, kind, record_key)
                       DO UPDATE SET payload = excluded.payload""",
                    (profile_id, kind, record_key, ciphertext),
                )
        except DataStoreError:
            raise
        except (sqlite3.Error, TypeError, ValueError) as exc:
            raise DataStoreError("The encrypted learning record could not be saved.") from exc

    def get(self, profile_id: str, key: bytes, kind: str, record_key: str) -> Any | None:
        try:
            with self._connect() as db:
                row = db.execute(
                    """SELECT payload FROM records
                       WHERE profile_id = ? AND kind = ? AND record_key = ?""",
                    (profile_id, kind, record_key),
                ).fetchone()
            if row is None:
                return None
            return json.loads(decrypt(key, bytes(row[0])).decode("utf-8"))
        except ProfileError as exc:
            raise DataStoreError("This record could not be decrypted with the unlocked profile.") from exc
        except (sqlite3.Error, UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError) as exc:
            raise DataStoreError("The encrypted learning record could not be read.") from exc

    def list(self, profile_id: str, key: bytes, kind: str) -> list[Any]:
        try:
            with self._connect() as db:
                rows = db.execute(
                    """SELECT payload FROM records
                       WHERE profile_id = ? AND kind = ? ORDER BY rowid""",
                    (profile_id, kind),
                ).fetchall()
            return [
                json.loads(decrypt(key, bytes(row[0])).decode("utf-8"))
                for row in rows
            ]
        except ProfileError as exc:
            raise DataStoreError("Some records could not be decrypted with the unlocked profile.") from exc
        except (sqlite3.Error, UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError) as exc:
            raise DataStoreError("The encrypted learning records could not be read.") from exc

    def delete_profile(self, profile_id: str) -> None:
        try:
            with self._connect() as db:
                db.execute("DELETE FROM vaults WHERE profile_id = ?", (profile_id,))
        except sqlite3.Error as exc:
            raise DataStoreError("This profile and its data could not be deleted.") from exc
