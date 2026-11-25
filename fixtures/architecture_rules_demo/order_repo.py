# Static architecture rules fixture only. Never import or execute.
import sqlite3


class OrderRepository:
    def fetch_all(self):
        conn = sqlite3.connect('demo.db')
        return conn.execute('SELECT id FROM orders').fetchall()
