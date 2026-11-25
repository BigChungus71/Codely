# Deliberately vulnerable static ASIM fixture. Never import or execute.
import sqlite3
from flask import request


class Repository:
    def lookup(self):
        username = request.args.get('username')
        statement = "SELECT name FROM records WHERE name = '" + username + "'"
        connection = sqlite3.connect('example.db')
        return connection.execute(statement)
