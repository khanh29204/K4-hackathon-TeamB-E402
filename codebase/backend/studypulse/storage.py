"""
=============================================================================
STUDYPULSE AI — SQLITE PHYSICAL STORAGE
=============================================================================
Persistent SQLite storage for timeline items and evidence entries.
Enables external dashboard integration and data survival across restarts.
=============================================================================
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
from datetime import datetime
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════
# TABLE SCHEMAS
# ═══════════════════════════════════════════════════════════════════════════

_CREATE_TIMELINE_TABLE = """
CREATE TABLE IF NOT EXISTS timeline_items (
    id TEXT PRIMARY KEY,
    category TEXT NOT NULL DEFAULT 'other',
    title TEXT NOT NULL,
    description TEXT DEFAULT '',
    due_date TEXT,
    due_time TEXT,
    priority TEXT DEFAULT 'medium',
    confidence_score REAL DEFAULT 0.0,
    source_platform TEXT DEFAULT 'direct_input',
    source_message_id TEXT DEFAULT '',
    language_detected TEXT DEFAULT 'vi',
    conflict_detected INTEGER DEFAULT 0,
    requires_clarification INTEGER DEFAULT 0,
    meeting_link TEXT DEFAULT NULL,
    naming_convention TEXT DEFAULT NULL,
    required_materials TEXT DEFAULT NULL,
    alert_sent INTEGER DEFAULT 0,
    created_at TEXT NOT NULL,
    raw_json TEXT NOT NULL
);
"""

_CREATE_EVIDENCE_TABLE = """
CREATE TABLE IF NOT EXISTS evidence_entries (
    id TEXT PRIMARY KEY,
    respondent_email_masked TEXT NOT NULL,
    survey_question TEXT NOT NULL,
    verbatim_text TEXT NOT NULL,
    language_detected TEXT DEFAULT 'vi',
    source TEXT DEFAULT 'direct_input',
    pii_masked_fields TEXT DEFAULT '[]',
    created_at TEXT NOT NULL,
    raw_json TEXT NOT NULL
);
"""

_CREATE_TOKEN_USAGE_TABLE = """
CREATE TABLE IF NOT EXISTS token_usage_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    node_name TEXT NOT NULL,
    thread_id TEXT DEFAULT '',
    input_tokens INTEGER DEFAULT 0,
    output_tokens INTEGER DEFAULT 0,
    total_tokens INTEGER DEFAULT 0,
    model_name TEXT DEFAULT '',
    timestamp TEXT NOT NULL
);
"""


class StudyPulseDB:
    """
    SQLite-backed persistent storage for StudyPulse AI data.
    
    Tables:
    - timeline_items: Academic deadlines, schedules, assignments
    - evidence_entries: Verbatim survey/feedback responses
    - token_usage_log: LLM token consumption tracking
    """

    def __init__(self, db_path: Optional[str] = None):
        if db_path is None:
            db_path = os.environ.get(
                "STUDYPULSE_DB_PATH",
                os.path.join(os.path.dirname(__file__), "..", "studypulse_data.sqlite")
            )
        self._db_path = os.path.abspath(db_path)
        self._conn: Optional[sqlite3.Connection] = None
        self._init_db()

    def _init_db(self):
        """Create tables if they don't exist."""
        try:
            self._conn = sqlite3.connect(self._db_path, check_same_thread=False)
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA journal_mode=WAL;")
            self._conn.execute(_CREATE_TIMELINE_TABLE)
            self._conn.execute(_CREATE_EVIDENCE_TABLE)
            self._conn.execute(_CREATE_TOKEN_USAGE_TABLE)
            self._conn.commit()

            # Migration: Add new columns if they do not exist
            for col, col_type in [
                ("meeting_link", "TEXT DEFAULT NULL"),
                ("naming_convention", "TEXT DEFAULT NULL"),
                ("required_materials", "TEXT DEFAULT NULL"),
                ("alert_sent", "INTEGER DEFAULT 0"),
                ("user_id", "TEXT DEFAULT 'default_user'"),
            ]:
                try:
                    self._conn.execute(f"ALTER TABLE timeline_items ADD COLUMN {col} {col_type};")
                    self._conn.commit()
                except sqlite3.OperationalError:
                    pass  # Column already exists

            logger.info(f"StudyPulseDB initialized at: {self._db_path}")
        except Exception as e:
            logger.error(f"Failed to initialize StudyPulseDB: {e}")
            self._conn = None

    def _ensure_conn(self) -> bool:
        """Check and reconnect if needed."""
        if self._conn is None:
            self._init_db()
        return self._conn is not None

    # ── TIMELINE OPERATIONS ──

    def save_timeline_item(self, item: Dict[str, Any], user_id: Optional[str] = None) -> bool:
        """
        Persist a timeline item to SQLite.
        Uses INSERT OR REPLACE to handle updates. Supports multi-tenant user_id.
        """
        if not self._ensure_conn():
            return False

        try:
            uid = user_id or item.get("user_id") or "default_user"
            item["user_id"] = uid
            alert_sent = item.get("alert_sent", 0)
            if not alert_sent:
                try:
                    cursor = self._conn.execute("SELECT alert_sent FROM timeline_items WHERE id = ?", (item.get("id", ""),))
                    row = cursor.fetchone()
                    if row:
                        alert_sent = row[0]
                except Exception:
                    pass

            self._conn.execute(
                """INSERT OR REPLACE INTO timeline_items 
                   (id, category, title, description, due_date, due_time, 
                    priority, confidence_score, source_platform, source_message_id,
                    language_detected, conflict_detected, requires_clarification,
                    meeting_link, naming_convention, required_materials, alert_sent, user_id,
                    created_at, raw_json)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    item.get("id", ""),
                    item.get("category", "other"),
                    item.get("title", ""),
                    item.get("description", ""),
                    item.get("due_date"),
                    item.get("due_time"),
                    item.get("priority", "medium"),
                    item.get("confidence_score", 0.0),
                    item.get("source_platform", "direct_input"),
                    item.get("source_message_id", ""),
                    item.get("language_detected", "vi"),
                    1 if item.get("conflict_detected") else 0,
                    1 if item.get("requires_clarification") else 0,
                    item.get("meeting_link"),
                    item.get("naming_convention"),
                    item.get("required_materials"),
                    alert_sent,
                    uid,
                    item.get("timestamp", datetime.utcnow().isoformat()),
                    json.dumps(item, ensure_ascii=False, default=str),
                ),
            )
            self._conn.commit()
            logger.info(f"Saved timeline item for user {uid}: {item.get('title', 'N/A')}")
            return True
        except Exception as e:
            logger.error(f"Failed to save timeline item: {e}")
            return False

    def save_timeline_items(self, items: List[Dict[str, Any]], user_id: Optional[str] = None) -> int:
        """Batch save timeline items. Returns count of successfully saved items."""
        saved = 0
        for item in items:
            if self.save_timeline_item(item, user_id=user_id):
                saved += 1
        return saved

    def get_all_timeline(self, user_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """Retrieve all timeline items from SQLite, filtered by user_id if provided."""
        if not self._ensure_conn():
            return []

        try:
            if user_id:
                cursor = self._conn.execute(
                    "SELECT raw_json FROM timeline_items WHERE user_id = ? OR user_id = 'default_user' ORDER BY due_date ASC",
                    (user_id,)
                )
            else:
                cursor = self._conn.execute(
                    "SELECT raw_json FROM timeline_items ORDER BY due_date ASC"
                )
            return [json.loads(row[0]) for row in cursor.fetchall()]
        except Exception as e:
            logger.error(f"Failed to read timeline items: {e}")
            return []

    def get_timeline_count(self) -> int:
        """Get total number of timeline items."""
        if not self._ensure_conn():
            return 0
        try:
            cursor = self._conn.execute("SELECT COUNT(*) FROM timeline_items")
            return cursor.fetchone()[0]
        except Exception:
            return 0

    def get_timeline_item(self, item_id: str) -> Optional[Dict[str, Any]]:
        """Single item by id, for the FE's edit/feedback/calendar actions."""
        if not self._ensure_conn():
            return None
        try:
            cursor = self._conn.execute("SELECT raw_json FROM timeline_items WHERE id = ?", (item_id,))
            row = cursor.fetchone()
            return json.loads(row[0]) if row else None
        except Exception as e:
            logger.error(f"Failed to read timeline item {item_id}: {e}")
            return None

    def update_timeline_item(self, item_id: str, patch: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Merge `patch` into the stored item and re-save (INSERT OR REPLACE
        keeps both the individual columns and raw_json in sync)."""
        item = self.get_timeline_item(item_id)
        if item is None:
            return None
        item.update(patch)
        if not self.save_timeline_item(item):
            return None
        return item

    def delete_timeline_item(self, item_id: str) -> bool:
        """Used by the FE's 'mark incorrect' feedback action — removes the
        item outright rather than just flagging it, matching the old
        in-memory timeline_store's behavior."""
        if not self._ensure_conn():
            return False
        try:
            cursor = self._conn.execute("DELETE FROM timeline_items WHERE id = ?", (item_id,))
            self._conn.commit()
            return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"Failed to delete timeline item {item_id}: {e}")
            return False

    def get_pending_alerts(self, window_minutes: int = 10) -> List[Dict[str, Any]]:
        """Find items due within window_minutes from now that haven't been alerted."""
        if not self._ensure_conn():
            return []
        try:
            cursor = self._conn.execute(
                "SELECT raw_json FROM timeline_items WHERE alert_sent = 0 AND due_date IS NOT NULL"
            )
            now = datetime.utcnow()
            results = []
            for row in cursor.fetchall():
                item = json.loads(row[0])
                due_date_str = item.get("due_date")
                if not due_date_str:
                    continue
                try:
                    dt_str = due_date_str.strip()
                    if dt_str.endswith("Z"):
                        dt_str = dt_str[:-1]
                    
                    has_tz = False
                    tz_offset = 0.0
                    if "T" in dt_str:
                        time_part = dt_str.split("T")[1]
                        if "+" in time_part:
                            has_tz = True
                            base_time, offset = time_part.split("+")
                            dt_str = dt_str.split("+")[0]
                            h, m = map(int, offset.split(":"))
                            tz_offset = h + m / 60.0
                        elif "-" in time_part:
                            has_tz = True
                            base_time, offset = time_part.split("-")
                            dt_str = dt_str.split("-")[0]
                            h, m = map(int, offset.split(":"))
                            tz_offset = -(h + m / 60.0)
                    
                    due_dt = datetime.fromisoformat(dt_str)
                    if has_tz:
                        due_dt = due_dt - timedelta(hours=tz_offset)
                    
                    diff_seconds = (due_dt - now).total_seconds()
                    # Trigger alert if the due date is within window (e.g. 0 to 10 minutes)
                    if 0 <= diff_seconds <= (window_minutes * 60):
                        results.append(item)
                except Exception as ex:
                    logger.error(f"Error parsing due_date {due_date_str}: {ex}")
            return results
        except Exception as e:
            logger.error(f"Failed to query pending alerts: {e}")
            return []

    def mark_alert_sent(self, item_id: str) -> bool:
        """Mark timeline item alert_sent to 1 to prevent double-alerts."""
        if not self._ensure_conn():
            return False
        try:
            cursor = self._conn.execute(
                "SELECT raw_json FROM timeline_items WHERE id = ?", (item_id,)
            )
            row = cursor.fetchone()
            if row:
                item = json.loads(row[0])
                item["alert_sent"] = 1
                self._conn.execute(
                    "UPDATE timeline_items SET alert_sent = 1, raw_json = ? WHERE id = ?",
                    (json.dumps(item, ensure_ascii=False, default=str), item_id)
                )
                self._conn.commit()
                logger.info(f"Marked alert_sent = 1 for item: {item_id}")
                return True
            return False
        except Exception as e:
            logger.error(f"Failed to mark alert sent: {e}")
            return False

    # ── EVIDENCE OPERATIONS ──

    def save_evidence_entry(self, entry: Dict[str, Any]) -> bool:
        """Persist a verbatim evidence entry to SQLite."""
        if not self._ensure_conn():
            return False

        try:
            pii_fields = entry.get("pii_masked_fields", [])
            if isinstance(pii_fields, list):
                pii_fields = json.dumps(pii_fields)

            self._conn.execute(
                """INSERT OR REPLACE INTO evidence_entries
                   (id, respondent_email_masked, survey_question, verbatim_text,
                    language_detected, source, pii_masked_fields, created_at, raw_json)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    entry.get("id", ""),
                    entry.get("respondent_email_masked", ""),
                    entry.get("survey_question", ""),
                    entry.get("verbatim_text", ""),
                    entry.get("language_detected", "vi"),
                    entry.get("source", "direct_input"),
                    pii_fields,
                    entry.get("timestamp", datetime.utcnow().isoformat()),
                    json.dumps(entry, ensure_ascii=False, default=str),
                ),
            )
            self._conn.commit()
            logger.info(f"Saved evidence entry: {entry.get('id', 'N/A')[:8]}...")
            return True
        except Exception as e:
            logger.error(f"Failed to save evidence entry: {e}")
            return False

    def get_all_evidence(self) -> List[Dict[str, Any]]:
        """Retrieve all evidence entries from SQLite."""
        if not self._ensure_conn():
            return []

        try:
            cursor = self._conn.execute(
                "SELECT raw_json FROM evidence_entries ORDER BY created_at DESC"
            )
            return [json.loads(row[0]) for row in cursor.fetchall()]
        except Exception as e:
            logger.error(f"Failed to read evidence entries: {e}")
            return []

    def get_evidence_count(self) -> int:
        """Get total number of evidence entries."""
        if not self._ensure_conn():
            return 0
        try:
            cursor = self._conn.execute("SELECT COUNT(*) FROM evidence_entries")
            return cursor.fetchone()[0]
        except Exception:
            return 0

    # ── TOKEN USAGE OPERATIONS ──

    def log_token_usage(
        self,
        node_name: str,
        input_tokens: int,
        output_tokens: int,
        model_name: str = "",
        thread_id: str = "",
    ) -> bool:
        """Log token usage for a single LLM call."""
        if not self._ensure_conn():
            return False

        try:
            self._conn.execute(
                """INSERT INTO token_usage_log
                   (node_name, thread_id, input_tokens, output_tokens, total_tokens,
                    model_name, timestamp)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    node_name,
                    thread_id,
                    input_tokens,
                    output_tokens,
                    input_tokens + output_tokens,
                    model_name,
                    datetime.utcnow().isoformat(),
                ),
            )
            self._conn.commit()
            return True
        except Exception as e:
            logger.error(f"Failed to log token usage: {e}")
            return False

    def get_total_token_usage(self) -> Dict[str, int]:
        """Get aggregated token usage across all calls."""
        if not self._ensure_conn():
            return {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}

        try:
            cursor = self._conn.execute(
                """SELECT COALESCE(SUM(input_tokens), 0) as input_total,
                          COALESCE(SUM(output_tokens), 0) as output_total,
                          COALESCE(SUM(total_tokens), 0) as grand_total
                   FROM token_usage_log"""
            )
            row = cursor.fetchone()
            return {
                "input_tokens": row[0],
                "output_tokens": row[1],
                "total_tokens": row[2],
            }
        except Exception:
            return {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}

    def close(self):
        """Close the database connection."""
        if self._conn:
            self._conn.close()
            self._conn = None


# ═══════════════════════════════════════════════════════════════════════════
# SINGLETON INSTANCE
# ═══════════════════════════════════════════════════════════════════════════

_db_instance: Optional[StudyPulseDB] = None


def get_db() -> StudyPulseDB:
    """Get or create the singleton StudyPulseDB instance."""
    global _db_instance
    if _db_instance is None:
        _db_instance = StudyPulseDB()
    return _db_instance
