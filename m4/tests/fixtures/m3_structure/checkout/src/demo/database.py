# Static fixture: never import or execute.
import sqlite3 as sql


class Repository:
    def fetch(self, item_id):
        return item_id


def connect():
    return sql.connect(':memory:')
