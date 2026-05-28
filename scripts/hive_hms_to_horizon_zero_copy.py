#!/usr/bin/env python3
"""Hive HMS to Snowflake Horizon Iceberg (zero-copy) export script.

Connects to HiveServer2 via Beeline (docker exec), discovers all tables in a database,
extracts full metadata, and generates Snowflake-managed Iceberg DDL,
distcp commands (HDFS -> S3), and COPY INTO statements per table.
"""

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone


HIVE_TO_SNOWFLAKE_TYPES = {
    "string": "VARCHAR",
    "varchar": "VARCHAR",
    "char": "VARCHAR",
    "int": "INT",
    "integer": "INT",
    "bigint": "BIGINT",
    "smallint": "SMALLINT",
    "tinyint": "TINYINT",
    "double": "DOUBLE",
    "float": "FLOAT",
    "boolean": "BOOLEAN",
    "timestamp": "TIMESTAMP_NTZ",
    "date": "DATE",
    "binary": "BINARY",
    "array": "ARRAY",
    "map": "OBJECT",
    "struct": "OBJECT",
}


def map_hive_type(hive_type: str) -> str:
    lower = hive_type.lower().strip()
    if lower.startswith("decimal"):
        return lower.replace("decimal", "NUMBER")
    if lower.startswith("varchar"):
        return "VARCHAR"
    if lower.startswith("char"):
        return "VARCHAR"
    if lower.startswith("array"):
        return "ARRAY"
    if lower.startswith("map"):
        return "OBJECT"
    if lower.startswith("struct"):
        return "OBJECT"
    return HIVE_TO_SNOWFLAKE_TYPES.get(lower, "VARCHAR")


def escape_comment(comment: str) -> str:
    if not comment:
        return ""
    return comment.replace("'", "''")


def run_beeline(query: str, jdbc_url: str) -> str:
    cmd = [
        "docker", "exec", "hiveserver2",
        "beeline", "-u", jdbc_url,
        "--silent=true", "--outputformat=csv2",
        "-e", query,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    output = result.stdout
    if result.returncode != 0:
        stderr_clean = "\n".join(
            l for l in result.stderr.split("\n")
            if not any(skip in l for skip in ["SLF4J", "WARN", "INFO", "log4j", "deprecated", "packages", "scanning", "Configuration", "Started", "Stopped"])
        ).strip()
        if stderr_clean:
            raise RuntimeError(f"Beeline failed: {stderr_clean}")
    return output


def get_tables(jdbc_url: str, database: str) -> list:
    output = run_beeline(f"USE {database}; SHOW TABLES;", jdbc_url)
    tables = []
    for line in output.strip().split("\n"):
        line = line.strip()
        if not line:
            continue
        if line == "tab_name":
            continue
        if any(skip in line for skip in ["INFO", "Error", "WARN", ":", "/", ".", " "]):
            continue
        if re.match(r'^[a-z_][a-z0-9_]*$', line):
            tables.append(line)
    return tables


def parse_describe_formatted(output: str) -> dict:
    columns = []
    partition_keys = []
    properties = {}
    location = ""
    input_format = ""
    output_format = ""
    serde = ""
    table_comment = ""

    section = "columns"
    lines = output.strip().split("\n")

    for line in lines:
        parts = [p.strip() for p in line.split(",", 2)]
        if len(parts) < 2:
            continue

        col_name = parts[0]
        data_type = parts[1]
        comment = parts[2] if len(parts) > 2 else ""

        if col_name == "col_name" and data_type == "data_type":
            continue
        if col_name == "" and data_type == "" and comment == "":
            continue
        if col_name == "# col_name":
            section = "partition_keys"
            continue
        if col_name == "# Partition Information":
            section = "partition_keys"
            continue
        if col_name == "# Detailed Table Information":
            section = "details"
            continue
        if col_name == "# Storage Information":
            section = "storage"
            continue

        if section == "columns" and col_name and data_type and col_name != "#":
            if not col_name.startswith("#") and not col_name.startswith("Location"):
                columns.append({"name": col_name, "type": data_type, "comment": comment})

        elif section == "partition_keys" and col_name and data_type:
            if not col_name.startswith("#"):
                partition_keys.append({"name": col_name, "type": data_type, "comment": comment})

        elif section in ("details", "storage"):
            if col_name == "Location:":
                location = data_type
            elif col_name == "InputFormat:":
                input_format = data_type
            elif col_name == "OutputFormat:":
                output_format = data_type
            elif col_name == "SerDe Library:":
                serde = data_type
            elif data_type.strip() == "comment" or col_name.strip() == "comment":
                table_comment = comment if comment else data_type
            elif col_name == "" and data_type.strip() == "comment":
                table_comment = comment
            elif col_name == "" and data_type.strip() and data_type.strip() != "NULL":
                properties[data_type.strip()] = comment.strip() if comment else ""
            elif "=" in col_name and data_type:
                properties[col_name] = data_type

    return {
        "columns": columns,
        "partition_keys": partition_keys,
        "location": location,
        "input_format": input_format,
        "output_format": output_format,
        "serde": serde,
        "table_comment": table_comment,
        "parameters": properties,
    }


def extract_table_metadata(jdbc_url: str, database: str, table_name: str) -> dict:
    output = run_beeline(f"DESCRIBE FORMATTED {database}.{table_name};", jdbc_url)
    meta = parse_describe_formatted(output)
    meta["database"] = database
    meta["table_name"] = table_name

    is_parquet = (
        "parquet" in meta["input_format"].lower()
        or "parquet" in meta["output_format"].lower()
        or "parquet" in meta["serde"].lower()
    )
    meta["is_parquet"] = is_parquet
    return meta


def generate_snowflake_name(table_name: str, args) -> str:
    return f"{args.domain}{args.component}_{args.maturity}_TB_{table_name.upper()}"


def generate_schema_name(args) -> str:
    return f"{args.domain}_{args.maturity}_V{args.version}"


def generate_database_name(args) -> str:
    return f"{args.domain}_{args.env}"


def generate_stage_name(args) -> str:
    return f"{args.domain}{args.component}_{args.maturity}_ST_ICEBERG"


def generate_create_iceberg_ddl(meta: dict, args) -> str:
    db_name = generate_database_name(args)
    schema_name = generate_schema_name(args)
    table_name = generate_snowflake_name(meta["table_name"], args)

    all_columns = meta["columns"] + meta["partition_keys"]

    col_defs = []
    for col in all_columns:
        sf_type = map_hive_type(col["type"])
        line = f"    {col['name'].upper()} {sf_type}"
        if col["comment"]:
            line += f" COMMENT '{escape_comment(col['comment'])}'"
        col_defs.append(line)

    ddl = f"CREATE OR REPLACE ICEBERG TABLE {db_name}.{schema_name}.{table_name} (\n"
    ddl += ",\n".join(col_defs)
    ddl += "\n)"

    table_comment = meta["table_comment"]
    if table_comment:
        ddl += f"\nCOMMENT = '{escape_comment(table_comment)}'"

    ddl += f"\nCATALOG = 'SNOWFLAKE'"
    ddl += f"\nEXTERNAL_VOLUME = '{args.external_volume}'"

    base_location = f"{meta['database']}/{meta['table_name']}"
    ddl += f"\nBASE_LOCATION = '{base_location}';"

    return ddl


def generate_copy_into(meta: dict, args) -> str:
    db_name = generate_database_name(args)
    schema_name = generate_schema_name(args)
    table_name = generate_snowflake_name(meta["table_name"], args)
    stage_fqn = f"{db_name}.{schema_name}.{generate_stage_name(args)}"
    stage_path = f"@{stage_fqn}/{meta['database']}/{meta['table_name']}/"

    return f"""COPY INTO {db_name}.{schema_name}.{table_name}
FROM {stage_path}
FILE_FORMAT = (TYPE = PARQUET)
MATCH_BY_COLUMN_NAME = CASE_INSENSITIVE;"""


GOVERNANCE_TAG_KEYS = ["domain", "data_owner", "sensitivity", "source_system"]
TAG_ALLOWED_VALUES = {
    "domain": "'CRM', 'PAY', 'INV', 'REF', 'LOA', 'EQT', 'CLR'",
    "sensitivity": "'LOW', 'MEDIUM', 'HIGH'",
    "pii": "'sha2', 'mask', 'pseudonymize', 'full'",
}


def generate_tags_sql(meta: dict, args) -> str:
    db_name = generate_database_name(args)
    schema_name = generate_schema_name(args)
    table_name = generate_snowflake_name(meta["table_name"], args)
    fqn = f"{db_name}.{schema_name}.{table_name}"
    tag_schema = f"{db_name}.{schema_name}"

    lines = []

    all_tag_keys = set()
    for key in GOVERNANCE_TAG_KEYS:
        if key in meta["parameters"]:
            all_tag_keys.add(key.upper())

    pii_map = {}
    if "pii_map" in meta["parameters"]:
        raw = meta["parameters"]["pii_map"]
        try:
            pii_map = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            cleaned = re.sub(r'(\w+)', r'"\1"', raw)
            cleaned = cleaned.replace('""', '"')
            try:
                pii_map = json.loads(cleaned)
            except (json.JSONDecodeError, TypeError):
                pass
    if pii_map:
        all_tag_keys.add("PII")

    for tag_key in sorted(all_tag_keys):
        allowed = TAG_ALLOWED_VALUES.get(tag_key.lower(), "")
        if allowed:
            lines.append(f"CREATE TAG IF NOT EXISTS {tag_schema}.{tag_key} ALLOWED_VALUES {allowed};")
        else:
            lines.append(f"CREATE TAG IF NOT EXISTS {tag_schema}.{tag_key};")

    lines.append("")

    table_tags = []
    for key in GOVERNANCE_TAG_KEYS:
        if key in meta["parameters"]:
            table_tags.append(f"  {tag_schema}.{key.upper()} = '{meta['parameters'][key]}'")
    if table_tags:
        lines.append(f"ALTER ICEBERG TABLE {fqn} SET TAG")
        lines.append(",\n".join(table_tags) + ";")
        lines.append("")

    for col_name, method in pii_map.items():
        lines.append(f"ALTER ICEBERG TABLE {fqn} ALTER COLUMN {col_name.upper()} SET TAG {tag_schema}.PII = '{method}';")

    return "\n".join(lines)



def generate_dcm_table_definition(meta: dict, args) -> str:
    db_name = generate_database_name(args)
    schema_name = generate_schema_name(args)
    table_name = generate_snowflake_name(meta["table_name"], args)

    all_columns = meta["columns"] + meta["partition_keys"]

    col_defs = []
    for col in all_columns:
        sf_type = map_hive_type(col["type"])
        line = f"    {col['name'].upper()} {sf_type}"
        if col["comment"]:
            line += f" COMMENT '{escape_comment(col['comment'])}'"
        col_defs.append(line)

    ddl = f"DEFINE ICEBERG TABLE {db_name}.{schema_name}.{table_name} (\n"
    ddl += ",\n".join(col_defs)
    ddl += "\n)"

    table_comment = meta["table_comment"]
    if table_comment:
        ddl += f"\nCOMMENT = '{escape_comment(table_comment)}'"

    ddl += f"\nCATALOG = 'SNOWFLAKE'"
    ddl += f"\nEXTERNAL_VOLUME = '{args.external_volume}'"

    base_location = f"{meta['database']}/{meta['table_name']}"
    ddl += f"\nBASE_LOCATION = '{base_location}';"

    return ddl


def generate_distcp(meta: dict, args) -> str:
    source = meta["location"]
    if not source.endswith("/"):
        source += "/"
    target = f"{args.object_store_prefix}/{meta['database']}/{meta['table_name']}/"

    return f"""#!/bin/bash
hadoop distcp \\
  {source} \\
  {target}"""


def generate_dcm_manifest(args, table_metas: list) -> str:
    db_name = generate_database_name(args)
    schema_name = generate_schema_name(args)
    stage_name = generate_stage_name(args)

    lines = [
        "manifest:",
        "  version: \"1\"",
        f"  description: \"Hadoop Migration - {args.database} to Snowflake Managed Iceberg\"",
        "",
        "databases:",
        f"  - name: {db_name}",
        f"    comment: \"{args.domain} domain {args.env} environment\"",
        "    schemas:",
        f"      - name: {schema_name}",
        f"        comment: \"{args.maturity} ingestion layer (version {args.version})\"",
        "",
        "stages:",
        f"  - name: {db_name}.{schema_name}.{stage_name}",
        f"    url: \"{args.object_store_prefix}/\"",
        f"    storage_integration: {args.storage_integration}",
        "    file_format: \"(TYPE = PARQUET)\"",
        "",
        "iceberg_tables:",
    ]

    for meta in table_metas:
        sf_name = generate_snowflake_name(meta["table_name"], args)
        lines.append(f"  - name: {db_name}.{schema_name}.{sf_name}")
        lines.append(f"    external_volume: {args.external_volume}")
        lines.append(f"    base_location: \"{meta['database']}/{meta['table_name']}\"")
        if meta["table_comment"]:
            lines.append(f"    comment: \"{meta['table_comment']}\"")
        lines.append(f"    columns:")
        all_columns = meta["columns"] + meta["partition_keys"]
        for col in all_columns:
            sf_type = map_hive_type(col["type"])
            col_line = f"      - name: {col['name'].upper()}"
            lines.append(col_line)
            lines.append(f"        type: {sf_type}")
            if col["comment"]:
                lines.append(f"        comment: \"{col['comment']}\"")
        lines.append("")

    return "\n".join(lines)



    source = meta["location"]
    if not source.endswith("/"):
        source += "/"
    target = f"{args.object_store_prefix}/{meta['database']}/{meta['table_name']}/"

    return f"""#!/bin/bash
hadoop distcp \\
  {source} \\
  {target}"""


def process_database(args):
    jdbc_url = f"jdbc:hive2://hiveserver2:10000/"
    print(f"Connecting to HiveServer2 via Beeline...")
    print(f"Database: {args.database}")
    print(f"Target S3: {args.object_store_prefix}")
    print("")

    tables = get_tables(jdbc_url, args.database)
    if args.tables:
        table_filter = [t.strip() for t in args.tables.split(",")]
        tables = [t for t in tables if t in table_filter]

    print(f"Found {len(tables)} table(s) in database '{args.database}'")

    os.makedirs(args.output_dir, exist_ok=True)

    manifest = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_database": args.database,
        "snowflake_database": generate_database_name(args),
        "snowflake_schema": generate_schema_name(args),
        "external_volume": args.external_volume,
        "object_store_prefix": args.object_store_prefix,
        "naming": {
            "domain": args.domain,
            "env": args.env,
            "component": args.component,
            "maturity": args.maturity,
            "version": args.version,
        },
        "tables": [],
    }

    exported = 0
    skipped = 0
    summary_lines = []
    exported_metas = []

    for table_name in sorted(tables):
        print(f"\nProcessing: {args.database}.{table_name}")
        meta = extract_table_metadata(jdbc_url, args.database, table_name)

        table_entry = {
            "table_name": table_name,
            "source_location": meta["location"],
            "target_location": f"{args.object_store_prefix}/{meta['database']}/{meta['table_name']}/",
            "columns": len(meta["columns"]),
            "partition_keys": [pk["name"] for pk in meta["partition_keys"]],
            "is_parquet": meta["is_parquet"],
            "table_comment": meta["table_comment"],
        }

        if not meta["is_parquet"]:
            table_entry["status"] = "skipped"
            table_entry["reason"] = "not_parquet"
            table_entry["input_format"] = meta["input_format"]
            manifest["tables"].append(table_entry)
            skipped += 1
            summary_lines.append(f"  [SKIP] {table_name} (not Parquet: {meta['input_format']})")
            print(f"  SKIPPED: not Parquet (format: {meta['input_format']})")
            continue

        table_dir = os.path.join(args.output_dir, table_name)
        os.makedirs(table_dir, exist_ok=True)

        ddl = generate_create_iceberg_ddl(meta, args)
        with open(os.path.join(table_dir, "create_iceberg_table.sql"), "w") as f:
            f.write(ddl)

        copy_sql = generate_copy_into(meta, args)
        with open(os.path.join(table_dir, "copy_into.sql"), "w") as f:
            f.write(copy_sql)

        distcp = generate_distcp(meta, args)
        with open(os.path.join(table_dir, "distcp.sh"), "w") as f:
            f.write(distcp)

        with open(os.path.join(table_dir, "properties.json"), "w") as f:
            json.dump(meta["parameters"], f, indent=2)

        dcm_define = generate_dcm_table_definition(meta, args)
        with open(os.path.join(table_dir, "define_table.sql"), "w") as f:
            f.write(dcm_define)

        tags_sql = generate_tags_sql(meta, args)
        with open(os.path.join(table_dir, "tags.sql"), "w") as f:
            f.write(tags_sql)

        table_entry["status"] = "exported"
        table_entry["output_dir"] = table_dir
        manifest["tables"].append(table_entry)
        exported += 1
        exported_metas.append(meta)

        partition_info = ""
        if meta["partition_keys"]:
            pk_names = ", ".join(pk["name"] for pk in meta["partition_keys"])
            partition_info = f" (partitioned by: {pk_names})"
        summary_lines.append(f"  [OK] {table_name}{partition_info}")
        print(f"  EXPORTED: {len(meta['columns'])} cols, {len(meta['partition_keys'])} partition keys")

    with open(os.path.join(args.output_dir, "manifest.json"), "w") as f:
        json.dump(manifest, f, indent=2)

    dcm_manifest = generate_dcm_manifest(args, exported_metas)
    with open(os.path.join(args.output_dir, "dcm_manifest.yml"), "w") as f:
        f.write(dcm_manifest)

    summary = f"""=== Migration Summary ===
Source Database: {args.database}
Target: {generate_database_name(args)}.{generate_schema_name(args)}
S3: {args.object_store_prefix}
External Volume: {args.external_volume}
Tables found: {len(tables)}
Tables exported: {exported}
Tables skipped: {skipped}

{chr(10).join(summary_lines)}
"""
    with open(os.path.join(args.output_dir, "summary.txt"), "w") as f:
        f.write(summary)

    print(f"\n{summary}")
    print(f"Output written to: {args.output_dir}/")
    return exported, skipped


def main():
    parser = argparse.ArgumentParser(description="Hive HMS to Snowflake Managed Iceberg export")
    parser.add_argument("--hms-host", default="localhost", help="(unused, connects via docker exec)")
    parser.add_argument("--hms-port", type=int, default=9083, help="(unused, connects via docker exec)")
    parser.add_argument("--database", required=True, help="Hive database to export")
    parser.add_argument("--tables", default=None, help="Comma-separated table filter (default: all tables)")
    parser.add_argument("--external-volume", required=True, help="Snowflake external volume name")
    parser.add_argument("--storage-integration", default="MDAEPPEN_S3_INTEGRATION", help="Snowflake storage integration name")
    parser.add_argument("--object-store-prefix", required=True, help="Full S3/ADLS prefix for distcp target")
    parser.add_argument("--domain", default="HAM", help="Naming standard: domain code (default: HAM)")
    parser.add_argument("--env", default="DEV", help="Naming standard: environment (default: DEV)")
    parser.add_argument("--component", default="I", help="Naming standard: component letter (default: I)")
    parser.add_argument("--maturity", default="RAW", help="Naming standard: maturity level (default: RAW)")
    parser.add_argument("--version", default="001", help="Naming standard: schema version (default: 001)")
    parser.add_argument("--output-dir", default="workspace/output", help="Output directory (default: workspace/output)")

    args = parser.parse_args()
    exported, skipped = process_database(args)

    if exported == 0 and skipped > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
