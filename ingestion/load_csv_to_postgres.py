import csv
import os
from pathlib import Path

import psycopg2
from dotenv import load_dotenv

load_dotenv()

RAW_DIR = Path("data/raw")

# table name -> CSV file
TABLES = {
    "customers": "olist_customers_dataset.csv",
    "orders": "olist_orders_dataset.csv",
    "order_items": "olist_order_items_dataset.csv",
    "order_payments": "olist_order_payments_dataset.csv",
    "order_reviews": "olist_order_reviews_dataset.csv",
    "products": "olist_products_dataset.csv",
    "sellers": "olist_sellers_dataset.csv",
    "geolocation": "olist_geolocation_dataset.csv",
    "product_category_translation": "product_category_name_translation.csv",
}


def get_connection():
    return psycopg2.connect(
        host=os.getenv("POSTGRES_HOST", "localhost"),
        port=os.getenv("POSTGRES_PORT", "5432"),
        dbname=os.getenv("POSTGRES_DB"),
        user=os.getenv("POSTGRES_USER"),
        password=os.getenv("POSTGRES_PASSWORD"),
    )


def load_table(cur, table, csv_path):
    # Read only the header to know which columns the CSV has
    with open(csv_path, encoding="utf-8-sig", newline="") as f:
        columns = next(csv.reader(f))

    cur.execute(f"TRUNCATE TABLE {table}")  # makes reruns safe (no duplicates)

    col_list = ", ".join(columns)
    sql = f"COPY {table} ({col_list}) FROM STDIN WITH (FORMAT csv, HEADER true)"
    with open(csv_path, encoding="utf-8-sig", newline="") as f:
        cur.copy_expert(sql, f)

    cur.execute(f"SELECT COUNT(*) FROM {table}")
    return cur.fetchone()[0]


def main():
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            for table, filename in TABLES.items():
                csv_path = RAW_DIR / filename
                count = load_table(cur, table, csv_path)
                print(f"{table:32s} {count:>10,} rows loaded")
        conn.commit()
        print("\nAll tables loaded and committed.")
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    main()