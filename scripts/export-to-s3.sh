#!/bin/bash
set -euo pipefail

S3_PREFIX="${1:-s3://mdaeppen/hadoop-root}"
HIVE_DATABASE="${2:-test_db}"
HDFS_WAREHOUSE="/user/hive/warehouse/${HIVE_DATABASE}.db"
LOCAL_EXPORT="./workspace/export"

echo "=== HDFS to S3 Export ==="
echo "  Source: HDFS ($HDFS_WAREHOUSE)"
echo "  Target: $S3_PREFIX/$HIVE_DATABASE/"
echo ""

echo "[1/3] Exporting Parquet from HDFS to local staging..."
rm -rf "$LOCAL_EXPORT"
mkdir -p "$LOCAL_EXPORT"

TABLES=$(docker exec namenode hdfs dfs -ls "$HDFS_WAREHOUSE" 2>/dev/null | awk '{print $NF}' | grep "$HDFS_WAREHOUSE/" | xargs -I{} basename {})

for TABLE in $TABLES; do
    echo "  Exporting: $TABLE"
    mkdir -p "$LOCAL_EXPORT/$TABLE"
    docker exec namenode hdfs dfs -get "$HDFS_WAREHOUSE/$TABLE/" "/tmp/export_$TABLE" 2>/dev/null
    docker cp "namenode:/tmp/export_$TABLE" "$LOCAL_EXPORT/$TABLE/"
    docker exec namenode rm -rf "/tmp/export_$TABLE"

    # Flatten: move files from nested dir
    if [ -d "$LOCAL_EXPORT/$TABLE/export_$TABLE" ]; then
        mv "$LOCAL_EXPORT/$TABLE/export_$TABLE"/* "$LOCAL_EXPORT/$TABLE/" 2>/dev/null || true
        rm -rf "$LOCAL_EXPORT/$TABLE/export_$TABLE"
    fi
done
echo "  Done. Local staging: $LOCAL_EXPORT/"

echo ""
echo "[2/3] Uploading to S3..."
for TABLE in $TABLES; do
    echo "  Uploading: $TABLE -> $S3_PREFIX/$HIVE_DATABASE/$TABLE/"
    aws s3 sync "$LOCAL_EXPORT/$TABLE/" "$S3_PREFIX/$HIVE_DATABASE/$TABLE/" --quiet
done
echo "  Done."

echo ""
echo "[3/3] Verifying S3..."
aws s3 ls "$S3_PREFIX/$HIVE_DATABASE/" --recursive | wc -l | xargs echo "  Files in S3:"

echo ""
echo "=== Export Complete ==="
echo "  Run the generated Snowflake DDL from workspace/output/ to create Iceberg tables."
