import sqlite3
import os

db_path = 'plattera.db'

def setup_admin():
    conn = sqlite3.connect(db_path)
    # Check if admin exists
    res = conn.execute("SELECT * FROM users WHERE u_email = 'admin@plattera.com'").fetchone()
    
    if res:
        conn.execute("UPDATE users SET u_role = 'admin', approval_status = 'Approved' WHERE u_email = 'admin@plattera.com'")
        print("Updated existing user to Admin.")
    else:
        # Create fresh admin (Password will be 'admin123' - plain for now as per your auth.py flexibility)
        conn.execute("""
            INSERT INTO users (u_name, first_name, last_name, u_email, phone_number, u_password, u_role, approval_status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, ('System Admin', 'Admin', 'User', 'admin@plattera.com', '0000000000', 'admin123', 'admin', 'Approved'))
        print("Created new Admin account: admin@plattera.com / admin123")
    
    conn.commit()
    conn.close()

if __name__ == "__main__":
    setup_admin()
