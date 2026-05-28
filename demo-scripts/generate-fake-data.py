#!/usr/bin/env python3
"""Generate fake data for 3 related tables as Parquet files.

Tables:
  - customers (master): 500 rows
  - customer_transactions (detail): 1000 rows, FK to customers.customer_id
  - transaction_disputes (detail): 150 rows, FK to customer_transactions.transaction_id

Output: ./workspace/data/<table_name>/[partition=value/]data.parquet
"""

import os
import random
import uuid
from datetime import date, timedelta

try:
    import pyarrow as pa
    import pyarrow.parquet as pq
except ImportError:
    print("ERROR: pyarrow is required. Install with: pip install pyarrow")
    raise SystemExit(1)

random.seed(42)

BASE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "workspace", "data")

START_DATE = date(2024, 1, 1)
END_DATE = date(2024, 12, 31)

COUNTRIES = ["CH", "DE", "US", "GB", "FR", "JP", "SG"]
SEGMENTS = ["RETAIL", "PRIVATE", "INSTITUTIONAL"]
CURRENCIES = ["USD", "EUR", "GBP", "CHF", "JPY"]
CATEGORIES = ["TRANSFER", "PAYMENT", "WITHDRAWAL", "DEPOSIT", "FEE"]
STATUSES = ["COMPLETED", "PENDING", "FAILED"]
DISPUTE_REASONS = ["UNAUTHORIZED", "DUPLICATE", "AMOUNT_MISMATCH", "SERVICE_NOT_RECEIVED", "FRAUD"]
DISPUTE_STATUSES = ["OPEN", "UNDER_REVIEW", "RESOLVED", "REJECTED"]


def random_date(start=START_DATE, end=END_DATE):
    delta = (end - start).days
    return (start + timedelta(days=random.randint(0, delta))).isoformat()


def generate_customers(n=500):
    rows = []
    for i in range(1, n + 1):
        rows.append({
            "customer_id": i,
            "first_name": f"First_{i}",
            "last_name": f"Last_{i}",
            "email": f"customer_{i}@example.com",
            "country": random.choice(COUNTRIES),
            "segment": random.choice(SEGMENTS),
            "created_date": random_date(date(2020, 1, 1), date(2023, 12, 31)),
            "is_active": random.choice([True, True, True, False]),
        })
    return rows


def generate_transactions(n=1000, max_customer_id=500):
    rows = []
    for _ in range(n):
        rows.append({
            "transaction_id": str(uuid.uuid4()),
            "customer_id": random.randint(1, max_customer_id),
            "amount": round(random.uniform(1.0, 10000.0), 2),
            "currency": random.choice(CURRENCIES),
            "transaction_date": random_date(),
            "category": random.choice(CATEGORIES),
            "status": random.choice(STATUSES),
        })
    return rows


def generate_disputes(transactions, n=150):
    completed = [t for t in transactions if t["status"] == "COMPLETED"]
    sampled = random.sample(completed, min(n, len(completed)))
    rows = []
    for t in sampled:
        dispute_date = date.fromisoformat(t["transaction_date"]) + timedelta(days=random.randint(1, 30))
        rows.append({
            "dispute_id": str(uuid.uuid4()),
            "transaction_id": t["transaction_id"],
            "customer_id": t["customer_id"],
            "dispute_reason": random.choice(DISPUTE_REASONS),
            "dispute_amount": round(t["amount"] * random.uniform(0.5, 1.0), 2),
            "dispute_date": min(dispute_date, END_DATE).isoformat(),
            "resolution_status": random.choice(DISPUTE_STATUSES),
        })
    return rows


def write_customers(rows):
    out_dir = os.path.join(BASE_DIR, "customers")
    os.makedirs(out_dir, exist_ok=True)

    schema = pa.schema([
        ("customer_id", pa.int32()),
        ("first_name", pa.string()),
        ("last_name", pa.string()),
        ("email", pa.string()),
        ("country", pa.string()),
        ("segment", pa.string()),
        ("created_date", pa.string()),
        ("is_active", pa.bool_()),
    ])

    table = pa.table({
        "customer_id": pa.array([r["customer_id"] for r in rows], type=pa.int32()),
        "first_name": pa.array([r["first_name"] for r in rows], type=pa.string()),
        "last_name": pa.array([r["last_name"] for r in rows], type=pa.string()),
        "email": pa.array([r["email"] for r in rows], type=pa.string()),
        "country": pa.array([r["country"] for r in rows], type=pa.string()),
        "segment": pa.array([r["segment"] for r in rows], type=pa.string()),
        "created_date": pa.array([r["created_date"] for r in rows], type=pa.string()),
        "is_active": pa.array([r["is_active"] for r in rows], type=pa.bool_()),
    }, schema=schema)

    path = os.path.join(out_dir, "data.parquet")
    pq.write_table(table, path)
    print(f"  customers: {len(rows)} rows -> {path}")


def write_transactions(rows):
    for status in STATUSES:
        partition_rows = [r for r in rows if r["status"] == status]
        if not partition_rows:
            continue

        out_dir = os.path.join(BASE_DIR, "customer_transactions", f"status={status}")
        os.makedirs(out_dir, exist_ok=True)

        schema = pa.schema([
            ("transaction_id", pa.string()),
            ("customer_id", pa.int32()),
            ("amount", pa.float64()),
            ("currency", pa.string()),
            ("transaction_date", pa.string()),
            ("category", pa.string()),
        ])

        table = pa.table({
            "transaction_id": pa.array([r["transaction_id"] for r in partition_rows], type=pa.string()),
            "customer_id": pa.array([r["customer_id"] for r in partition_rows], type=pa.int32()),
            "amount": pa.array([r["amount"] for r in partition_rows], type=pa.float64()),
            "currency": pa.array([r["currency"] for r in partition_rows], type=pa.string()),
            "transaction_date": pa.array([r["transaction_date"] for r in partition_rows], type=pa.string()),
            "category": pa.array([r["category"] for r in partition_rows], type=pa.string()),
        }, schema=schema)

        path = os.path.join(out_dir, "data.parquet")
        pq.write_table(table, path)
        print(f"  customer_transactions (status={status}): {len(partition_rows)} rows -> {path}")


def write_disputes(rows):
    for status in DISPUTE_STATUSES:
        partition_rows = [r for r in rows if r["resolution_status"] == status]
        if not partition_rows:
            continue

        out_dir = os.path.join(BASE_DIR, "transaction_disputes", f"resolution_status={status}")
        os.makedirs(out_dir, exist_ok=True)

        schema = pa.schema([
            ("dispute_id", pa.string()),
            ("transaction_id", pa.string()),
            ("customer_id", pa.int32()),
            ("dispute_reason", pa.string()),
            ("dispute_amount", pa.float64()),
            ("dispute_date", pa.string()),
        ])

        table = pa.table({
            "dispute_id": pa.array([r["dispute_id"] for r in partition_rows], type=pa.string()),
            "transaction_id": pa.array([r["transaction_id"] for r in partition_rows], type=pa.string()),
            "customer_id": pa.array([r["customer_id"] for r in partition_rows], type=pa.int32()),
            "dispute_reason": pa.array([r["dispute_reason"] for r in partition_rows], type=pa.string()),
            "dispute_amount": pa.array([r["dispute_amount"] for r in partition_rows], type=pa.float64()),
            "dispute_date": pa.array([r["dispute_date"] for r in partition_rows], type=pa.string()),
        }, schema=schema)

        path = os.path.join(out_dir, "data.parquet")
        pq.write_table(table, path)
        print(f"  transaction_disputes (resolution_status={status}): {len(partition_rows)} rows -> {path}")


if __name__ == "__main__":
    print("=== Generating fake data for 3 related tables ===")
    print("")

    print("[1/3] customers (master, 500 rows)...")
    customers = generate_customers(500)
    write_customers(customers)

    print("[2/3] customer_transactions (detail, 1000 rows, FK -> customers.customer_id)...")
    transactions = generate_transactions(1000, 500)
    write_transactions(transactions)

    print("[3/3] transaction_disputes (detail, 150 rows, FK -> customer_transactions.transaction_id)...")
    disputes = generate_disputes(transactions, 150)
    write_disputes(disputes)

    print("")
    print("=== Summary ===")
    print(f"  customers:              500 rows (no partitions)")
    print(f"  customer_transactions: 1000 rows (partitioned by status)")
    print(f"  transaction_disputes:   {len(disputes)} rows (partitioned by resolution_status)")
    print(f"  Output: {BASE_DIR}")
