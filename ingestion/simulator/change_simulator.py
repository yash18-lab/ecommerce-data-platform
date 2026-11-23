import os
import random
import uuid

import psycopg2
from dotenv import load_dotenv

load_dotenv()

# How many changes per run (override in .env if you like)
NEW_ORDERS = int(os.getenv("SIM_NEW_ORDERS", 50))
STATUS_UPDATES = int(os.getenv("SIM_STATUS_UPDATES", 100))
CANCELLATIONS = int(os.getenv("SIM_CANCELLATIONS", 5))
CUSTOMER_MOVES = int(os.getenv("SIM_CUSTOMER_MOVES", 20))
PRODUCT_UPDATES = int(os.getenv("SIM_PRODUCT_UPDATES", 10))
SOFT_DELETES = int(os.getenv("SIM_SOFT_DELETES", 5))


def get_connection():
    return psycopg2.connect(
        host=os.getenv("POSTGRES_HOST", "localhost"),
        port=os.getenv("POSTGRES_PORT", "5432"),
        dbname=os.getenv("POSTGRES_DB"),
        user=os.getenv("POSTGRES_USER"),
        password=os.getenv("POSTGRES_PASSWORD"),
    )


def new_id():
    return uuid.uuid4().hex  # 32 chars, same shape as Olist ids


def insert_new_orders(cur, n):
    """Clone random existing orders (with a new customer row, items, payments)."""
    cur.execute(
        "SELECT order_id, customer_id FROM orders "
        "WHERE is_deleted = FALSE ORDER BY random() LIMIT %s", (n,))
    for src_order, src_customer in cur.fetchall():
        oid, cid = new_id(), new_id()
        # same real person (customer_unique_id), new customer_id -> repeat customers
        cur.execute(
            "INSERT INTO customers (customer_id, customer_unique_id, "
            "customer_zip_code_prefix, customer_city, customer_state) "
            "SELECT %s, customer_unique_id, customer_zip_code_prefix, "
            "customer_city, customer_state FROM customers WHERE customer_id = %s",
            (cid, src_customer))
        cur.execute(
            "INSERT INTO orders (order_id, customer_id, order_status, "
            "order_purchase_timestamp, order_estimated_delivery_date) "
            "VALUES (%s, %s, 'created', NOW(), NOW() + INTERVAL '10 days')",
            (oid, cid))
        cur.execute(
            "INSERT INTO order_items (order_id, order_item_id, product_id, seller_id, "
            "shipping_limit_date, price, freight_value) "
            "SELECT %s, order_item_id, product_id, seller_id, "
            "NOW() + INTERVAL '3 days', price, freight_value "
            "FROM order_items WHERE order_id = %s", (oid, src_order))
        cur.execute(
            "INSERT INTO order_payments (order_id, payment_sequential, payment_type, "
            "payment_installments, payment_value) "
            "SELECT %s, payment_sequential, payment_type, payment_installments, "
            "payment_value FROM order_payments WHERE order_id = %s", (oid, src_order))
    return n


def update_order_status(cur, n):
    """Move open orders one step forward: created -> approved -> shipped -> delivered."""
    cur.execute(
        """
        UPDATE orders SET
            order_status = CASE order_status
                WHEN 'created'  THEN 'approved'
                WHEN 'approved' THEN 'shipped'
                WHEN 'shipped'  THEN 'delivered'
                ELSE order_status END,
            order_approved_at = CASE WHEN order_status = 'created'
                THEN NOW() ELSE order_approved_at END,
            order_delivered_customer_date = CASE WHEN order_status = 'shipped'
                THEN NOW() ELSE order_delivered_customer_date END,
            updated_at = NOW()
        WHERE order_id IN (
            SELECT order_id FROM orders
            WHERE order_status IN ('created', 'approved', 'shipped')
              AND is_deleted = FALSE
            ORDER BY random() LIMIT %s)
        """, (n,))
    return cur.rowcount


def cancel_orders(cur, n):
    cur.execute(
        """
        UPDATE orders SET order_status = 'canceled', updated_at = NOW()
        WHERE order_id IN (
            SELECT order_id FROM orders
            WHERE order_status IN ('created', 'approved') AND is_deleted = FALSE
            ORDER BY random() LIMIT %s)
        """, (n,))
    return cur.rowcount


def move_customers(cur, n):
    """Customers change city/state (this is what SCD Type 2 will track)."""
    cur.execute("SELECT customer_id FROM customers WHERE is_deleted = FALSE "
                "ORDER BY random() LIMIT %s", (n,))
    ids = [r[0] for r in cur.fetchall()]
    cur.execute("SELECT customer_zip_code_prefix, customer_city, customer_state "
                "FROM customers ORDER BY random() LIMIT %s", (n,))
    places = cur.fetchall()
    for cid, (zipc, city, state) in zip(ids, places):
        cur.execute(
            "UPDATE customers SET customer_zip_code_prefix = %s, customer_city = %s, "
            "customer_state = %s, updated_at = NOW() WHERE customer_id = %s",
            (zipc, city, state, cid))
    return len(ids)


def update_products(cur, n):
    """Product attribute changes (SCD Type 2 candidate)."""
    cur.execute(
        """
        UPDATE products SET
            product_weight_g = GREATEST(1, product_weight_g + (floor(random() * 200) - 100)::int),
            updated_at = NOW()
        WHERE product_id IN (
            SELECT product_id FROM products
            WHERE product_weight_g IS NOT NULL AND is_deleted = FALSE
            ORDER BY random() LIMIT %s)
        """, (n,))
    return cur.rowcount


def soft_delete(cur, n):
    """Mark rows deleted instead of removing them, so the delete can be captured."""
    cur.execute(
        """
        UPDATE order_reviews SET is_deleted = TRUE, updated_at = NOW()
        WHERE ctid IN (SELECT ctid FROM order_reviews WHERE is_deleted = FALSE
                       ORDER BY random() LIMIT %s)
        """, (n,))
    reviews = cur.rowcount
    cur.execute(
        """
        UPDATE orders SET is_deleted = TRUE, updated_at = NOW()
        WHERE order_id IN (SELECT order_id FROM orders WHERE is_deleted = FALSE
                           ORDER BY random() LIMIT %s)
        """, (n,))
    return reviews, cur.rowcount


def main():
    random.seed()
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT NOW()")
            started = cur.fetchone()[0]
            print(f"Simulation started at {started}\n")

            print(f"Inserted new orders       : {insert_new_orders(cur, NEW_ORDERS)}")
            print(f"Order status updates      : {update_order_status(cur, STATUS_UPDATES)}")
            print(f"Cancelled orders          : {cancel_orders(cur, CANCELLATIONS)}")
            print(f"Customers moved (city)    : {move_customers(cur, CUSTOMER_MOVES)}")
            print(f"Products updated (weight) : {update_products(cur, PRODUCT_UPDATES)}")
            reviews, orders = soft_delete(cur, SOFT_DELETES)
            print(f"Soft-deleted reviews      : {reviews}")
            print(f"Soft-deleted orders       : {orders}")
        conn.commit()
        print("\nChanges committed.")
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    main() 