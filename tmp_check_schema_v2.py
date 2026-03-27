import sqlite3
import os

db_path = 'plattera.db'

def check_schema():
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    print("--- Table: cart ---")
    cursor.execute("PRAGMA table_info(cart)")
    rows = cursor.fetchall()
    for row in rows:
        print(dict(row))
        
    print("\n--- Table: products ---")
    cursor.execute("PRAGMA table_info(products)")
    rows = cursor.fetchall()
    for row in rows:
        print(dict(row))
        
    print("\n--- Table: users ---")
    cursor.execute("PRAGMA table_info(users)")
    rows = cursor.fetchall()
    for row in rows:
        print(dict(row))
        
    conn.close()

if __name__ == "__main__":
    check_schema()
