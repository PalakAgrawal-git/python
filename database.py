import sqlite3
from datetime import datetime


class HeatwaveDB:
    """SQLite-backed store for sensor readings."""

    def __init__(self, path="heatwave.db"):
        self.path = path
        self._create_table()

    def _connect(self):
        return sqlite3.connect(self.path)

    def _create_table(self):
        with self._connect() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS readings (
                    id        INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT    NOT NULL,
                    temp      REAL    NOT NULL,
                    humidity  REAL    NOT NULL,
                    heat_idx  REAL    NOT NULL,
                    alert     TEXT    NOT NULL
                )
            """)

    def insert(self, temp, humidity, heat_idx, alert):
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO readings (timestamp, temp, humidity, heat_idx, alert) "
                "VALUES (?, ?, ?, ?, ?)",
                (ts, temp, humidity, heat_idx, alert),
            )

    def fetch_recent(self, limit=100):
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT timestamp, temp, humidity, heat_idx, alert "
                "FROM readings ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return list(reversed(rows))

    def count(self):
        with self._connect() as conn:
            return conn.execute("SELECT COUNT(*) FROM readings").fetchone()[0]

    def clear(self):
        with self._connect() as conn:
            conn.execute("DELETE FROM readings")
