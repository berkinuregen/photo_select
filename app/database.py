import sqlite3
from contextlib import contextmanager

from .config import DATA_DIR

DB_PATH = DATA_DIR / "photo_select.sqlite3"


def init_db():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with connect() as db:
        db.executescript("""
            CREATE TABLE IF NOT EXISTS galleries (
                id INTEGER PRIMARY KEY,
                token TEXT NOT NULL UNIQUE,
                title TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                selection_limit INTEGER NOT NULL CHECK(selection_limit > 0),
                published INTEGER NOT NULL DEFAULT 0,
                submitted_at TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS photos (
                id INTEGER PRIMARY KEY,
                gallery_id INTEGER NOT NULL REFERENCES galleries(id) ON DELETE CASCADE,
                filename TEXT NOT NULL,
                preview_name TEXT NOT NULL UNIQUE,
                selected INTEGER NOT NULL DEFAULT 0,
                note TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE INDEX IF NOT EXISTS photos_gallery ON photos(gallery_id);
            CREATE TABLE IF NOT EXISTS pending_preview_deletions (
                preview_name TEXT PRIMARY KEY
            );
        """)


@contextmanager
def connect():
    db = sqlite3.connect(DB_PATH, timeout=30)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys = ON")
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
