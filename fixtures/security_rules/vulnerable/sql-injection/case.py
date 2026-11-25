# Static analysis fixture only. Never import or execute this file.
import sqlite3
from flask import request
def lookup(cursor):
    name = request.args.get("name")
    statement = "SELECT * FROM users WHERE name = '" + name + "'"
    # ruleid: codely.python.sql-injection
    cursor.execute(statement)
