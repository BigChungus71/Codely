# Static analysis fixture only. Never import or execute this file.
def query(cursor):
    name = input("Name: ")
    sql = f"SELECT id FROM users WHERE name = '{name}'"
    # ruleid: codely.python.sql-injection
    cursor.execute(sql)
