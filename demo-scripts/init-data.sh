#!/bin/bash
set -euo pipefail

# Load environment variables from .env
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
if [ -f "$PROJECT_DIR/.env" ]; then
    set -a; source "$PROJECT_DIR/.env"; set +a
fi

HIVE_JDBC="jdbc:hive2://hiveserver2:10000/"
HDFS_WAREHOUSE="/user/hive/warehouse/test_db.db"

echo "=== Hadoop Test Stack: Data Initialization (3 Tables) ==="
echo "  Run this script from the HOST, not inside a container."
echo ""

echo "[1/7] Waiting for HiveServer2..."
until docker exec hiveserver2 beeline -u "$HIVE_JDBC" --silent=true -e "SHOW DATABASES;" > /dev/null 2>&1; do
    echo "  HiveServer2 not ready, retrying in 5s..."
    sleep 5
done
echo "  HiveServer2 is ready."

echo "[2/7] Creating Hive database..."
docker exec hiveserver2 beeline -u "$HIVE_JDBC" --silent=true -e "
DROP DATABASE IF EXISTS test_db CASCADE;
CREATE DATABASE test_db COMMENT 'Test database for Hive-to-Iceberg migration validation. Contains 3 related tables: customers (master), customer_transactions (detail), transaction_disputes (detail).';
" 2>/dev/null
docker exec namenode hdfs dfs -rm -r -f "$HDFS_WAREHOUSE" 2>/dev/null || true
docker exec namenode hdfs dfs -mkdir -p "$HDFS_WAREHOUSE" 2>/dev/null
echo "  Database test_db created (clean)."

echo "[3/7] Loading customers (master table, 500 rows)..."
docker exec namenode hdfs dfs -mkdir -p "$HDFS_WAREHOUSE/customers"
docker cp ./workspace/data/customers/data.parquet namenode:/tmp/customers.parquet
docker exec namenode hdfs dfs -put -f /tmp/customers.parquet "$HDFS_WAREHOUSE/customers/"
docker exec hiveserver2 beeline -u "$HIVE_JDBC" --silent=true -e "
CREATE EXTERNAL TABLE IF NOT EXISTS test_db.customers (
    customer_id INT COMMENT 'Unique customer identifier (PK, 1-500)',
    first_name STRING COMMENT 'Customer first name',
    last_name STRING COMMENT 'Customer last name',
    email STRING COMMENT 'Customer email address',
    country STRING COMMENT 'ISO 3166-1 alpha-2 country code (CH, DE, US, GB, FR, JP, SG)',
    segment STRING COMMENT 'Customer segment: RETAIL, PRIVATE, or INSTITUTIONAL',
    created_date STRING COMMENT 'Account creation date in ISO 8601 format (YYYY-MM-DD)',
    is_active BOOLEAN COMMENT 'Whether the customer account is currently active'
)
COMMENT 'Master customer dimension table. Contains 500 synthetic customers across multiple countries and segments.'
STORED AS PARQUET
LOCATION 'hdfs://namenode:9000$HDFS_WAREHOUSE/customers'
TBLPROPERTIES (
    'domain'='CRM',
    'data_owner'='risk_team',
    'sensitivity'='HIGH',
    'source_system'='core_banking',
    'pii_map'='{"email": "sha2", "first_name": "mask", "last_name": "mask"}'
);
" 2>/dev/null
echo "  customers table created."

echo "[4/7] Loading customer_transactions (detail table, 1000 rows, partitioned)..."
docker exec namenode hdfs dfs -mkdir -p "$HDFS_WAREHOUSE/customer_transactions/status=COMPLETED"
docker exec namenode hdfs dfs -mkdir -p "$HDFS_WAREHOUSE/customer_transactions/status=PENDING"
docker exec namenode hdfs dfs -mkdir -p "$HDFS_WAREHOUSE/customer_transactions/status=FAILED"
for STATUS in COMPLETED PENDING FAILED; do
    docker cp ./workspace/data/customer_transactions/status=$STATUS/data.parquet namenode:/tmp/data.parquet
    docker exec namenode hdfs dfs -put -f /tmp/data.parquet "$HDFS_WAREHOUSE/customer_transactions/status=$STATUS/"
done
docker exec hiveserver2 beeline -u "$HIVE_JDBC" --silent=true -e "
CREATE EXTERNAL TABLE IF NOT EXISTS test_db.customer_transactions (
    transaction_id STRING COMMENT 'Unique transaction identifier (UUID v4)',
    customer_id INT COMMENT 'Foreign key to customers.customer_id',
    amount DOUBLE COMMENT 'Transaction amount in the specified currency',
    currency STRING COMMENT 'ISO 4217 currency code (USD, EUR, GBP, CHF, JPY)',
    transaction_date STRING COMMENT 'Transaction date in ISO 8601 format (YYYY-MM-DD)',
    category STRING COMMENT 'Transaction type: TRANSFER, PAYMENT, WITHDRAWAL, DEPOSIT, or FEE'
)
COMMENT 'Customer transaction fact table. Contains 1000 synthetic transactions partitioned by processing status. FK: customer_id -> customers.customer_id'
PARTITIONED BY (status STRING COMMENT 'Processing status: COMPLETED, PENDING, or FAILED')
STORED AS PARQUET
LOCATION 'hdfs://namenode:9000$HDFS_WAREHOUSE/customer_transactions'
TBLPROPERTIES (
    'domain'='PAY',
    'data_owner'='payments_team',
    'sensitivity'='MEDIUM',
    'source_system'='core_banking',
    'pii_map'='{"transaction_id": "pseudonymize"}'
);

MSCK REPAIR TABLE test_db.customer_transactions;
" 2>/dev/null
echo "  customer_transactions table created."

echo "[5/7] Loading transaction_disputes (detail table, ~150 rows, partitioned)..."
docker exec namenode hdfs dfs -mkdir -p "$HDFS_WAREHOUSE/transaction_disputes/resolution_status=OPEN"
docker exec namenode hdfs dfs -mkdir -p "$HDFS_WAREHOUSE/transaction_disputes/resolution_status=UNDER_REVIEW"
docker exec namenode hdfs dfs -mkdir -p "$HDFS_WAREHOUSE/transaction_disputes/resolution_status=RESOLVED"
docker exec namenode hdfs dfs -mkdir -p "$HDFS_WAREHOUSE/transaction_disputes/resolution_status=REJECTED"
for RSTATUS in OPEN UNDER_REVIEW RESOLVED REJECTED; do
    if [ -f "./workspace/data/transaction_disputes/resolution_status=$RSTATUS/data.parquet" ]; then
        docker cp "./workspace/data/transaction_disputes/resolution_status=$RSTATUS/data.parquet" namenode:/tmp/data.parquet
        docker exec namenode hdfs dfs -put -f /tmp/data.parquet "$HDFS_WAREHOUSE/transaction_disputes/resolution_status=$RSTATUS/"
    fi
done
docker exec hiveserver2 beeline -u "$HIVE_JDBC" --silent=true -e "
CREATE EXTERNAL TABLE IF NOT EXISTS test_db.transaction_disputes (
    dispute_id STRING COMMENT 'Unique dispute identifier (UUID v4)',
    transaction_id STRING COMMENT 'Foreign key to customer_transactions.transaction_id',
    customer_id INT COMMENT 'Foreign key to customers.customer_id (denormalized)',
    dispute_reason STRING COMMENT 'Reason for dispute: UNAUTHORIZED, DUPLICATE, AMOUNT_MISMATCH, SERVICE_NOT_RECEIVED, or FRAUD',
    dispute_amount DOUBLE COMMENT 'Disputed amount (may be partial, 50-100% of original transaction amount)',
    dispute_date STRING COMMENT 'Date the dispute was filed in ISO 8601 format (YYYY-MM-DD)'
)
COMMENT 'Transaction dispute fact table. Contains ~150 disputes for completed transactions. FK: transaction_id -> customer_transactions.transaction_id, customer_id -> customers.customer_id'
PARTITIONED BY (resolution_status STRING COMMENT 'Dispute resolution status: OPEN, UNDER_REVIEW, RESOLVED, or REJECTED')
STORED AS PARQUET
LOCATION 'hdfs://namenode:9000$HDFS_WAREHOUSE/transaction_disputes'
TBLPROPERTIES (
    'domain'='PAY',
    'data_owner'='compliance_team',
    'sensitivity'='HIGH',
    'source_system'='dispute_engine',
    'pii_map'='{"dispute_id": "pseudonymize", "customer_id": "mask"}'
);

MSCK REPAIR TABLE test_db.transaction_disputes;
" 2>/dev/null
echo "  transaction_disputes table created."

echo "[6/7] Verifying row counts..."
C_COUNT=$(docker exec hiveserver2 beeline -u "$HIVE_JDBC" --silent=true --outputformat=csv2 -e "SELECT COUNT(*) FROM test_db.customers;" 2>/dev/null | tail -1)
T_COUNT=$(docker exec hiveserver2 beeline -u "$HIVE_JDBC" --silent=true --outputformat=csv2 -e "SELECT COUNT(*) FROM test_db.customer_transactions;" 2>/dev/null | tail -1)
D_COUNT=$(docker exec hiveserver2 beeline -u "$HIVE_JDBC" --silent=true --outputformat=csv2 -e "SELECT COUNT(*) FROM test_db.transaction_disputes;" 2>/dev/null | tail -1)
echo "  customers:              $C_COUNT rows"
echo "  customer_transactions:  $T_COUNT rows"
echo "  transaction_disputes:   $D_COUNT rows"

echo "[7/7] Verifying relationships..."
ORPHAN_TXN=$(docker exec hiveserver2 beeline -u "$HIVE_JDBC" --silent=true --outputformat=csv2 -e "
SELECT COUNT(*) FROM test_db.customer_transactions t
LEFT JOIN test_db.customers c ON t.customer_id = c.customer_id
WHERE c.customer_id IS NULL;
" 2>/dev/null | tail -1)
echo "  Orphan transactions (no matching customer): $ORPHAN_TXN"

echo ""
echo "=== Summary ==="
echo "  Database: test_db"
echo "  Tables:"
echo "    - customers              (master, $C_COUNT rows, no partitions)"
echo "    - customer_transactions  (detail, $T_COUNT rows, partitioned by status)"
echo "    - transaction_disputes   (detail, $D_COUNT rows, partitioned by resolution_status)"
echo "  Relationships:"
echo "    - customer_transactions.customer_id -> customers.customer_id"
echo "    - transaction_disputes.transaction_id -> customer_transactions.transaction_id"
echo "    - transaction_disputes.customer_id -> customers.customer_id"
echo ""

if [ "$C_COUNT" -eq 500 ] 2>/dev/null && [ "$T_COUNT" -eq 1000 ] 2>/dev/null; then
    echo "SUCCESS: All tables loaded correctly."
else
    echo "WARNING: Unexpected row counts."
    exit 1
fi

# Load Ranger policies if Ranger is available
if curl -sf -u admin:${RANGER_ADMIN_PASSWORD:?Set RANGER_ADMIN_PASSWORD in .env} "http://localhost:6080/login.jsp" > /dev/null 2>&1; then
    echo ""
    echo "[8/7] Loading Ranger policies (Ranger detected)..."
    bash "$SCRIPT_DIR/ranger-bootstrap.sh" 2>&1 | grep -E "OK|SKIP|Complete|registered"
else
    echo ""
    echo "[INFO] Ranger not running -- skipping policy bootstrap."
    echo "       Policies available as fixture: fixtures/ranger_policies.json"
fi
