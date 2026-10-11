import sqlite3


class HeatwaveDB:
    """SQLite database for heatwave event records."""

    def __init__(self, path="heatwave.db"):
        self.path = path
        self._create_table()

    def _connect(self):
        return sqlite3.connect(self.path)

    def _create_table(self):
        with self._connect() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS records (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    city        TEXT    NOT NULL,
                    date        TEXT    NOT NULL,
                    temperature REAL    NOT NULL,
                    humidity    REAL    NOT NULL,
                    alert_level TEXT    NOT NULL
                )
            """)

    def insert(self, city, date, temperature, humidity, alert_level):
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO records (city, date, temperature, humidity, alert_level) "
                "VALUES (?, ?, ?, ?, ?)",
                (city, date, temperature, humidity, alert_level),
            )

    def fetch_all(self):
        with self._connect() as conn:
            return conn.execute(
                "SELECT id, city, date, temperature, humidity, alert_level "
                "FROM records ORDER BY date DESC"
            ).fetchall()

    def search(self, query):
        like = f"%{query}%"
        with self._connect() as conn:
            return conn.execute(
                "SELECT id, city, date, temperature, humidity, alert_level "
                "FROM records WHERE city LIKE ? OR date LIKE ? OR alert_level LIKE ? "
                "ORDER BY date DESC",
                (like, like, like),
            ).fetchall()

    def update(self, record_id, city, date, temperature, humidity, alert_level):
        with self._connect() as conn:
            conn.execute(
                "UPDATE records SET city=?, date=?, temperature=?, humidity=?, alert_level=? "
                "WHERE id=?",
                (city, date, temperature, humidity, alert_level, record_id),
            )

    def delete(self, record_id):
        with self._connect() as conn:
            conn.execute("DELETE FROM records WHERE id=?", (record_id,))

    def get_stats(self):
        with self._connect() as conn:
            return conn.execute("""
                SELECT
                    COUNT(*)                                              AS total,
                    ROUND(AVG(temperature), 1)                           AS avg_temp,
                    MAX(temperature)                                      AS max_temp,
                    COUNT(CASE WHEN alert_level != 'NORMAL' THEN 1 END)  AS events
                FROM records
            """).fetchone()
