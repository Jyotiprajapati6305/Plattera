import sqlite3

def add_images():
    conn = sqlite3.connect('plattera.db')
    c = conn.cursor()

    # Get all products that have only 1 image or no image
    c.execute('''
        SELECT p_id FROM products
    ''')
    products = c.fetchall()

    dummy_images = [
        "https://images.unsplash.com/photo-1629853926662-f7034b07c87c?w=800&q=80",
        "https://images.unsplash.com/photo-1596461404969-9ce20c718cbf?w=800&q=80",
        "https://images.unsplash.com/photo-1621531070503-431ea67b57b9?w=800&q=80"
    ]

    for (p_id,) in products:
        c.execute('SELECT COUNT(*) FROM product_images WHERE p_id = ?', (p_id,))
        count = c.fetchone()[0]

        if count < 3:
            for i in range(count, 3):
                c.execute('INSERT INTO product_images (p_id, image_url) VALUES (?, ?)', (p_id, dummy_images[i]))

    conn.commit()
    conn.close()
    print("Dummy images added successfully!")

if __name__ == '__main__':
    add_images()
