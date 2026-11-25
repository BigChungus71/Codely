# Static analysis fixture only. Never import or execute this file.
from flask import request
def lookup(cursor):
    name = request.args.get("name")
    cursor.execute("SELECT * FROM users WHERE name = ?", (name,))
