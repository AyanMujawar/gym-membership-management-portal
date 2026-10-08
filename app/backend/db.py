import mysql.connector
import os
import re
from contextlib import contextmanager


# Connects to the MySQL database using settings from environment variables
def get_db_connection():
    connection = mysql.connector.connect(
        host=os.environ.get("DB_HOST", "localhost"),
        user=os.environ.get("DB_USER", "root"),
        password=os.environ.get("DB_PASSWORD", "password"),
        database=os.environ.get("DB_NAME", "gym_portal")
    )
    return connection


# Runs a SELECT and returns all rows as dicts (or just the first row / None if one=True)
def query(sql, params=(), one=False):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(sql, params)
        return cursor.fetchone() if one else cursor.fetchall()
    finally:
        cursor.close()
        conn.close()


# Runs an INSERT/UPDATE/DELETE, commits it, and returns the new row's id (for inserts)
def execute(sql, params=()):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(sql, params)
        conn.commit()
        return cursor.lastrowid
    finally:
        cursor.close()
        conn.close()


# Several statements that must succeed or fail together. Use as:
#     with transaction() as cursor:
#         cursor.execute(...)
# Everything is committed when the block ends, or rolled back if anything inside raises.
@contextmanager
def transaction():
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        yield cursor
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        cursor.close()
        conn.close()


_IDENTIFIER = re.compile(r"^[a-z_]+$")


# UPDATE one row from a {column: value} dict. The table and column names come from fixed
# whitelists in the calling routes and are checked again here; values are always passed
# as query parameters, never pasted into the SQL.
def update_row(table, key_column, key_value, updates):
    for name in (table, key_column, *updates):
        if not _IDENTIFIER.match(name):
            raise ValueError(f"unsafe SQL identifier: {name}")
    assignments = ", ".join(f"{column} = %s" for column in updates)
    # Safe: every identifier was checked against _IDENTIFIER above and the values stay parameters
    sql = f"UPDATE {table} SET {assignments} WHERE {key_column} = %s"  # nosec B608
    return execute(sql, (*updates.values(), key_value))
