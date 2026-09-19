from contextlib import contextmanager
import json
import os
from pathlib import Path
import sqlite3
import time


class Store:
    """Separate, transactional native profile; never opens the Flutter Hive files."""

    def __init__(self, app, directory=None):
        self.path = Path(
            directory
            or Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share"))
            / f"{app.lower()}-gtk"
        )
        self.path.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.db = self.path / "profile.sqlite3"
        with self.connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS library(kind TEXT, id TEXT, data TEXT NOT NULL, updated REAL NOT NULL,
                  PRIMARY KEY(kind, id));
            """)
        self.db.chmod(0o600)

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.db, timeout=10)
        try:
            with db:
                yield db
        finally:
            db.close()

    def get(self, key, default=None):
        with self.connect() as db:
            row = db.execute(
                "SELECT value FROM settings WHERE key=?", (key,)
            ).fetchone()
        return json.loads(row[0]) if row else default

    def set(self, key, value):
        with self.connect() as db:
            db.execute(
                "INSERT OR REPLACE INTO settings VALUES(?, ?)", (key, json.dumps(value))
            )

    def put(self, kind, item):
        with self.connect() as db:
            db.execute(
                "INSERT OR REPLACE INTO library VALUES(?, ?, ?, ?)",
                (
                    kind,
                    str(item["id"]),
                    json.dumps(item, ensure_ascii=False),
                    time.time(),
                ),
            )

    def remove(self, kind, identifier):
        with self.connect() as db:
            db.execute(
                "DELETE FROM library WHERE kind=? AND id=?", (kind, str(identifier))
            )

    def items(self, kind):
        with self.connect() as db:
            rows = db.execute(
                "SELECT data FROM library WHERE kind=? ORDER BY updated DESC", (kind,)
            ).fetchall()
        return [json.loads(r[0]) for r in rows]

    def export_data(self):
        with self.connect() as db:
            return {
                "format": "gnome-media-profile",
                "version": 1,
                "settings": {
                    k: json.loads(v)
                    for k, v in db.execute("SELECT key,value FROM settings")
                    if k not in ("token", "cookie")
                },
                "library": [list(r) for r in db.execute("SELECT * FROM library")],
            }

    def import_data(self, data):
        if data.get("format") != "gnome-media-profile" or data.get("version") != 1:
            raise ValueError("不是本原生版的备份文件；Flutter 数据迁移尚未实现")
        settings = data["settings"]
        rows = data["library"]
        # Validate the whole backup before entering the write transaction.
        if not isinstance(settings, dict):
            raise ValueError("设置格式无效")
        for row in rows:
            if len(row) != 4 or not isinstance(json.loads(row[2]), dict):
                raise ValueError("备份记录无效")
        with self.connect() as db:
            for key, value in settings.items():
                if key not in ("token", "cookie"):
                    db.execute(
                        "INSERT OR REPLACE INTO settings VALUES(?,?)",
                        (key, json.dumps(value)),
                    )
            db.executemany("INSERT OR REPLACE INTO library VALUES(?,?,?,?)", rows)
