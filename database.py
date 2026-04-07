import sqlite3
import os

DB_NAME = "ecommerce.db"

def init_db():
    if os.path.exists(DB_NAME):
        print(f"Database {DB_NAME} already exists. Skipping initialization.")
        return

    print("Initializing demo database...")
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    # Create tables
    cursor.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            signup_date DATE NOT NULL
        );

        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            category TEXT NOT NULL,
            price REAL NOT NULL
        );

        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            order_date DATE NOT NULL,
            total_amount REAL NOT NULL,
            status TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users (id)
        );

        CREATE TABLE IF NOT EXISTS order_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id INTEGER,
            product_id INTEGER,
            quantity INTEGER NOT NULL,
            price_at_purchase REAL NOT NULL,
            FOREIGN KEY (order_id) REFERENCES orders (id),
            FOREIGN KEY (product_id) REFERENCES products (id)
        );
    """)

    # Insert sample data
    users = [
        ("Alice Smith", "alice@example.com", "2023-01-15"),
        ("Bob Johnson", "bob@example.com", "2023-02-20"),
        ("Charlie Brown", "charlie@example.com", "2023-03-10"),
        ("Diana Prince", "diana@example.com", "2023-04-05"),
        ("Evan Wright", "evan@example.com", "2023-05-12")
    ]
    cursor.executemany("INSERT INTO users (name, email, signup_date) VALUES (?, ?, ?)", users)

    products = [
        ("Laptop Pro", "Electronics", 1299.99),
        ("Wireless Mouse", "Electronics", 49.99),
        ("Mechanical Keyboard", "Electronics", 149.99),
        ("Coffee Maker", "Home Appliances", 89.99),
        ("Standing Desk", "Furniture", 399.99)
    ]
    cursor.executemany("INSERT INTO products (name, category, price) VALUES (?, ?, ?)", products)

    orders = [
        (1, "2023-06-01", 1349.98, "Delivered"),
        (2, "2023-06-15", 89.99, "Shipped"),
        (3, "2023-07-20", 399.99, "Processing"),
        (1, "2023-08-05", 149.99, "Delivered"),
        (4, "2023-08-10", 1299.99, "Delivered")
    ]
    cursor.executemany("INSERT INTO orders (user_id, order_date, total_amount, status) VALUES (?, ?, ?, ?)", orders)

    order_items = [
        (1, 1, 1, 1299.99),
        (1, 2, 1, 49.99),
        (2, 4, 1, 89.99),
        (3, 5, 1, 399.99),
        (4, 3, 1, 149.99),
        (5, 1, 1, 1299.99)
    ]
    cursor.executemany("INSERT INTO order_items (order_id, product_id, quantity, price_at_purchase) VALUES (?, ?, ?, ?)", order_items)

    conn.commit()
    conn.close()
    print("Demo database initialized with sample data.")

if __name__ == "__main__":
    init_db()
