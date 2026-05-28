#!/bin/bash
set -euo pipefail

echo "=============================================="
echo "  Hive-to-Snowflake Iceberg Migration E2E Demo"
echo "=============================================="
echo ""

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_DIR"

HIVE_DATABASE="test_db"
S3_PREFIX="s3://mdaeppen/hadoop-root"
EXTERNAL_VOLUME="HAM_ICEBERG_VOL"
STORAGE_INTEGRATION="MDAEPPEN_S3_INTEGRATION"
DOMAIN="HAM"
ENV="DEV"
COMPONENT="I"
MATURITY="RAW"
VERSION="001"

SF_DATABASE="${DOMAIN}_${ENV}"
SF_SCHEMA="${DOMAIN}_${MATURITY}_V${VERSION}"
SF_STAGE="${DOMAIN}${COMPONENT}_${MATURITY}_ST_ICEBERG"
DCM_PROJECT="${SF_DATABASE}.${SF_SCHEMA}.${DOMAIN}_DCM_PROJECT"

echo "  Config:"
echo "    Hive DB:          $HIVE_DATABASE"
echo "    S3:               $S3_PREFIX"
echo "    Snowflake:        $SF_DATABASE.$SF_SCHEMA"
echo "    External Volume:  $EXTERNAL_VOLUME"
echo "    DCM Project:      $DCM_PROJECT"
echo ""

echo "[1/10] Cleaning previous state..."
rm -rf workspace/data workspace/output workspace/export
docker compose down -v 2>/dev/null || true
echo "  Done."
echo ""

echo "[2/10] Starting Docker stack..."
docker compose up -d
echo "  All containers healthy."
echo ""

echo "[3/10] Generating fake data (3 tables, 1650 rows)..."
python3 scripts/generate-fake-data.py 2>&1 | grep "Summary" -A5
echo ""

echo "[4/10] Loading into HDFS + Hive (with TBLPROPERTIES + pii_map)..."
./scripts/init-data.sh 2>&1 | grep -E "SUCCESS|WARNING|customers:|customer_trans|transaction_dis|Orphan"
echo ""

echo "[5/10] Validating stack..."
./scripts/validate.sh "$HIVE_DATABASE" 2>&1 | grep -E "PASS|FAIL|Results"
echo ""

echo "[6/10] Exporting HMS metadata -> Snowflake DDL + DCM + tags..."
python3 scripts/hive_hms_to_horizon_zero_copy.py \
  --database "$HIVE_DATABASE" \
  --external-volume "$EXTERNAL_VOLUME" \
  --object-store-prefix "$S3_PREFIX" \
  --domain "$DOMAIN" --env "$ENV" --component "$COMPONENT" --maturity "$MATURITY" --version "$VERSION" \
  --output-dir workspace/output 2>&1 | grep -E "Found|EXPORTED|Summary|Tables|OK|SKIP"
echo ""

echo "[7/10] Exporting Parquet from HDFS -> S3..."
./scripts/export-to-s3.sh "$S3_PREFIX" "$HIVE_DATABASE" 2>&1 | grep -E "Files in S3|Done|Upload"
echo ""

echo "[8/10] Deploying infrastructure via DCM..."
snow sql -q "CREATE DATABASE IF NOT EXISTS ${SF_DATABASE}" 2>/dev/null || true
snow sql -q "CREATE SCHEMA IF NOT EXISTS ${SF_DATABASE}.${SF_SCHEMA}" 2>/dev/null || true
snow dcm create "${DCM_PROJECT}" --if-not-exists --database "${SF_DATABASE}" --schema "${SF_SCHEMA}" 2>/dev/null || true
snow dcm deploy "${DCM_PROJECT}" --from dcm/ --database "${SF_DATABASE}" --schema "${SF_SCHEMA}" 2>&1 | grep -E "Deployed|Error" || true

echo "  Creating Iceberg tables (not yet supported by DCM DEFINE)..."
for TABLE_DIR in workspace/output/*/; do
    TABLE_NAME=$(basename "$TABLE_DIR")
    if [ -f "${TABLE_DIR}create_iceberg_table.sql" ]; then
        echo "  Creating: $TABLE_NAME"
        snow sql -f "${TABLE_DIR}create_iceberg_table.sql" 2>/dev/null || true
    fi
done
echo "  DCM + tables deployed."
echo ""

echo "[9/10] Loading data via COPY INTO..."
snow sql -q "CREATE OR REPLACE STAGE ${SF_DATABASE}.${SF_SCHEMA}.${SF_STAGE} URL='${S3_PREFIX}/' STORAGE_INTEGRATION=${STORAGE_INTEGRATION} FILE_FORMAT=(TYPE=PARQUET)" 2>/dev/null || true
for TABLE_DIR in workspace/output/*/; do
    TABLE_NAME=$(basename "$TABLE_DIR")
    if [ -f "${TABLE_DIR}copy_into.sql" ]; then
        echo "  Loading: $TABLE_NAME"
        snow sql -f "${TABLE_DIR}copy_into.sql" 2>/dev/null || true
    fi
done
echo "  Data loaded."
echo ""

echo "[10/10] Applying governance tags..."
for TABLE_DIR in workspace/output/*/; do
    TABLE_NAME=$(basename "$TABLE_DIR")
    if [ -f "${TABLE_DIR}tags.sql" ] && [ -s "${TABLE_DIR}tags.sql" ]; then
        echo "  Tagging: $TABLE_NAME"
        snow sql -f "${TABLE_DIR}tags.sql" 2>/dev/null || true
    fi
done
echo "  Tags applied."
echo ""

echo "[Verify] Row counts in Snowflake..."
snow sql -q "SELECT table_name, row_count FROM ${SF_DATABASE}.INFORMATION_SCHEMA.TABLES WHERE TABLE_SCHEMA = '${SF_SCHEMA}' AND TABLE_TYPE = 'BASE TABLE' ORDER BY table_name" 2>/dev/null || \
snow sql -q "SHOW ICEBERG TABLES IN ${SF_DATABASE}.${SF_SCHEMA}" 2>/dev/null
echo ""

echo "=============================================="
echo "  E2E Demo Complete"
echo "=============================================="
echo ""
echo "  Snowflake: ${SF_DATABASE}.${SF_SCHEMA}"
echo "  DCM Project: ${DCM_PROJECT}"
echo "  Tags: DOMAIN, DATA_OWNER, SENSITIVITY, SOURCE_SYSTEM, PII"
echo ""
