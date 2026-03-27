import sqlite3
import os

DATABASE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'plattera.db')

def migrate():
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    
    # Create coupons table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS coupons (
            cp_id INTEGER PRIMARY KEY AUTOINCREMENT,
            cp_code TEXT UNIQUE NOT NULL,
            cp_discount_perc INTEGER NOT NULL,
            cp_status TEXT DEFAULT 'active',
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Insert default coupons from the spin wheel
    default_coupons = [
        ('PLATTERA10', 10),
        ('FREESHIP', 0), # Special handling for free ship
        ('PLATTERA20', 20),
        ('WELCOME05', 5),
        ('GIFTSTITCH', 0) # Special gift
    ]
    for code, disc in default_coupons:
        try:
            cursor.execute('INSERT INTO coupons (cp_code, cp_discount_perc) VALUES (?, ?)', (code, disc))
        except sqlite3.IntegrityError:
            pass # Already exists
            
    conn.commit()
    conn.close()
    print("Migration successful: Coupons table created and populated.")

if __name__ == '__main__':
    migrate()
