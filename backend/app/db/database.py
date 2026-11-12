import sqlite3
import json
from pathlib import Path
from typing import Any, Dict, List, Optional
from app.config import settings


class Database:
    def __init__(self, db_path: str = settings.DATABASE_PATH):
        self.db_path = db_path
        self._init_db()

    def get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=15.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def _init_db(self):
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # Products table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS products (
                    id TEXT PRIMARY KEY,
                    data TEXT NOT NULL
                )
            """)
            
            # Orders table (for AG Grid history and audit)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS orders (
                    id TEXT PRIMARY KEY,
                    date TEXT NOT NULL,
                    total REAL NOT NULL,
                    data TEXT NOT NULL
                )
            """)
            
            # Cart table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS cart_items (
                    id TEXT PRIMARY KEY,
                    product_id TEXT NOT NULL,
                    quantity INTEGER NOT NULL,
                    variant TEXT NOT NULL
                )
            """)
            
            # Accessibility preferences table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS preferences (
                    id TEXT PRIMARY KEY,
                    data TEXT NOT NULL
                )
            """)
            
            # Timeline events table (Bryntum)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS timeline_events (
                    id TEXT PRIMARY KEY,
                    date TEXT NOT NULL,
                    category TEXT NOT NULL,
                    data TEXT NOT NULL
                )
            """)
            
            # Audit log / Confirmation events table (Structured, no raw audio)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS audit_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    details TEXT NOT NULL,
                    mode TEXT NOT NULL
                )
            """)

            # Saved Items (explicitly persisted products for later; separate from cart)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS saved_items (
                    saved_item_id TEXT PRIMARY KEY,
                    product_id TEXT NOT NULL UNIQUE,
                    saved_at TEXT NOT NULL,
                    data TEXT NOT NULL
                )
            """)

            # Saved Searches (explicitly persisted structured search intents)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS saved_searches (
                    saved_search_id TEXT PRIMARY KEY,
                    saved_at TEXT NOT NULL,
                    data TEXT NOT NULL
                )
            """)

            # Search History (lightweight bounded log of recent automatic searches)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS search_history (
                    history_id TEXT PRIMARY KEY,
                    searched_at TEXT NOT NULL,
                    data TEXT NOT NULL
                )
            """)

            # Subscriptions (PayPal Sandbox recurring agreements, separate from one-time orders)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS subscriptions (
                    subscription_id TEXT PRIMARY KEY,
                    created_at TEXT NOT NULL,
                    data TEXT NOT NULL
                )
            """)

            # PayPal Catalog/Plan cache (avoids creating duplicate Sandbox products/plans)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS paypal_catalog_cache (
                    offer_id TEXT PRIMARY KEY,
                    paypal_product_id TEXT NOT NULL,
                    paypal_plan_id TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)

            conn.commit()

    def save_product(self, product_dict: Dict[str, Any]):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT OR REPLACE INTO products (id, data) VALUES (?, ?)",
                (product_dict["id"], json.dumps(product_dict))
            )
            conn.commit()

    def get_product(self, product_id: str) -> Optional[Dict[str, Any]]:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT data FROM products WHERE id = ?", (product_id,))
            row = cursor.fetchone()
            if row:
                return json.loads(row["data"])
            return None

    def get_all_products(self) -> List[Dict[str, Any]]:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT data FROM products")
            rows = cursor.fetchall()
            return [json.loads(row["data"]) for row in rows]

    def save_order(self, order_dict: Dict[str, Any]):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT OR REPLACE INTO orders (id, date, total, data) VALUES (?, ?, ?, ?)",
                (order_dict["order_id"], order_dict["date"], order_dict["total"], json.dumps(order_dict))
            )
            conn.commit()

    def get_all_orders(self) -> List[Dict[str, Any]]:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT data FROM orders ORDER BY date DESC")
            rows = cursor.fetchall()
            return [json.loads(row["data"]) for row in rows]

    def log_audit_event(self, event_type: str, details: str, mode: str = "VOICE"):
        import datetime
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO audit_events (timestamp, event_type, details, mode) VALUES (?, ?, ?, ?)",
                (now, event_type, details, mode)
            )
            conn.commit()

    def get_recent_audit_events(self, limit: int = 50) -> List[Dict[str, Any]]:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT timestamp, event_type, details, mode FROM audit_events ORDER BY id DESC LIMIT ?", (limit,))
            rows = cursor.fetchall()
            return [dict(row) for row in rows]

    def save_timeline_event(self, event_dict: Dict[str, Any]):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT OR REPLACE INTO timeline_events (id, date, category, data) VALUES (?, ?, ?, ?)",
                (event_dict["id"], event_dict["date"], event_dict["category"], json.dumps(event_dict))
            )
            conn.commit()

    def get_all_timeline_events(self) -> List[Dict[str, Any]]:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT data FROM timeline_events ORDER BY date ASC")
            rows = cursor.fetchall()
            return [json.loads(row["data"]) for row in rows]

    def save_saved_item(self, item_dict: Dict[str, Any]):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO saved_items (saved_item_id, product_id, saved_at, data)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(product_id) DO UPDATE SET
                    saved_at = excluded.saved_at,
                    data = excluded.data
                """,
                (
                    item_dict["saved_item_id"],
                    item_dict["product_id"],
                    item_dict["saved_at"],
                    json.dumps(item_dict),
                ),
            )
            conn.commit()

    def get_all_saved_items(self) -> List[Dict[str, Any]]:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT data FROM saved_items ORDER BY saved_at DESC")
            return [json.loads(row["data"]) for row in cursor.fetchall()]

    def delete_saved_item(self, saved_item_id_or_product_id: str) -> bool:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "DELETE FROM saved_items WHERE saved_item_id = ? OR product_id = ?",
                (saved_item_id_or_product_id, saved_item_id_or_product_id),
            )
            conn.commit()
            return cursor.rowcount > 0

    def save_saved_search(self, search_dict: Dict[str, Any]):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT OR REPLACE INTO saved_searches (saved_search_id, saved_at, data) VALUES (?, ?, ?)",
                (search_dict["saved_search_id"], search_dict["saved_at"], json.dumps(search_dict)),
            )
            conn.commit()

    def get_all_saved_searches(self) -> List[Dict[str, Any]]:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT data FROM saved_searches ORDER BY saved_at DESC")
            return [json.loads(row["data"]) for row in cursor.fetchall()]

    def delete_saved_search(self, saved_search_id: str) -> bool:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "DELETE FROM saved_searches WHERE saved_search_id = ?",
                (saved_search_id,),
            )
            conn.commit()
            return cursor.rowcount > 0

    def record_search_history(self, entry_dict: Dict[str, Any], max_entries: int = 20):
        norm_query = (entry_dict.get("query") or "").strip().lower()
        norm_display = (entry_dict.get("display_query") or "").strip().lower()
        with self.get_connection() as conn:
            cursor = conn.cursor()
            # Deduplicate identical searches so repeated queries move to the top without clutter.
            cursor.execute("SELECT history_id, data FROM search_history")
            for row in cursor.fetchall():
                try:
                    existing = json.loads(row["data"])
                except Exception:
                    continue
                ex_q = (existing.get("query") or "").strip().lower()
                ex_d = (existing.get("display_query") or "").strip().lower()
                if (norm_query and ex_q == norm_query) or (norm_display and ex_d == norm_display):
                    cursor.execute("DELETE FROM search_history WHERE history_id = ?", (row["history_id"],))

            cursor.execute(
                "INSERT OR REPLACE INTO search_history (history_id, searched_at, data) VALUES (?, ?, ?)",
                (entry_dict["history_id"], entry_dict["searched_at"], json.dumps(entry_dict)),
            )
            cursor.execute(
                """
                DELETE FROM search_history
                WHERE history_id NOT IN (
                    SELECT history_id FROM search_history ORDER BY searched_at DESC LIMIT ?
                )
                """,
                (max_entries,),
            )
            conn.commit()

    def get_recent_search_history(self, limit: int = 25) -> List[Dict[str, Any]]:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT data FROM search_history ORDER BY searched_at DESC LIMIT ?",
                (limit,),
            )
            return [json.loads(row["data"]) for row in cursor.fetchall()]

    def clear_search_history(self):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM search_history")
            conn.commit()

    def save_subscription(self, sub_dict: Dict[str, Any]):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT OR REPLACE INTO subscriptions (subscription_id, created_at, data) VALUES (?, ?, ?)",
                (sub_dict["subscription_id"], sub_dict["created_at"], json.dumps(sub_dict)),
            )
            conn.commit()

    def get_subscription(self, subscription_id: str) -> Optional[Dict[str, Any]]:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT data FROM subscriptions WHERE subscription_id = ?",
                (subscription_id,),
            )
            row = cursor.fetchone()
            return json.loads(row["data"]) if row else None

    def get_all_subscriptions(self) -> List[Dict[str, Any]]:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT data FROM subscriptions ORDER BY created_at DESC")
            return [json.loads(row["data"]) for row in cursor.fetchall()]

    def get_paypal_catalog_cache(self, offer_id: str) -> Optional[Dict[str, str]]:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT offer_id, paypal_product_id, paypal_plan_id, updated_at FROM paypal_catalog_cache WHERE offer_id = ?",
                (offer_id,),
            )
            row = cursor.fetchone()
            return dict(row) if row else None

    def save_paypal_catalog_cache(self, offer_id: str, paypal_product_id: str, paypal_plan_id: str, updated_at: str):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT OR REPLACE INTO paypal_catalog_cache (offer_id, paypal_product_id, paypal_plan_id, updated_at) VALUES (?, ?, ?, ?)",
                (offer_id, paypal_product_id, paypal_plan_id, updated_at),
            )
            conn.commit()

    def clear_all(self):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM products")
            cursor.execute("DELETE FROM orders")
            cursor.execute("DELETE FROM cart_items")
            cursor.execute("DELETE FROM timeline_events")
            cursor.execute("DELETE FROM audit_events")
            cursor.execute("DELETE FROM saved_items")
            cursor.execute("DELETE FROM saved_searches")
            cursor.execute("DELETE FROM search_history")
            cursor.execute("DELETE FROM subscriptions")
            conn.commit()


db = Database()
