"""SQLite-Zugriff (nur Standardbibliothek) und einfache SQL-Migrationen."""
from __future__ import annotations

import contextlib
import os
import sqlite3
import threading
import time
from pathlib import Path
from typing import Iterator, Optional

from .config import settings

_lock = threading.RLock()
MIGRATIONS_DIR = Path(__file__).resolve().parent.parent / "migrations"


def db_path() -> str:
    return os.path.join(settings.data_dir, "opp.db")


@contextlib.contextmanager
def conn() -> Iterator[sqlite3.Connection]:
    """Verbindung mit Commit/Rollback und garantiertem Schließen; Fremdschlüssel sind aktiv."""
    os.makedirs(settings.data_dir, exist_ok=True)
    c = sqlite3.connect(db_path(), timeout=15)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys = ON")
    try:
        with c:
            yield c
    finally:
        c.close()


def migrate() -> list[str]:
    """Wendet alle noch nicht angewendeten Migrationen (migrations/NNNN_name.sql) der Reihe nach an."""
    applied: list[str] = []
    with _lock, conn() as c:
        c.execute("CREATE TABLE IF NOT EXISTS schema_migrations (name TEXT PRIMARY KEY, applied_at REAL NOT NULL)")
        done = {r["name"] for r in c.execute("SELECT name FROM schema_migrations")}
        for f in sorted(MIGRATIONS_DIR.glob("*.sql")):
            if f.name in done:
                continue
            c.executescript(f.read_text(encoding="utf-8"))
            c.execute("INSERT INTO schema_migrations(name, applied_at) VALUES (?,?)", (f.name, time.time()))
            applied.append(f.name)
    try:
        os.chmod(db_path(), 0o600)
    except OSError:
        pass
    return applied


def rows(sql: str, args: tuple = ()) -> list[dict]:
    with _lock, conn() as c:
        return [dict(r) for r in c.execute(sql, args)]


def row(sql: str, args: tuple = ()) -> Optional[dict]:
    with _lock, conn() as c:
        r = c.execute(sql, args).fetchone()
        return dict(r) if r else None


def execute(sql: str, args: tuple = ()) -> int:
    """Führt eine Schreibanweisung aus und liefert lastrowid."""
    with _lock, conn() as c:
        return c.execute(sql, args).lastrowid


def get_setting(key: str, default: str = "") -> str:
    r = row("SELECT value FROM app_settings WHERE key=?", (key,))
    return r["value"] if r else default


def put_settings(values: dict) -> None:
    with _lock, conn() as c:
        for k, v in values.items():
            c.execute("INSERT INTO app_settings(key, value) VALUES (?,?) "
                      "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (k, str(v)))
