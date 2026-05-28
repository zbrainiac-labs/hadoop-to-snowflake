#!/bin/bash
set -euo pipefail

HIVE_DATABASE="${1:-test_db}"

echo "=== Hadoop Test Stack: Full Validation ==="
echo "  Database: $HIVE_DATABASE"
echo ""

PASS=0
FAIL=0

check() {
    local desc="$1"
    shift
    if "$@" > /dev/null 2>&1; then
        echo "  [PASS] $desc"
        PASS=$((PASS + 1))
    else
        echo "  [FAIL] $desc"
        FAIL=$((FAIL + 1))
    fi
}

echo "[AC-001] Docker Compose stack is running and healthy"
check "All containers are running" docker compose ps --status running --quiet
check "NameNode is healthy" docker inspect --format='{{.State.Health.Status}}' namenode | grep -q healthy
check "DataNode is healthy" docker inspect --format='{{.State.Health.Status}}' datanode | grep -q healthy
check "Metastore is healthy" docker inspect --format='{{.State.Health.Status}}' metastore | grep -q healthy
check "HiveServer2 is healthy" docker inspect --format='{{.State.Health.Status}}' hiveserver2 | grep -q healthy
check "Hue is healthy" docker inspect --format='{{.State.Health.Status}}' hue | grep -q healthy
echo ""

echo "[AC-002] Hue web UI is accessible"
check "Hue responds on port 8888" curl -sf http://localhost:8888/
echo ""

echo "[AC-003] Hive can list databases and tables"
check "Beeline SHOW DATABASES" docker exec hiveserver2 beeline -u 'jdbc:hive2://hiveserver2:10000/' --silent=true -e 'SHOW DATABASES;'
echo ""

echo "[AC-004] HDFS is operational"
check "NameNode web UI responds" curl -sf http://localhost:9870/
check "HDFS mkdir works" docker exec namenode hdfs dfs -mkdir -p /tmp/validation_test
check "HDFS rmdir works" docker exec namenode hdfs dfs -rmdir /tmp/validation_test
echo ""

echo "[AC-005] Migration test infrastructure"
check "Workspace mounted in hiveserver2" docker exec hiveserver2 test -d /workspace
check "Scripts mounted in hiveserver2" docker exec hiveserver2 test -d /scripts
echo ""

echo "[AC-006] Sample data (if loaded)"
if docker exec hiveserver2 beeline -u 'jdbc:hive2://hiveserver2:10000/' --silent=true -e "USE ${HIVE_DATABASE};" > /dev/null 2>&1; then
    ROW_COUNT=$(docker exec hiveserver2 beeline -u 'jdbc:hive2://hiveserver2:10000/' --silent=true --outputformat=csv2 -e "SELECT COUNT(*) FROM ${HIVE_DATABASE}.customer_transactions;" 2>/dev/null | tail -1)
    if [ "$ROW_COUNT" = "1000" ]; then
        echo "  [PASS] ${HIVE_DATABASE}.customer_transactions has 1000 rows"
        PASS=$((PASS + 1))
    else
        echo "  [FAIL] ${HIVE_DATABASE}.customer_transactions has $ROW_COUNT rows (expected 1000)"
        FAIL=$((FAIL + 1))
    fi
else
    echo "  [SKIP] ${HIVE_DATABASE} not yet created (run init-data.sh first)"
fi

echo ""
echo "=== Results: $PASS passed, $FAIL failed ==="

if [ "$FAIL" -gt 0 ]; then
    exit 1
fi
echo "All checks passed."
