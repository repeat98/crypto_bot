import sqlite3
import threading

class PortfolioManager:
    def __init__(self, db_path):
        self.db_path = db_path
        self._local = threading.local()
        self._create_table()

    def _get_connection(self):
        """Get a thread-local database connection"""
        if not hasattr(self._local, 'conn'):
            self._local.conn = sqlite3.connect(self.db_path)
        return self._local.conn

    def _create_table(self):
        conn = self._get_connection()
        c = conn.cursor()
        c.execute("""
        CREATE TABLE IF NOT EXISTS holdings (
          user_id INTEGER,
          symbol TEXT,
          amount REAL,
          PRIMARY KEY(user_id, symbol)
        )""")
        conn.commit()

    def add(self, user_id, symbol, amount):
        conn = self._get_connection()
        c = conn.cursor()
        c.execute("""
        INSERT INTO holdings(user_id, symbol, amount)
        VALUES (?, ?, ?)
        ON CONFLICT(user_id, symbol) DO UPDATE SET amount = amount + excluded.amount
        """, (user_id, symbol, amount))
        conn.commit()

    def remove(self, user_id, symbol, amount):
        conn = self._get_connection()
        c = conn.cursor()
        # Get current amount
        c.execute("SELECT amount FROM holdings WHERE user_id = ? AND symbol = ?", (user_id, symbol))
        result = c.fetchone()
        
        if not result:
            return False  # No holdings found
            
        current_amount = result[0]
        new_amount = current_amount - amount
        
        if new_amount < 0:
            return False  # Not enough holdings
            
        if new_amount == 0:
            c.execute("DELETE FROM holdings WHERE user_id = ? AND symbol = ?", (user_id, symbol))
        else:
            c.execute("""
            UPDATE holdings SET amount = ?
            WHERE user_id = ? AND symbol = ?
            """, (new_amount, user_id, symbol))
            
        conn.commit()
        return True

    def remove_all(self, user_id):
        """Remove all holdings for a user"""
        conn = self._get_connection()
        c = conn.cursor()
        c.execute("DELETE FROM holdings WHERE user_id = ?", (user_id,))
        conn.commit()
        return True

    def get(self, user_id):
        conn = self._get_connection()
        c = conn.cursor()
        c.execute("SELECT symbol, amount FROM holdings WHERE user_id = ?", (user_id,))
        return dict(c.fetchall())

    def list_users(self):
        conn = self._get_connection()
        c = conn.cursor()
        c.execute("SELECT DISTINCT user_id FROM holdings")
        return [row[0] for row in c.fetchall()]