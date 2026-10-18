#!/usr/bin/env python3
"""
PostgreSQL e-commerce schema + sample-data seeder.

Usage:
  pip install "psycopg2-binary>=2.9"
  python ecommerce_seeder.py

You will be prompted for the existing database name and PostgreSQL connection details.
The script creates tables in the public schema and inserts linked demo data.
It does NOT drop existing tables. It refuses to seed if its core tables already contain
rows, preventing accidental duplicate demo data.
"""
import getpass
import random
import sys
from decimal import Decimal
from datetime import datetime, timedelta, timezone

import psycopg2
from psycopg2.extras import execute_values

random.seed()

DDL = """
CREATE TABLE IF NOT EXISTS customers (
    customer_id BIGSERIAL PRIMARY KEY,
    first_name VARCHAR(80) NOT NULL,
    last_name VARCHAR(80) NOT NULL,
    email VARCHAR(255) NOT NULL UNIQUE,
    phone VARCHAR(30),
    password_hash TEXT NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS customer_addresses (
    address_id BIGSERIAL PRIMARY KEY,
    customer_id BIGINT NOT NULL REFERENCES customers(customer_id) ON DELETE CASCADE,
    address_type VARCHAR(20) NOT NULL CHECK (address_type IN ('shipping','billing','both')),
    recipient_name VARCHAR(160) NOT NULL,
    line1 VARCHAR(255) NOT NULL,
    line2 VARCHAR(255),
    city VARCHAR(100) NOT NULL,
    state VARCHAR(100) NOT NULL,
    postal_code VARCHAR(20) NOT NULL,
    country VARCHAR(100) NOT NULL DEFAULT 'India',
    is_default BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS categories (
    category_id BIGSERIAL PRIMARY KEY,
    name VARCHAR(120) NOT NULL UNIQUE,
    slug VARCHAR(140) NOT NULL UNIQUE,
    description TEXT
);

CREATE TABLE IF NOT EXISTS brands (
    brand_id BIGSERIAL PRIMARY KEY,
    name VARCHAR(120) NOT NULL UNIQUE,
    website VARCHAR(255)
);

CREATE TABLE IF NOT EXISTS products (
    product_id BIGSERIAL PRIMARY KEY,
    category_id BIGINT NOT NULL REFERENCES categories(category_id),
    brand_id BIGINT REFERENCES brands(brand_id),
    name VARCHAR(200) NOT NULL,
    slug VARCHAR(220) NOT NULL UNIQUE,
    description TEXT,
    sku VARCHAR(80) NOT NULL UNIQUE,
    price NUMERIC(12,2) NOT NULL CHECK (price >= 0),
    compare_at_price NUMERIC(12,2) CHECK (compare_at_price IS NULL OR compare_at_price >= price),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS product_images (
    image_id BIGSERIAL PRIMARY KEY,
    product_id BIGINT NOT NULL REFERENCES products(product_id) ON DELETE CASCADE,
    image_url TEXT NOT NULL,
    alt_text VARCHAR(255),
    sort_order INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS inventory (
    inventory_id BIGSERIAL PRIMARY KEY,
    product_id BIGINT NOT NULL UNIQUE REFERENCES products(product_id) ON DELETE CASCADE,
    quantity INTEGER NOT NULL DEFAULT 0 CHECK (quantity >= 0),
    reserved_quantity INTEGER NOT NULL DEFAULT 0 CHECK (reserved_quantity >= 0 AND reserved_quantity <= quantity),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS coupons (
    coupon_id BIGSERIAL PRIMARY KEY,
    code VARCHAR(40) NOT NULL UNIQUE,
    discount_type VARCHAR(20) NOT NULL CHECK (discount_type IN ('percent','fixed')),
    discount_value NUMERIC(10,2) NOT NULL CHECK (discount_value > 0),
    min_order_amount NUMERIC(12,2) NOT NULL DEFAULT 0,
    starts_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMPTZ NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE IF NOT EXISTS orders (
    order_id BIGSERIAL PRIMARY KEY,
    order_number VARCHAR(40) NOT NULL UNIQUE,
    customer_id BIGINT NOT NULL REFERENCES customers(customer_id),
    shipping_address_id BIGINT REFERENCES customer_addresses(address_id),
    coupon_id BIGINT REFERENCES coupons(coupon_id),
    status VARCHAR(30) NOT NULL CHECK (status IN ('pending','confirmed','processing','shipped','delivered','cancelled','refunded')),
    subtotal NUMERIC(12,2) NOT NULL CHECK (subtotal >= 0),
    discount_amount NUMERIC(12,2) NOT NULL DEFAULT 0 CHECK (discount_amount >= 0),
    tax_amount NUMERIC(12,2) NOT NULL DEFAULT 0 CHECK (tax_amount >= 0),
    shipping_amount NUMERIC(12,2) NOT NULL DEFAULT 0 CHECK (shipping_amount >= 0),
    total_amount NUMERIC(12,2) NOT NULL CHECK (total_amount >= 0),
    currency CHAR(3) NOT NULL DEFAULT 'INR',
    placed_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS order_items (
    order_item_id BIGSERIAL PRIMARY KEY,
    order_id BIGINT NOT NULL REFERENCES orders(order_id) ON DELETE CASCADE,
    product_id BIGINT NOT NULL REFERENCES products(product_id),
    product_name VARCHAR(200) NOT NULL,
    sku VARCHAR(80) NOT NULL,
    unit_price NUMERIC(12,2) NOT NULL CHECK (unit_price >= 0),
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    line_total NUMERIC(12,2) NOT NULL CHECK (line_total >= 0)
);

CREATE TABLE IF NOT EXISTS payments (
    payment_id BIGSERIAL PRIMARY KEY,
    order_id BIGINT NOT NULL UNIQUE REFERENCES orders(order_id) ON DELETE CASCADE,
    provider VARCHAR(50) NOT NULL,
    transaction_reference VARCHAR(100) UNIQUE,
    amount NUMERIC(12,2) NOT NULL CHECK (amount >= 0),
    status VARCHAR(30) NOT NULL CHECK (status IN ('pending','authorized','paid','failed','refunded')),
    paid_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS shipments (
    shipment_id BIGSERIAL PRIMARY KEY,
    order_id BIGINT NOT NULL UNIQUE REFERENCES orders(order_id) ON DELETE CASCADE,
    carrier VARCHAR(100),
    tracking_number VARCHAR(100) UNIQUE,
    status VARCHAR(30) NOT NULL CHECK (status IN ('not_shipped','packed','shipped','in_transit','delivered','returned')),
    shipped_at TIMESTAMPTZ,
    delivered_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS reviews (
    review_id BIGSERIAL PRIMARY KEY,
    customer_id BIGINT NOT NULL REFERENCES customers(customer_id) ON DELETE CASCADE,
    product_id BIGINT NOT NULL REFERENCES products(product_id) ON DELETE CASCADE,
    order_id BIGINT REFERENCES orders(order_id) ON DELETE SET NULL,
    rating SMALLINT NOT NULL CHECK (rating BETWEEN 1 AND 5),
    title VARCHAR(160),
    review_text TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (customer_id, product_id)
);

CREATE TABLE IF NOT EXISTS wishlists (
    wishlist_id BIGSERIAL PRIMARY KEY,
    customer_id BIGINT NOT NULL UNIQUE REFERENCES customers(customer_id) ON DELETE CASCADE,
    name VARCHAR(120) NOT NULL DEFAULT 'My Wishlist',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS wishlist_items (
    wishlist_id BIGINT NOT NULL REFERENCES wishlists(wishlist_id) ON DELETE CASCADE,
    product_id BIGINT NOT NULL REFERENCES products(product_id) ON DELETE CASCADE,
    added_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (wishlist_id, product_id)
);

CREATE INDEX IF NOT EXISTS idx_products_category ON products(category_id);
CREATE INDEX IF NOT EXISTS idx_orders_customer ON orders(customer_id);
CREATE INDEX IF NOT EXISTS idx_orders_placed_at ON orders(placed_at);
CREATE INDEX IF NOT EXISTS idx_order_items_order ON order_items(order_id);
CREATE INDEX IF NOT EXISTS idx_reviews_product ON reviews(product_id);
"""

FIRST_NAMES = ["Aarav", "Vivaan", "Aditya", "Vihaan", "Arjun", "Sai", "Ishaan", "Rohan", "Anaya", "Diya", "Aadhya", "Ira", "Meera", "Priya", "Kavya", "Neha", "Anika", "Sana", "Rahul", "Karan"]
LAST_NAMES = ["Sharma", "Patel", "Verma", "Singh", "Gupta", "Kumar", "Mehta", "Joshi", "Nair", "Reddy", "Iyer", "Das", "Shah", "Kulkarni"]
CITIES = [
    ("Pune", "Maharashtra", "411001"), ("Mumbai", "Maharashtra", "400001"),
    ("Bengaluru", "Karnataka", "560001"), ("Hyderabad", "Telangana", "500001"),
    ("Delhi", "Delhi", "110001"), ("Jaipur", "Rajasthan", "302001"),
    ("Chennai", "Tamil Nadu", "600001"), ("Ahmedabad", "Gujarat", "380001")
]
CATALOG = {
    "Electronics": [
        ("Wireless Bluetooth Headphones", "Audio", 2499),
        ("Portable Bluetooth Speaker", "SoundPeak", 1799),
        ("USB-C Fast Charger", "Voltix", 899),
        ("Smart Fitness Watch", "TimeLoop", 3299),
        ("Wireless Mouse", "ClickPro", 699),
    ],
    "Fashion": [
        ("Classic Cotton T-Shirt", "UrbanThread", 599),
        ("Everyday Running Shoes", "Stride", 2199),
        ("Casual Backpack", "CarryOn", 1499),
        ("Denim Jeans", "BlueStreet", 1799),
        ("Analog Wrist Watch", "TimeLoop", 1299),
    ],
    "Home & Kitchen": [
        ("Stainless Steel Water Bottle", "HomeNest", 499),
        ("Non-stick Frying Pan", "KitchenCraft", 1099),
        ("Cotton Bedsheet Set", "HomeNest", 1599),
        ("LED Desk Lamp", "BrightHome", 999),
        ("Storage Container Set", "KitchenCraft", 799),
    ],
    "Books": [
        ("Python Programming Guide", "TechReads", 699),
        ("Practical SQL Handbook", "TechReads", 549),
        ("The Daily Productivity Journal", "PaperTrail", 399),
        ("Beginner's Data Science", "TechReads", 799),
        ("Short Stories Collection", "PaperTrail", 349),
    ],
}

def slugify(value):
    return "-".join("".join(ch.lower() if ch.isalnum() else " " for ch in value).split())

def ask(prompt, default):
    value = input(f"{prompt} [{default}]: ").strip()
    return value or default

def main():
    print("\\n=== PostgreSQL E-commerce Seeder ===")
    dbname = input("Existing database name: ").strip()
    if not dbname:
        print("Database name is required.")
        sys.exit(1)
    host = ask("Host", "localhost")
    port = ask("Port", "5432")
    user = ask("Username", "postgres")
    password = getpass.getpass("Password (input hidden): ")
    customer_count = int(ask("Number of demo customers", "20"))
    order_count = int(ask("Number of demo orders", "35"))
    if customer_count < 2 or order_count < 1:
        print("Use at least 2 customers and 1 order.")
        sys.exit(1)

    conn = psycopg2.connect(
        dbname=dbname, host=host, port=port, user=user, password=password,
        connect_timeout=10
    )
    try:
        conn.autocommit = False
        with conn.cursor() as cur:
            cur.execute(DDL)

            # Prevent accidental duplicate seeding. Schema creation is rolled back too if this fails.
            cur.execute("""
                SELECT
                  (SELECT COUNT(*) FROM customers),
                  (SELECT COUNT(*) FROM categories),
                  (SELECT COUNT(*) FROM products),
                  (SELECT COUNT(*) FROM orders)
            """)
            counts = cur.fetchone()
            if any(counts):
                raise RuntimeError(
                    "One or more core tables already contain data "
                    f"(customers/categories/products/orders = {counts}). "
                    "No data was added. Use a fresh empty database or adapt the script "
                    "to your existing schema."
                )

            # Categories and brands
            category_ids = {}
            for name in CATALOG:
                cur.execute(
                    "INSERT INTO categories(name, slug, description) VALUES (%s,%s,%s) RETURNING category_id",
                    (name, slugify(name), f"Products in the {name.lower()} category.")
                )
                category_ids[name] = cur.fetchone()[0]

            brand_names = sorted({brand for items in CATALOG.values() for _, brand, _ in items})
            brand_ids = {}
            for brand in brand_names:
                cur.execute(
                    "INSERT INTO brands(name, website) VALUES (%s,%s) RETURNING brand_id",
                    (brand, f"https://www.example.com/brands/{slugify(brand)}")
                )
                brand_ids[brand] = cur.fetchone()[0]

            product_ids = []
            product_info = {}
            for category, items in CATALOG.items():
                for name, brand, price in items:
                    sku = f"SKU-{len(product_ids)+1:05d}"
                    cur.execute("""
                        INSERT INTO products(category_id, brand_id, name, slug, description, sku, price, compare_at_price)
                        VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
                        RETURNING product_id
                    """, (category_ids[category], brand_ids[brand], name, slugify(name),
                          f"Demo product: {name}. Quality everyday item for testing an e-commerce application.",
                          sku, Decimal(price), Decimal(price * 1.2).quantize(Decimal("0.01"))))
                    pid = cur.fetchone()[0]
                    product_ids.append(pid)
                    product_info[pid] = (name, sku, Decimal(price))
                    cur.execute(
                        "INSERT INTO product_images(product_id,image_url,alt_text,sort_order) VALUES (%s,%s,%s,0)",
                        (pid, f"https://placehold.co/600x600?text={slugify(name)}", name)
                    )
                    cur.execute(
                        "INSERT INTO inventory(product_id,quantity,reserved_quantity) VALUES (%s,%s,0)",
                        (pid, random.randint(10, 150))
                    )

            # Coupons
            coupon_ids = []
            for code, dtype, value, minimum in [
                ("WELCOME10", "percent", Decimal("10"), Decimal("500")),
                ("SAVE200", "fixed", Decimal("200"), Decimal("1500")),
                ("FESTIVE15", "percent", Decimal("15"), Decimal("1000")),
            ]:
                cur.execute("""
                    INSERT INTO coupons(code,discount_type,discount_value,min_order_amount,starts_at,expires_at)
                    VALUES (%s,%s,%s,%s,NOW() - INTERVAL '30 days',NOW() + INTERVAL '365 days')
                    RETURNING coupon_id
                """, (code, dtype, value, minimum))
                coupon_ids.append((cur.fetchone()[0], dtype, value, minimum))

            # Customers, two addresses each, and one wishlist per customer
            customer_ids, address_ids, wishlist_ids = [], {}, {}
            for i in range(customer_count):
                first, last = random.choice(FIRST_NAMES), random.choice(LAST_NAMES)
                email = f"customer{i+1:03d}@example.com"
                cur.execute("""
                    INSERT INTO customers(first_name,last_name,email,phone,password_hash,created_at)
                    VALUES (%s,%s,%s,%s,%s,%s) RETURNING customer_id
                """, (first, last, email, f"+91{random.randint(6000000000,9999999999)}",
                      "DEMO_ONLY_NOT_A_REAL_PASSWORD_HASH",
                      datetime.now(timezone.utc) - timedelta(days=random.randint(1, 500))))
                cid = cur.fetchone()[0]
                customer_ids.append(cid)
                city, state, pin = random.choice(CITIES)
                customer_address_ids = []
                for addr_type in ("both", "shipping"):
                    cur.execute("""
                        INSERT INTO customer_addresses
                        (customer_id,address_type,recipient_name,line1,line2,city,state,postal_code,country,is_default)
                        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,'India',%s) RETURNING address_id
                    """, (cid, addr_type, f"{first} {last}", f"{random.randint(1,999)} {random.choice(['MG Road','Park Street','Lake View Road','Station Road','Market Lane'])}",
                          random.choice(["Apt 2B", "Flat 301", "Near City Park", None]),
                          city, state, pin, addr_type == "both"))
                    customer_address_ids.append(cur.fetchone()[0])
                address_ids[cid] = customer_address_ids
                cur.execute("INSERT INTO wishlists(customer_id,name) VALUES (%s,'My Wishlist') RETURNING wishlist_id", (cid,))
                wid = cur.fetchone()[0]
                wishlist_ids[cid] = wid
                for pid in random.sample(product_ids, k=random.randint(1, 4)):
                    cur.execute("INSERT INTO wishlist_items(wishlist_id,product_id) VALUES (%s,%s)", (wid, pid))

            # Orders, line items, payments, and shipment records
            order_statuses = ["confirmed", "processing", "shipped", "delivered", "cancelled", "pending"]
            for i in range(order_count):
                cid = random.choice(customer_ids)
                chosen = random.sample(product_ids, k=random.randint(1, 4))
                line_items = []
                subtotal = Decimal("0.00")
                for pid in chosen:
                    name, sku, price = product_info[pid]
                    qty = random.randint(1, 3)
                    line_total = (price * qty).quantize(Decimal("0.01"))
                    subtotal += line_total
                    line_items.append((pid, name, sku, price, qty, line_total))

                status = random.choice(order_statuses)
                coupon_id, discount = None, Decimal("0.00")
                eligible = [c for c in coupon_ids if subtotal >= c[3]]
                if eligible and random.random() < 0.3:
                    cp = random.choice(eligible)
                    coupon_id = cp[0]
                    discount = (subtotal * cp[2] / Decimal("100")).quantize(Decimal("0.01")) if cp[1] == "percent" else cp[2]
                    discount = min(discount, subtotal)
                tax = ((subtotal - discount) * Decimal("0.05")).quantize(Decimal("0.01"))
                shipping = Decimal("0.00") if subtotal >= Decimal("1500") else Decimal("79.00")
                total = subtotal - discount + tax + shipping
                placed_at = datetime.now(timezone.utc) - timedelta(days=random.randint(0, 180))
                cur.execute("""
                    INSERT INTO orders
                    (order_number,customer_id,shipping_address_id,coupon_id,status,subtotal,discount_amount,tax_amount,shipping_amount,total_amount,placed_at)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING order_id
                """, (f"ORD-{datetime.now().strftime('%Y%m%d')}-{i+1:05d}", cid,
                      random.choice(address_ids[cid]), coupon_id, status, subtotal, discount, tax, shipping, total, placed_at))
                oid = cur.fetchone()[0]
                for pid, name, sku, price, qty, line_total in line_items:
                    cur.execute("""
                        INSERT INTO order_items(order_id,product_id,product_name,sku,unit_price,quantity,line_total)
                        VALUES (%s,%s,%s,%s,%s,%s,%s)
                    """, (oid, pid, name, sku, price, qty, line_total))

                paid_status = "paid" if status in ("confirmed", "processing", "shipped", "delivered") else (
                    "refunded" if status == "refunded" else ("failed" if status == "cancelled" else "pending"))
                paid_at = placed_at + timedelta(minutes=random.randint(1, 60)) if paid_status in ("paid", "refunded") else None
                cur.execute("""
                    INSERT INTO payments(order_id,provider,transaction_reference,amount,status,paid_at)
                    VALUES (%s,%s,%s,%s,%s,%s)
                """, (oid, random.choice(["Razorpay", "Stripe", "PayPal", "Cash on Delivery"]),
                      f"TXN-{i+1:07d}", total, paid_status, paid_at))

                ship_status = {
                    "pending": "not_shipped", "confirmed": "packed", "processing": "packed",
                    "shipped": "shipped", "delivered": "delivered", "cancelled": "not_shipped",
                    "refunded": "returned"
                }[status]
                shipped_at = placed_at + timedelta(days=1) if ship_status in ("shipped", "delivered", "returned") else None
                delivered_at = shipped_at + timedelta(days=2) if ship_status == "delivered" and shipped_at else None
                cur.execute("""
                    INSERT INTO shipments(order_id,carrier,tracking_number,status,shipped_at,delivered_at)
                    VALUES (%s,%s,%s,%s,%s,%s)
                """, (oid, random.choice(["Delhivery", "Blue Dart", "India Post", "DTDC"]) if ship_status != "not_shipped" else None,
                      f"TRK-{i+1:07d}" if ship_status in ("packed", "shipped", "delivered", "returned") else None,
                      ship_status, shipped_at, delivered_at))

            # Reviews only for unique customer/product combinations; order link optional.
            used_reviews = set()
            for _ in range(min(customer_count * 2, len(customer_ids) * len(product_ids))):
                cid, pid = random.choice(customer_ids), random.choice(product_ids)
                if (cid, pid) in used_reviews:
                    continue
                used_reviews.add((cid, pid))
                cur.execute("""
                    INSERT INTO reviews(customer_id,product_id,rating,title,review_text)
                    VALUES (%s,%s,%s,%s,%s)
                    ON CONFLICT (customer_id,product_id) DO NOTHING
                """, (cid, pid, random.randint(3, 5),
                      random.choice(["Good quality", "Worth the price", "Happy with purchase", "Nice product"]),
                      random.choice(["Works as expected.", "Good value for money.", "Quality is good for everyday use.", "Delivery and packaging were fine."])))

        conn.commit()
        print("\\nSUCCESS: schema created and demo data inserted.")
        with conn.cursor() as cur:
            cur.execute("""
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema='public' AND table_type='BASE TABLE'
                ORDER BY table_name
            """)
            tables = [r[0] for r in cur.fetchall()]
            print("\\nTables in public schema:")
            for table in tables:
                cur.execute(f'SELECT COUNT(*) FROM public."{table}"')
                print(f"  {table}: {cur.fetchone()[0]} rows")
        print("\\nDemo emails: customer001@example.com, customer002@example.com, ...")
        print("Demo password_hash values are placeholders, not usable login credentials.")
    except Exception as exc:
        conn.rollback()
        print(f"\\nERROR: {exc}")
        print("The transaction was rolled back; no partial schema/data changes were committed.")
        sys.exit(1)
    finally:
        conn.close()

if __name__ == "__main__":
    main()
