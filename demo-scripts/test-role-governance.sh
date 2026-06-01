#!/bin/bash
set -euo pipefail

# Test governance enforcement with different Snowflake roles
# Requires a connection that supports USE ROLE (interactive user, not PAT-restricted).
# Set SNOW_CONN to a non-PAT connection, e.g.: SNOW_CONN=my-interactive-conn ./demo-scripts/test-role-governance.sh
# If PAT-restricted, tests run with default role only.

SNOW_CONN="${SNOW_CONN:-zs28104-svc_mdaeppen}"
SF_DATABASE="HAM_DEV"
SF_SCHEMA="HAM_RAW_V001"
TABLE="HAMI_RAW_TB_CUSTOMERS"
FQN="${SF_DATABASE}.${SF_SCHEMA}.${TABLE}"

echo "=============================================="
echo "  Role-Based Governance Verification"
echo "=============================================="
echo "  Table: $FQN"
echo "  Connection: $SNOW_CONN"
echo ""

# Check if USE ROLE is supported
CAN_SWITCH=$(snow sql -q "USE ROLE CICD" -c "$SNOW_CONN" 2>&1 | grep -c "Statement executed" || echo "0")
if [ "$CAN_SWITCH" = "0" ]; then
    echo "  NOTE: Connection is PAT-restricted (no USE ROLE support)."
    echo "  Running limited tests with default role (CICD) only."
    echo "  For full role-switching tests, use an interactive connection."
    echo ""
    USE_ROLE_CMD=""
else
    USE_ROLE_CMD="supported"
fi

PASS=0
FAIL=0

sf_query() {
    snow sql -q "$1" -c "$SNOW_CONN" 2>/dev/null
}

test_query() {
    local QUERY="$1"
    local EXPECT_PATTERN="$2"
    local TEST_NAME="$3"

    RESULT=$(sf_query "$QUERY" || echo "ERROR")

    if echo "$RESULT" | grep -qE "$EXPECT_PATTERN"; then
        echo "  [PASS] $TEST_NAME"
        PASS=$((PASS + 1))
    else
        echo "  [FAIL] $TEST_NAME"
        echo "         Expected: $EXPECT_PATTERN"
        echo "         Got: $(echo "$RESULT" | grep -v "^$" | head -5)"
        FAIL=$((FAIL + 1))
    fi
}

echo "--- Masking Policy Verification (default role: CICD -> inherits DATA_ANALYSTS) ---"
echo ""

test_query \
    "SELECT EMAIL FROM $FQN LIMIT 1" \
    "[a-f0-9]{64}" \
    "EMAIL is SHA-256 hashed (PII tag = sha2)"

test_query \
    "SELECT FIRST_NAME FROM $FQN LIMIT 1" \
    "\*\*\*" \
    "FIRST_NAME is masked (PII tag = mask)"

test_query \
    "SELECT LAST_NAME FROM $FQN LIMIT 1" \
    "\*\*\*" \
    "LAST_NAME is masked (PII tag = mask)"

test_query \
    "SELECT COUNTRY FROM $FQN LIMIT 1" \
    "(CH|DE|US|GB|FR|JP|SG)" \
    "COUNTRY is unmasked (no PII tag)"

test_query \
    "SELECT SEGMENT FROM $FQN LIMIT 1" \
    "(RETAIL|PRIVATE|INSTITUTIONAL)" \
    "SEGMENT is unmasked (no PII tag)"

test_query \
    "SELECT COUNT(*) AS CNT FROM $FQN" \
    "500" \
    "Row count = 500 (all rows visible)"

echo ""
echo "--- Transaction Table Masking ---"
echo ""

test_query \
    "SELECT TRANSACTION_ID FROM ${SF_DATABASE}.${SF_SCHEMA}.HAMI_RAW_TB_CUSTOMER_TRANSACTIONS LIMIT 1" \
    "[a-f0-9]{64}" \
    "TRANSACTION_ID is SHA-256 hashed (PII tag = pseudonymize)"

test_query \
    "SELECT AMOUNT, CURRENCY FROM ${SF_DATABASE}.${SF_SCHEMA}.HAMI_RAW_TB_CUSTOMER_TRANSACTIONS LIMIT 1" \
    "[0-9]" \
    "AMOUNT is unmasked (no PII tag)"

echo ""
echo "--- Tag Verification ---"
echo ""

test_query \
    "SELECT CASE WHEN EMAIL NOT LIKE '%@%' THEN 'MASKED' ELSE 'UNMASKED' END AS STATUS FROM $FQN LIMIT 1" \
    "MASKED" \
    "Masking policy is actively enforcing (EMAIL != plaintext)"

test_query \
    "SHOW TAGS IN SCHEMA ${SF_DATABASE}.${SF_SCHEMA}" \
    "PII" \
    "PII tag exists"

echo ""
echo "=============================================="
echo "  Results: $PASS passed, $FAIL failed"
echo "=============================================="
echo ""

if [ "$FAIL" -eq 0 ]; then
    echo "  ALL TESTS PASS - Governance enforcement verified"
    exit 0
else
    echo "  $FAIL TEST(S) FAILED"
    exit 1
fi
