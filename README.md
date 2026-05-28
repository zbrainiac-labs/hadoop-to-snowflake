# Hive/HMS to Snowflake Managed Iceberg -- Migration Showcase

Automated extraction of Hive Metastore metadata and conversion into Snowflake-managed Iceberg table DDL, governance tags, DCM manifests, and data copy commands. Includes a local Docker-based Hadoop/Hive environment for end-to-end demonstration and validation.

**WARNING: The local stack is non-production and suitable only for functional and integration testing.**

---

## Why Migrate from Hadoop to Snowflake

Organizations running Hadoop-based platforms manage a broad set of interdependent services: HDFS, Hive Metastore, HiveServer2, YARN, and surrounding operational infrastructure. This creates significant operational overhead in capacity planning, patching, scaling, and monitoring.

Snowflake provides a simpler target operating model:

- **Elastic compute** without cluster sizing or YARN queue management
- **Zero infrastructure** -- no HDFS, no Metastore database, no HiveServer2 tuning
- **Native governance** -- object tags, masking policies, and row access policies replace ad-hoc TBLPROPERTIES
- **Iceberg as a first-class format** -- Snowflake-managed Iceberg tables provide open table format benefits with managed catalog simplicity

The key challenge in migration is not moving files. It is **preserving metadata, governance context, and table semantics** so that downstream consumers and compliance controls survive the transition intact. This repository demonstrates that automated path.

---

## What This Showcase Demonstrates

- Automatic extraction of Hive/HMS metadata (columns, types, comments, partitions, TBLPROPERTIES)
- Generation of Snowflake-managed Iceberg DDL (`CREATE ICEBERG TABLE ... CATALOG='SNOWFLAKE'`)
- Preservation of governance metadata: domain, data owner, sensitivity, source system
- Column-level PII tagging from Hive `pii_map` properties to Snowflake `SET TAG` statements
- DCM (Database Change Management) declarative manifest generation
- Consistent naming convention applied to all generated Snowflake objects
- `COPY INTO` statements for data loading (with `MATCH_BY_COLUMN_NAME`)
- `hadoop distcp` commands for HDFS-to-S3 data export

---

## Migration Flow

```
Step 1          Step 2              Step 3              Step 4              Step 5
Generate        Load into HDFS      Read metadata       Convert to          Export Parquet
sample data     + register Hive     from Hive           Snowflake           to S3
(Parquet)       external tables     Metastore           artifacts

 [Host]    -->   [HDFS + Hive]  -->  [HMS Thrift]  -->  [Python Script] --> [S3 Bucket]
                                                              |
                                                              v
                                                     workspace/output/
                                                     ├── create_iceberg_table.sql
                                                     ├── define_table.sql (DCM)
                                                     ├── copy_into.sql
                                                     ├── tags.sql
                                                     ├── distcp.sh
                                                     ├── dcm_manifest.yml
                                                     └── manifest.json
```

1. **Generate sample Parquet data** -- `demo-scripts/generate-fake-data.py` creates 1650 rows across 3 related tables with governance TBLPROPERTIES baked in.
2. **Load into HDFS and register as Hive tables** -- `demo-scripts/init-data.sh` uploads Parquet to HDFS, creates external tables with comments, partitions, and governance properties (`domain`, `data_owner`, `sensitivity`, `pii_map`).
3. **Read metadata from Hive Metastore** -- The export script connects via Beeline, runs `DESCRIBE FORMATTED` for each table, and extracts columns, types, comments, partition keys, storage format, HDFS location, and all TBLPROPERTIES.
4. **Convert to Snowflake artifacts** -- Generates Iceberg DDL, DCM DEFINE statements, COPY INTO, governance tags (CREATE TAG + SET TAG), distcp commands, and a full manifest.
5. **Export Parquet to S3** -- `demo-scripts/export-to-s3.sh` copies files from HDFS preserving partition structure for Snowflake consumption.

---

## Generated Artifacts

After running the export script, `workspace/output/` contains:

```
workspace/output/
├── manifest.json                    # Full inventory of all tables processed
├── dcm_manifest.yml                 # DCM declarative deployment manifest
├── summary.txt                      # Human-readable migration report
├── customers/
│   ├── create_iceberg_table.sql     # CREATE ICEBERG TABLE (imperative DDL)
│   ├── define_table.sql             # DEFINE ICEBERG TABLE (DCM declarative)
│   ├── copy_into.sql                # COPY INTO with MATCH_BY_COLUMN_NAME
│   ├── distcp.sh                    # hadoop distcp HDFS -> S3
│   ├── tags.sql                     # CREATE TAG + SET TAG (table + column PII)
│   └── properties.json              # Raw TBLPROPERTIES from Hive
├── customer_transactions/           # Same structure per table
└── transaction_disputes/            # Same structure per table
```

---

## Naming Convention

All generated Snowflake objects follow a consistent naming standard controlled by CLI parameters:

| Parameter | CLI Flag | Default | Description |
| --- | --- | --- | --- |
| Domain | `--domain` | HAM | 3-char business domain code |
| Environment | `--env` | DEV | Environment: DEV, TE1, UAT, PRD |
| Component | `--component` | I | Component letter (I=Ingestion, T=Transform, A=Aggregation) |
| Maturity | `--maturity` | RAW | Data maturity: RAW, CUR, TRS, AGG, SRV, DAP |
| Version | `--version` | 001 | Schema version (V001, V002, ...) |

**Transformation rules:**

| Object Type | Pattern | Example |
| --- | --- | --- |
| Database | `{DOMAIN}_{ENV}` | `HAM_DEV` |
| Schema | `{DOMAIN}_{MATURITY}_V{VERSION}` | `HAM_RAW_V001` |
| Table | `{DOMAIN}{COMPONENT}_{MATURITY}_TB_{TABLE}` | `HAMI_RAW_TB_CUSTOMERS` |
| Stage | `{DOMAIN}{COMPONENT}_{MATURITY}_ST_ICEBERG` | `HAMI_RAW_ST_ICEBERG` |
| External Volume | (user-specified) | `HAM_ICEBERG_VOL` |

---

## Quickstart

```bash
# Generate fake Parquet data (host-side, requires pyarrow)
pip install pyarrow
python3 demo-scripts/generate-fake-data.py

# Start the full stack (6 containers)
docker compose up -d

# Check all services are healthy
docker compose ps

# Load sample data into HDFS + Hive (run from host)
./demo-scripts/init-data.sh

# Run validation
./demo-scripts/validate.sh

# Generate Snowflake Iceberg DDL + DCM + tags from HMS
pip install hmsclient thrift
python3 demo-scripts/hive_hms_to_horizon_zero_copy.py \
  --database test_db \
  --external-volume HAM_ICEBERG_VOL \
  --object-store-prefix s3://mdaeppen/hadoop-root \
  --domain HAM --env DEV --component I --maturity RAW --version 001

# Export Parquet from HDFS to S3
./demo-scripts/export-to-s3.sh

# Stop the stack
docker compose down

# Full reset (removes all data)
docker compose down -v
```

---

## Local Source Environment

### Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                      hadoop-test-net                         │
│                                                              │
│  ┌──────────┐   ┌──────────┐                                 │
│  │ NameNode │───│ DataNode │            HDFS Layer           │
│  │  :9870   │   │  :9864   │            (ARM64 native)       │
│  └────┬─────┘   └────┬─────┘                                 │
│       │               │                                      │
│  ┌────┴───────────────┴─────┐                                │
│  │    Hive Metastore        │                                │
│  │    :9083 (Derby)         │           Catalog Layer        │
│  └────────────┬─────────────┘           (ARM64 native)       │
│               │                                              │
│  ┌────────────┴─────────────┐                                │
│  │    HiveServer2           │                                │
│  │    :10000 / :10002       │           Query Layer          │
│  └────────────┬─────────────┘           (ARM64 native)       │
│               │                                              │
│  ┌────────────┴─────────────┐   ┌──────────────┐             │
│  │    Hue                   │───│ Hue Postgres │             │
│  │    :8888                 │   │ (backend DB) │             │
│  └──────────────────────────┘   └──────────────┘             │
│               (amd64/Rosetta)                                │
└──────────────────────────────────────────────────────────────┘
```

### Container Images

| Container | Image | Platform |
| --- | --- | --- |
| NameNode | `sbloodys/hadoop:3.3.6` | linux/amd64 + linux/arm64 |
| DataNode | `sbloodys/hadoop:3.3.6` | linux/amd64 + linux/arm64 |
| Hive Metastore | `apache/hive:4.1.0` | linux/amd64 + linux/arm64 |
| HiveServer2 | `apache/hive:4.1.0` | linux/amd64 + linux/arm64 |
| Hue | `gethue/hue:4.11.0` | linux/amd64 (Rosetta on Apple Silicon) |
| Hue PostgreSQL | `postgres:16-alpine` | linux/amd64 + linux/arm64 |

### Exposed Ports

| Service | Port | URL |
| --- | --- | --- |
| NameNode Web UI | 9870 | http://localhost:9870 |
| DataNode Web UI | 9864 | http://localhost:9864 |
| HDFS RPC | 9900 | -- |
| Hive Metastore Thrift | 9083 | -- |
| HiveServer2 JDBC | 10000 | `jdbc:hive2://localhost:10000/` |
| HiveServer2 Web UI | 10002 | http://localhost:10002 |
| Hue Web UI | 8888 | http://localhost:8888 |

### Default Credentials

| Service | Username | Password |
| --- | --- | --- |
| HiveServer2 (Beeline) | hive | (no password) |
| Hue | admin | admin (set on first visit) |
| Hue PostgreSQL | hue | hue |

These credentials are for local testing only.

### Sample Data

After running `./demo-scripts/init-data.sh`:

- **Database**: `test_db`
- **Tables**: 3 related tables (master + 2 detail)
- **Total rows**: 1650
- **Format**: Parquet on HDFS
- **TBLPROPERTIES**: governance tags (domain, data_owner, sensitivity, source_system, pii_map)

| Table | Rows | Partitions | PII Columns |
| --- | --- | --- | --- |
| customers | 500 | none | email (sha2), first_name (mask), last_name (mask) |
| customer_transactions | 1000 | status (3) | transaction_id (pseudonymize) |
| transaction_disputes | 150 | resolution_status (4) | dispute_id (pseudonymize), customer_id (mask) |

### Connecting to Hive

```bash
# Via Beeline inside the container
docker exec -it hiveserver2 beeline -u 'jdbc:hive2://hiveserver2:10000/'

# Via Beeline from host (if installed)
beeline -u 'jdbc:hive2://localhost:10000/'
```

---

## Project Structure

```
.
├── README.md
├── docker-compose.yml
├── .env                             # Externalized image tags, ports, paths
├── requirements.txt                 # Python dependencies (hmsclient, thrift)
├── hadoop_test_stack_requirements.md
├── manifest.yml                     # DCM project manifest
├── sources/
│   └── definitions/
│       └── stage.sql                # DEFINE STAGE template
├── config/
│   ├── core-site.xml                # HDFS NameNode address
│   ├── hdfs-site.xml                # Replication factor
│   ├── hive-site.xml                # HiveServer2 web UI settings
│   └── hue.ini                      # Hue Hive/PostgreSQL connector config
├── demo-scripts/
│   ├── generate-fake-data.py        # Generates 1650 rows across 3 tables
│   ├── init-data.sh                 # Loads data into HDFS + Hive + TBLPROPERTIES
│   ├── hive_hms_to_horizon_zero_copy.py  # HMS -> Snowflake DDL + DCM + tags
│   ├── export-to-s3.sh             # HDFS -> S3 upload
│   ├── validate.sh                  # Full acceptance checklist
│   └── run-e2e-demo.sh             # End-to-end demo runner
└── workspace/
    ├── data/                        # Generated Parquet partitions
    ├── export/                      # HDFS export staging
    └── output/                      # Generated DDL, DCM, tags, manifests
```

---

## Terminology

| Term | Meaning |
| --- | --- |
| HMS | Hive Metastore Service -- the Thrift-based catalog that stores table metadata |
| Zero-copy | Registering existing Parquet files in Snowflake without re-ingesting (via `ADD_FILES_REFERENCE` for external Iceberg, or direct `COPY INTO` for Snowflake-managed Iceberg) |
| DCM | Snowflake Database Change Management -- declarative YAML-driven deployment model |
| Snowflake-managed Iceberg | Iceberg table where Snowflake owns the catalog, metadata, and lifecycle (`CATALOG='SNOWFLAKE'`) |
| TBLPROPERTIES | Hive key-value metadata on tables, used here to carry governance attributes |

---

## Troubleshooting

### Containers not starting

```bash
docker compose logs namenode
docker compose logs metastore
docker compose logs hiveserver2
```

### NameNode stuck in safe mode

```bash
docker exec namenode hdfs dfsadmin -safemode leave
```

### Metastore schema not initialized

Derby auto-initializes on first boot. If corrupted, reset:

```bash
docker compose down -v
docker compose up -d
```

### Hue "database is locked" errors

Hue uses PostgreSQL as its backend DB to avoid SQLite locking. If errors persist:

```bash
docker compose restart hue
```

### Hue cannot connect to Hive

Verify HiveServer2 is healthy first:

```bash
docker compose ps hiveserver2
docker exec hiveserver2 beeline -u 'jdbc:hive2://hiveserver2:10000/' -e 'SHOW DATABASES;'
```

### Port conflicts

Edit `.env` to change exposed ports if defaults conflict with local services. The HDFS RPC port defaults to 9900 (not 9000) to avoid conflicts.

---

## Known Limitations

- Hue runs under Rosetta on Apple Silicon (no ARM64 image available) and may show empty query results
- HiveServer2 Web UI (http://localhost:10002) is the most reliable query interface
- Stack startup takes ~60s on first boot (NameNode format + Derby init)
- Subsequent starts with existing volumes are faster (~30s)
- `ADD_FILES_REFERENCE` is not supported for Snowflake-managed Iceberg tables; standard `COPY INTO` with `MATCH_BY_COLUMN_NAME` is used instead

---

## Extending the Stack

The network model supports adding containers without redesign:

```yaml
spark-master:
  image: apache/spark:3.5.0
  networks:
    - hadoop-test-net

trino:
  image: trinodb/trino:440
  networks:
    - hadoop-test-net
```

---

## Validation Checklist

| Check | Command |
| --- | --- |
| All containers healthy | `docker compose ps` |
| NameNode UI | `curl -s http://localhost:9870` |
| Hue UI | `curl -s http://localhost:8888` |
| HiveServer2 Web UI | `curl -s http://localhost:10002` |
| Hive responds | `docker exec hiveserver2 beeline -u 'jdbc:hive2://hiveserver2:10000/' -e 'SHOW DATABASES;'` |
| HDFS writable | `docker exec namenode hdfs dfs -mkdir -p /tmp/test && docker exec namenode hdfs dfs -rmdir /tmp/test` |
| Sample data | `docker exec hiveserver2 beeline -u 'jdbc:hive2://hiveserver2:10000/' -e 'SELECT COUNT(*) FROM test_db.customer_transactions;'` |
