# Static fullstack demo fixture only. Never import or execute.
import sqlite3
from flask import request


class OrderRepository:
    def query_orders(self, status: str):
        user_filter = request.args.get('status')
        sql = "SELECT id FROM orders WHERE status = '" + user_filter + "'"
        conn = sqlite3.connect('orders.db')
        return conn.execute(sql)
