import sqlite3

conn = sqlite3.connect('bakery.db')
conn.row_factory = sqlite3.Row
cursor = conn.cursor()

# Get recent products with images
products = cursor.execute('''
    SELECT id, name, image_path, price, stock_qty, created_at 
    FROM product 
    WHERE image_path IS NOT NULL
    ORDER BY created_at DESC 
    LIMIT 5
''').fetchall()

print("Recent Products with Images:")
print("=" * 80)
for p in products:
    print(f"ID: {p['id']}")
    print(f"  Name: {p['name']}")
    print(f"  Image: {p['image_path']}")
    print(f"  Price: {p['price']}")
    print(f"  Stock: {p['stock_qty']}")
    print(f"  Created: {p['created_at']}")
    print()

conn.close()
