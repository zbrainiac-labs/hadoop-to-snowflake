#!/usr/bin/env python3
"""Ranger Policy to Snowflake Governance Converter.

Exports policies from Apache Ranger via REST API and generates:
- Tag-based masking policy (single policy auto-applies to all PII-tagged columns)
- Row access policies (per-table filtering by role)
- GRANT statements (role creation + permission mapping)
"""

import argparse
import json
import os
import sys
import urllib.request
import urllib.error
import base64
from datetime import datetime, timezone


# Ranger masking type -> Snowflake expression (val is the column value)
RANGER_MASK_TO_SNOWFLAKE = {
    "MASK": "'***MASKED***'",
    "MASK_HASH": "SHA2(val, 256)",
    "MASK_NULL": "NULL",
    "MASK_SHOW_LAST_4": "CONCAT('***', RIGHT(val, 4))",
    "MASK_SHOW_FIRST_4": "CONCAT(LEFT(val, 4), '***')",
    "MASK_DATE_SHOW_YEAR": "DATE_TRUNC('YEAR', val)",
    "MASK_NONE": "val",
}

# Ranger masking type -> PII tag value (for tag-based masking approach)
RANGER_MASK_TO_PII_TAG = {
    "MASK": "mask",
    "MASK_HASH": "sha2",
    "MASK_NULL": "full",
    "MASK_SHOW_LAST_4": "mask",
    "MASK_SHOW_FIRST_4": "mask",
    "MASK_DATE_SHOW_YEAR": "mask",
}

# Ranger access type -> Snowflake privilege
RANGER_ACCESS_TO_SNOWFLAKE = {
    "select": "SELECT",
    "update": "INSERT",
    "create": "CREATE TABLE",
    "drop": "OWNERSHIP",
    "alter": "MODIFY",
    "all": "ALL",
}


def fetch_ranger_policies(ranger_url: str, service_name: str, username: str, password: str) -> dict:
    """Fetch policies from Ranger REST API."""
    url = f"{ranger_url}/service/plugins/policies/exportJson?serviceName={service_name}"
    creds = base64.b64encode(f"{username}:{password}".encode()).decode()

    req = urllib.request.Request(url)
    req.add_header("Authorization", f"Basic {creds}")

    try:
        resp = urllib.request.urlopen(req, timeout=30)
        return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        print(f"  ERROR: Ranger API returned HTTP {e.code}: {e.reason}")
        sys.exit(1)
    except urllib.error.URLError as e:
        print(f"  ERROR: Cannot connect to Ranger at {ranger_url}: {e.reason}")
        sys.exit(1)


def load_ranger_export(file_path: str) -> dict:
    """Load policies from a JSON file (offline mode)."""
    with open(file_path, "r") as f:
        return json.load(f)


def generate_snowflake_name(table_name: str, args) -> str:
    return f"{args.domain}{args.component}_{args.maturity}_TB_{table_name.upper()}"


def generate_schema_fqn(args) -> str:
    return f"{args.domain}_{args.env}.{args.domain}_{args.maturity}_V{args.version}"


def generate_tag_based_masking_sql(masking_policies: list, args) -> str:
    """Generate a single tag-based masking policy that auto-applies to PII-tagged columns."""
    schema_fqn = generate_schema_fqn(args)
    policy_name = f"{schema_fqn}.PII_AUTO_MASK"

    lines = [
        f"-- Tag-based masking policy: auto-applies to ALL columns tagged PII",
        f"-- Generated from {len(masking_policies)} Ranger column masking policies",
        f"-- Ranger groups mapped to Snowflake roles that see unmasked data: DATA_ENGINEER, ADMIN",
        f"",
        f"CREATE OR REPLACE MASKING POLICY {policy_name} AS",
        f"  (val VARCHAR) RETURNS VARCHAR ->",
        f"  CASE",
        f"    WHEN CURRENT_ROLE() IN ('DATA_ENGINEER', 'ADMIN', 'ACCOUNTADMIN') THEN val",
        f"    WHEN SYSTEM$GET_TAG_ON_CURRENT_COLUMN('{schema_fqn}.PII') = 'sha2'",
        f"      THEN SHA2(val, 256)",
        f"    WHEN SYSTEM$GET_TAG_ON_CURRENT_COLUMN('{schema_fqn}.PII') = 'mask'",
        f"      THEN CONCAT(LEFT(val, 1), '***')",
        f"    WHEN SYSTEM$GET_TAG_ON_CURRENT_COLUMN('{schema_fqn}.PII') = 'pseudonymize'",
        f"      THEN SHA2(val, 256)",
        f"    WHEN SYSTEM$GET_TAG_ON_CURRENT_COLUMN('{schema_fqn}.PII') = 'full'",
        f"      THEN NULL",
        f"    ELSE '***'",
        f"  END;",
        f"",
        f"-- Attach policy to the PII tag (auto-applies to all tagged columns)",
        f"ALTER TAG {schema_fqn}.PII SET MASKING POLICY {policy_name};",
        f"",
    ]

    # Document which Ranger policies drove this
    lines.append("-- Source Ranger masking policies:")
    for p in masking_policies:
        table = p["resources"].get("table", {}).get("values", ["?"])[0]
        col = p["resources"].get("column", {}).get("values", ["?"])[0]
        mask_type = "UNKNOWN"
        if p.get("dataMaskPolicyItems"):
            mask_type = p["dataMaskPolicyItems"][0].get("dataMaskInfo", {}).get("dataMaskType", "UNKNOWN")
        lines.append(f"--   {p['name']}: {table}.{col} -> {mask_type}")

    return "\n".join(lines)


def generate_row_access_policies_sql(row_filter_policies: list, args) -> dict:
    """Generate row access policies per table. Returns {table_name: sql_string}."""
    schema_fqn = generate_schema_fqn(args)
    result = {}

    for policy in row_filter_policies:
        table_values = policy["resources"].get("table", {}).get("values", [])
        if not table_values:
            continue
        table_name = table_values[0]
        sf_table_name = generate_snowflake_name(table_name, args)
        table_fqn = f"{schema_fqn}.{sf_table_name}"

        if table_name not in result:
            result[table_name] = []

        for item in policy.get("rowFilterPolicyItems", []):
            filter_expr = item.get("rowFilterInfo", {}).get("filterExpr", "")
            if not filter_expr:
                continue

            groups = item.get("groups", [])
            users = item.get("users", [])

            # Extract column from filter expression (simple parser)
            filter_col = filter_expr.split("=")[0].strip().split(" ")[0].strip() if "=" in filter_expr else "UNKNOWN"

            # Map Ranger group to Snowflake role name
            for group in groups:
                role_name = group.upper()
                policy_short = f"RAP_{table_name.upper()}_{role_name}"
                rap_name = f"{schema_fqn}.{policy_short}"

                lines = [
                    f"-- Row access policy from Ranger: {policy['name']}",
                    f"-- Ranger group '{group}' -> Snowflake role '{role_name}'",
                    f"-- Filter: {filter_expr}",
                    f"",
                    f"CREATE OR REPLACE ROW ACCESS POLICY {rap_name} AS",
                    f"  ({filter_col}_val VARCHAR) RETURNS BOOLEAN ->",
                    f"  CASE",
                    f"    WHEN CURRENT_ROLE() IN ('ADMIN', 'ACCOUNTADMIN', 'DATA_ENGINEER') THEN TRUE",
                    f"    WHEN CURRENT_ROLE() = '{role_name}' AND {filter_col}_val = {filter_expr.split('=')[1].strip() if '=' in filter_expr else 'TRUE'} THEN TRUE",
                    f"    ELSE FALSE",
                    f"  END;",
                    f"",
                    f"ALTER ICEBERG TABLE {table_fqn} ADD ROW ACCESS POLICY {rap_name} ON ({filter_col.upper()});",
                    f"",
                ]
                result[table_name].append("\n".join(lines))

    return {k: "\n".join(v) for k, v in result.items()}


def generate_grants_sql(access_policies: list, args) -> dict:
    """Generate role creation and GRANT statements per table. Returns {table_name: sql_string}."""
    schema_fqn = generate_schema_fqn(args)
    db_name = f"{args.domain}_{args.env}"

    # Collect all groups and their permissions
    role_grants = {}  # group -> [(table, [permissions])]

    for policy in access_policies:
        table_values = policy["resources"].get("table", {}).get("values", [])
        if not table_values:
            continue
        table_name = table_values[0]

        for item in policy.get("policyItems", []):
            accesses = [a["type"] for a in item.get("accesses", []) if a.get("isAllowed")]
            groups = item.get("groups", [])

            for group in groups:
                if group not in role_grants:
                    role_grants[group] = []
                role_grants[group].append((table_name, accesses))

    # Generate SQL grouped by table
    result = {}
    all_roles_sql = []

    # Create all roles first
    all_roles_sql.append("-- Snowflake roles mapped from Ranger groups")
    all_roles_sql.append(f"-- Generated from {len(access_policies)} Ranger access policies")
    all_roles_sql.append("")
    for group in sorted(role_grants.keys()):
        role_name = group.upper()
        all_roles_sql.append(f"CREATE ROLE IF NOT EXISTS {role_name};")
        all_roles_sql.append(f"GRANT USAGE ON DATABASE {db_name} TO ROLE {role_name};")
        all_roles_sql.append(f"GRANT USAGE ON SCHEMA {schema_fqn} TO ROLE {role_name};")
    all_roles_sql.append("")

    # Grant per table
    for group, table_perms in sorted(role_grants.items()):
        role_name = group.upper()
        for table_name, accesses in table_perms:
            if table_name not in result:
                result[table_name] = []

            sf_privs = []
            for acc in accesses:
                sf_priv = RANGER_ACCESS_TO_SNOWFLAKE.get(acc, "SELECT")
                sf_privs.append(sf_priv)

            if table_name == "*":
                grant_target = f"ALL TABLES IN SCHEMA {schema_fqn}"
                grant_future = f"FUTURE TABLES IN SCHEMA {schema_fqn}"
                result.setdefault("_global", [])
                for priv in sf_privs:
                    result["_global"].append(f"GRANT {priv} ON {grant_target} TO ROLE {role_name};")
                    result["_global"].append(f"GRANT {priv} ON {grant_future} TO ROLE {role_name};")
            else:
                sf_table_name = generate_snowflake_name(table_name, args)
                table_fqn = f"{schema_fqn}.{sf_table_name}"
                for priv in sf_privs:
                    result[table_name].append(
                        f"-- Ranger: {group} -> {','.join(accesses)} on {table_name}")
                    result[table_name].append(f"GRANT {priv} ON ICEBERG TABLE {table_fqn} TO ROLE {role_name};")

    # Prepend role creation to all results
    roles_header = "\n".join(all_roles_sql)
    final = {}
    for table_name, lines in result.items():
        final[table_name] = roles_header + "\n" + "\n".join(lines)

    return final


def process_ranger_policies(policies_data: dict, args):
    """Main processing: categorize and convert Ranger policies to Snowflake SQL."""
    policies = policies_data.get("policies", [])

    access_policies = [p for p in policies if p.get("policyType", 0) == 0]
    masking_policies = [p for p in policies if p.get("policyType", 0) == 1]
    row_filter_policies = [p for p in policies if p.get("policyType", 0) == 2]

    print(f"  Policies found: {len(policies)} total")
    print(f"    Access (policyType=0): {len(access_policies)}")
    print(f"    Masking (policyType=1): {len(masking_policies)}")
    print(f"    Row Filter (policyType=2): {len(row_filter_policies)}")
    print("")

    os.makedirs(args.output_dir, exist_ok=True)

    # 1. Generate tag-based masking policy (single file at output root)
    if masking_policies:
        masking_sql = generate_tag_based_masking_sql(masking_policies, args)
        masking_path = os.path.join(args.output_dir, "tag_based_masking.sql")
        with open(masking_path, "w") as f:
            f.write(masking_sql)
        print(f"  [OK] tag_based_masking.sql ({len(masking_policies)} Ranger masking policies -> 1 tag-based policy)")

    # 2. Generate row access policies (per table)
    if row_filter_policies:
        rap_by_table = generate_row_access_policies_sql(row_filter_policies, args)
        for table_name, sql in rap_by_table.items():
            table_dir = os.path.join(args.output_dir, table_name)
            os.makedirs(table_dir, exist_ok=True)
            rap_path = os.path.join(table_dir, "row_access_policies.sql")
            with open(rap_path, "w") as f:
                f.write(sql)
            print(f"  [OK] {table_name}/row_access_policies.sql")

    # 3. Generate grants (per table)
    if access_policies:
        grants_by_table = generate_grants_sql(access_policies, args)
        for table_name, sql in grants_by_table.items():
            table_dir = os.path.join(args.output_dir, table_name)
            os.makedirs(table_dir, exist_ok=True)
            grants_path = os.path.join(table_dir, "grants.sql")
            with open(grants_path, "w") as f:
                f.write(sql)
            print(f"  [OK] {table_name}/grants.sql")

    # 4. Write summary
    summary = f"""=== Ranger Policy Migration Summary ===
Source: {args.ranger_url or args.ranger_export}
Service: {args.service_name}
Target: {generate_schema_fqn(args)}

Policies processed: {len(policies)}
  Access policies:     {len(access_policies)} -> GRANT statements
  Masking policies:    {len(masking_policies)} -> 1 tag-based masking policy
  Row filter policies: {len(row_filter_policies)} -> row access policies

Snowflake mapping:
  Ranger groups -> Snowflake roles (uppercase)
  Ranger column masking -> PII tag + tag-based masking policy
  Ranger row filters -> CREATE ROW ACCESS POLICY per group/table
  Ranger access ALLOW -> GRANT privilege TO ROLE

Generated at: {datetime.now(timezone.utc).isoformat()}
"""
    summary_path = os.path.join(args.output_dir, "ranger_summary.txt")
    with open(summary_path, "w") as f:
        f.write(summary)
    print(f"  [OK] ranger_summary.txt")

    return len(access_policies), len(masking_policies), len(row_filter_policies)


def main():
    parser = argparse.ArgumentParser(description="Convert Apache Ranger policies to Snowflake governance SQL")
    source_group = parser.add_mutually_exclusive_group(required=True)
    source_group.add_argument("--ranger-url", help="Ranger Admin URL (e.g. http://localhost:6080)")
    source_group.add_argument("--ranger-export", help="Path to Ranger policy export JSON file")

    parser.add_argument("--service-name", default="test_db_hive", help="Ranger service name (default: test_db_hive)")
    parser.add_argument("--ranger-user", default="admin", help="Ranger admin username (default: admin)")
    parser.add_argument("--ranger-password", default="rangerR0cks!", help="Ranger admin password")

    parser.add_argument("--domain", default="HAM", help="Naming standard: domain code")
    parser.add_argument("--env", default="DEV", help="Naming standard: environment")
    parser.add_argument("--component", default="I", help="Naming standard: component letter")
    parser.add_argument("--maturity", default="RAW", help="Naming standard: maturity level")
    parser.add_argument("--version", default="001", help="Naming standard: schema version")
    parser.add_argument("--output-dir", default="workspace/output", help="Output directory")

    args = parser.parse_args()

    print("=== Ranger to Snowflake Policy Converter ===")
    print("")

    if args.ranger_url:
        print(f"  Fetching policies from: {args.ranger_url}")
        print(f"  Service: {args.service_name}")
        policies_data = fetch_ranger_policies(args.ranger_url, args.service_name, args.ranger_user, args.ranger_password)
    else:
        print(f"  Loading policies from: {args.ranger_export}")
        policies_data = load_ranger_export(args.ranger_export)

    print("")
    access, masking, row_filter = process_ranger_policies(policies_data, args)

    print("")
    print(f"=== Done: {access + masking + row_filter} policies converted ===")

    return 0


if __name__ == "__main__":
    sys.exit(main())
