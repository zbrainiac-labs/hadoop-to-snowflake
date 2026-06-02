#!/bin/bash
set -euo pipefail

# Bootstrap Ranger with sample Hive policies for the migration demo.
# Registers a Hive service and loads 10 policies (access, masking, row-filter).

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

# Load environment variables from .env
if [ -f "$PROJECT_DIR/.env" ]; then
    set -a; source "$PROJECT_DIR/.env"; set +a
fi

RANGER_URL="${RANGER_URL:-http://localhost:6080}"
RANGER_USER="admin"
RANGER_PASS="${RANGER_ADMIN_PASSWORD:?Set RANGER_ADMIN_PASSWORD in .env}"
SERVICE_NAME="test_db_hive"

echo "=== Ranger Policy Bootstrap ==="
echo "  URL: $RANGER_URL"
echo "  Service: $SERVICE_NAME"
echo ""

# Wait for Ranger
echo "[1/5] Waiting for Ranger Admin..."
until curl -sf -u "$RANGER_USER:$RANGER_PASS" "$RANGER_URL/service/plugins/policies/exportJson" > /dev/null 2>&1; do
    sleep 5
done
echo "  Ranger Admin is ready."

# Delete existing custom policies from service (clean slate)
echo "[2/5] Deleting existing custom policies..."
python3 -c "
import json, urllib.request, base64

ranger_url = '$RANGER_URL'
service_name = '$SERVICE_NAME'
creds = base64.b64encode(b'$RANGER_USER:$RANGER_PASS').decode()

# Default Ranger policies start with 'all -' or contain 'default' or 'Information_schema'
DEFAULT_PREFIXES = ('all -', 'default ', 'Information_schema')

req = urllib.request.Request(
    f'{ranger_url}/service/public/v2/api/policy?serviceName={service_name}',
    headers={'Authorization': f'Basic {creds}'}
)
try:
    resp = urllib.request.urlopen(req)
    policies = json.loads(resp.read().decode())
    deleted = 0
    for p in policies:
        name = p.get('name', '')
        if not any(name.startswith(prefix) for prefix in DEFAULT_PREFIXES):
            del_req = urllib.request.Request(
                f'{ranger_url}/service/public/v2/api/policy/{p[\"id\"]}',
                headers={'Authorization': f'Basic {creds}'},
                method='DELETE'
            )
            try:
                urllib.request.urlopen(del_req)
                deleted += 1
            except Exception:
                pass
    print(f'  Deleted {deleted} custom policies.')
except Exception as e:
    print(f'  No existing policies to clean (service may not exist yet).')
" 2>&1

# Register Hive service
echo "[3/5] Registering Hive service..."
HTTP_CODE=$(curl -sf -o /dev/null -w "%{http_code}" -u "$RANGER_USER:$RANGER_PASS" \
    "$RANGER_URL/service/public/v2/api/service/name/$SERVICE_NAME" 2>/dev/null || echo "000")
if [ "$HTTP_CODE" = "200" ]; then
    echo "  Service '$SERVICE_NAME' already exists."
else
    curl -sf -u "$RANGER_USER:$RANGER_PASS" \
        -X POST "$RANGER_URL/service/public/v2/api/service" \
        -H "Content-Type: application/json" \
        -d "{
            \"name\": \"$SERVICE_NAME\",
            \"type\": \"hive\",
            \"configs\": {
                \"username\": \"hive\",
                \"password\": \"hive\",
                \"jdbc.driverClassName\": \"org.apache.hive.jdbc.HiveDriver\",
                \"jdbc.url\": \"jdbc:hive2://hiveserver2:10000/\"
            },
            \"isEnabled\": true
        }" > /dev/null 2>&1 && echo "  Service '$SERVICE_NAME' registered." || echo "  WARN: Could not register service."
fi

# Create groups required by policies
echo "[4/5] Creating groups..."
for GROUP in data_analysts payments_team compliance_team ch_analysts de_analysts read_only_analysts; do
    HTTP_CODE=$(curl -sf -o /dev/null -w "%{http_code}" -u "$RANGER_USER:$RANGER_PASS" \
        "$RANGER_URL/service/xusers/groups/name/$GROUP" 2>/dev/null || echo "000")
    if [ "$HTTP_CODE" = "200" ]; then
        echo "  Group '$GROUP' already exists."
    else
        curl -sf -u "$RANGER_USER:$RANGER_PASS" \
            -X POST "$RANGER_URL/service/xusers/groups" \
            -H "Content-Type: application/json" \
            -d "{\"name\": \"$GROUP\", \"description\": \"Auto-created for migration demo\"}" > /dev/null 2>&1 \
            && echo "  Group '$GROUP' created." || echo "  WARN: Could not create group '$GROUP'."
    fi
done

# Load policies from fixture
echo "[5/5] Loading policies from fixtures/ranger_policies.json..."
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
FIXTURE="${SCRIPT_DIR}/../fixtures/ranger_policies.json"

if [ ! -f "$FIXTURE" ]; then
    echo "  ERROR: Fixture not found at $FIXTURE"
    exit 1
fi

LOADED=0
SKIPPED=0
python3 -c "
import json, urllib.request, base64, sys

fixture_path = '$FIXTURE'
ranger_url = '$RANGER_URL'
service_name = '$SERVICE_NAME'
creds = base64.b64encode(b'$RANGER_USER:$RANGER_PASS').decode()

with open(fixture_path) as f:
    data = json.load(f)

for policy in data['policies']:
    policy['service'] = service_name
    # Remove id to avoid conflicts
    policy.pop('id', None)
    policy.pop('guid', None)
    req = urllib.request.Request(
        f'{ranger_url}/service/public/v2/api/policy',
        data=json.dumps(policy).encode(),
        headers={'Content-Type': 'application/json', 'Authorization': f'Basic {creds}'},
        method='POST'
    )
    try:
        resp = urllib.request.urlopen(req)
        print(f'  [OK] {policy[\"name\"]}')
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        if 'already exists' in body.lower():
            print(f'  [SKIP] {policy[\"name\"]} (already exists)')
        else:
            print(f'  [WARN] {policy[\"name\"]} (HTTP {e.code}: {body[:120]})')
" 2>&1

echo ""
echo "=== Bootstrap Complete ==="
echo "  Ranger UI: $RANGER_URL (admin/****)"
echo "  Service: $SERVICE_NAME"
echo "  Export: curl -u admin:\$RANGER_ADMIN_PASSWORD $RANGER_URL/service/plugins/policies/exportJson?serviceName=$SERVICE_NAME"
echo ""
