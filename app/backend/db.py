import mysql.connector
import os

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
