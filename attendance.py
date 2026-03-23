"""
Attendance database module.
Handles all SQLite operations for attendance records and registered persons.
"""
import sqlite3
import os
import csv
import io
from datetime import datetime, timedelta
from config import DATABASE_PATH, SCAN_COOLDOWN_SECONDS


class AttendanceDB:
    def __init__(self, db_path=None):
        self.db_path = db_path or DATABASE_PATH
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self._init_db()

    def _get_conn(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        conn = self._get_conn()
        conn.execute('''
            CREATE TABLE IF NOT EXISTS attendance (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                date TEXT NOT NULL,
                time_in TEXT NOT NULL,
                direction TEXT DEFAULT 'IN',
                confidence REAL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        # Add direction column if upgrading from old schema
        try:
            conn.execute("ALTER TABLE attendance ADD COLUMN direction TEXT DEFAULT 'IN'")
        except sqlite3.OperationalError:
            pass  # Column already exists
        conn.execute('''
            CREATE TABLE IF NOT EXISTS registered_persons (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                num_photos INTEGER DEFAULT 0,
                registered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        conn.commit()
        conn.close()

    def mark_attendance(self, name, confidence=None):
        """
        Auto-alternating IN/OUT attendance.
        - First scan of the day  → IN
        - After cooldown, next   → OUT
        - After cooldown, next   → IN  ...

        Returns: (was_marked: bool, direction: str or None)
        """
        conn = self._get_conn()
        now = datetime.now()
        today = now.strftime("%Y-%m-%d")
        current_time = now.strftime("%H:%M:%S")

        # Get the most recent record for this person today
        last = conn.execute(
            "SELECT time_in, direction FROM attendance "
            "WHERE name = ? AND date = ? ORDER BY time_in DESC LIMIT 1",
            (name, today)
        ).fetchone()

        if last:
            # Parse the last scan time and check cooldown
            last_time = datetime.strptime(f"{today} {last['time_in']}", "%Y-%m-%d %H:%M:%S")
            elapsed = (now - last_time).total_seconds()

            if elapsed < SCAN_COOLDOWN_SECONDS:
                conn.close()
                return False, None  # Still in cooldown

            # Alternate direction
            direction = "OUT" if last["direction"] == "IN" else "IN"
        else:
            # First scan of the day
            direction = "IN"

        conn.execute(
            "INSERT INTO attendance (name, date, time_in, direction, confidence) VALUES (?, ?, ?, ?, ?)",
            (name, today, current_time, direction, confidence)
        )
        conn.commit()
        conn.close()
        return True, direction

    def get_today_attendance(self):
        """Get all attendance records for today."""
        conn = self._get_conn()
        today = datetime.now().strftime("%Y-%m-%d")
        rows = conn.execute(
            "SELECT * FROM attendance WHERE date = ? ORDER BY time_in DESC",
            (today,)
        ).fetchall()
        conn.close()
        return [dict(row) for row in rows]

    def get_attendance_by_date(self, date_str):
        """Get attendance records for a specific date (YYYY-MM-DD)."""
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT * FROM attendance WHERE date = ? ORDER BY time_in DESC",
            (date_str,)
        ).fetchall()
        conn.close()
        return [dict(row) for row in rows]

    def get_attendance_range(self, start_date, end_date):
        """Get attendance records between two dates."""
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT * FROM attendance WHERE date BETWEEN ? AND ? ORDER BY date DESC, time_in DESC",
            (start_date, end_date)
        ).fetchall()
        conn.close()
        return [dict(row) for row in rows]

    def get_stats(self):
        """Get summary statistics including IN/OUT counts."""
        conn = self._get_conn()
        today = datetime.now().strftime("%Y-%m-%d")

        today_count = conn.execute(
            "SELECT COUNT(DISTINCT name) as cnt FROM attendance WHERE date = ?",
            (today,)
        ).fetchone()["cnt"]

        today_in = conn.execute(
            "SELECT COUNT(*) as cnt FROM attendance WHERE date = ? AND direction = 'IN'",
            (today,)
        ).fetchone()["cnt"]

        today_out = conn.execute(
            "SELECT COUNT(*) as cnt FROM attendance WHERE date = ? AND direction = 'OUT'",
            (today,)
        ).fetchone()["cnt"]

        total_registered = conn.execute(
            "SELECT COUNT(*) as cnt FROM registered_persons"
        ).fetchone()["cnt"]

        total_records = conn.execute(
            "SELECT COUNT(*) as cnt FROM attendance"
        ).fetchone()["cnt"]

        conn.close()
        return {
            "today_present": today_count,
            "today_in": today_in,
            "today_out": today_out,
            "total_registered": total_registered,
            "total_records": total_records
        }

    def export_csv(self, start_date=None, end_date=None):
        """Export attendance records to CSV string."""
        conn = self._get_conn()
        if start_date and end_date:
            rows = conn.execute(
                "SELECT name, date, time_in, direction, confidence FROM attendance "
                "WHERE date BETWEEN ? AND ? ORDER BY date, time_in",
                (start_date, end_date)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT name, date, time_in, direction, confidence FROM attendance ORDER BY date, time_in"
            ).fetchall()
        conn.close()

        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["Name", "Date", "Time", "Direction", "Confidence"])
        for row in rows:
            conf = f"{row['confidence']:.2f}" if row["confidence"] else "N/A"
            writer.writerow([row["name"], row["date"], row["time_in"], row["direction"] or "IN", conf])
        return output.getvalue()

    def register_person(self, name, num_photos):
        """Add or update a registered person."""
        conn = self._get_conn()
        try:
            conn.execute(
                "INSERT OR REPLACE INTO registered_persons (name, num_photos) VALUES (?, ?)",
                (name, num_photos)
            )
            conn.commit()
        finally:
            conn.close()

    def get_registered_persons(self):
        """Get list of all registered persons."""
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT * FROM registered_persons ORDER BY name"
        ).fetchall()
        conn.close()
        return [dict(row) for row in rows]

    def delete_person(self, name):
        """Remove a person and their attendance records."""
        conn = self._get_conn()
        conn.execute("DELETE FROM registered_persons WHERE name = ?", (name,))
        conn.execute("DELETE FROM attendance WHERE name = ?", (name,))
        conn.commit()
        conn.close()
