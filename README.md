# Hadoop Test Stack

Local Docker Compose stack for testing the Hive-to-Iceberg migration workflow.

**WARNING: This is a non-production test environment. Do not use for production workloads.**

## Architecture

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

## Prerequisites

| Requirement | Minimum |
| --- | --- |
| Docker Engine | 24.0+ |
| Docker Compose | v2.20+ |
| RAM (available) | 8 GB |
| Disk (free) | 10 GB |
| OS | macOS (Apple Silicon supported), Linux, or Windows with WSL2 |
| Python 3 + pyarrow | For generating fake data |

## Quickstart

```bash
# Generate fake Parquet data (host-side, requires pyarrow)
pip install pyarrow
python3 scripts/generate-fake-data.py

# Start the full stack (6 containers)
docker compose up -d

# Check all services are healthy
docker compose ps

# Load sample data into HDFS + Hive (run from host)
./scripts/init-data.sh

# Run validation
./scripts/validate.sh

# Generate Snowflake Iceberg DDL + DCM + tags from HMS
pip install hmsclient thrift
python3 scripts/hive_hms_to_horizon_zero_copy.py \
  --database test_db \
  --external-volume HAM_ICEBERG_VOL \
  --object-store-prefix s3://mdaeppen/hadoop-root \
  --domain HAM --env DEV --component I --maturity RAW --version 001

# Export Parquet from HDFS to S3
./scripts/export-to-s3.sh

# Stop the stack
docker compose down

# Full reset (removes all data)
docker compose down -v
```

## Container Images

| Container | Image | Platform |
| --- | --- | --- |
| NameNode | `sbloodys/hadoop:3.3.6` | linux/amd64 + linux/arm64 |
| DataNode | `sbloodys/hadoop:3.3.6` | linux/amd64 + linux/arm64 |
| Hive Metastore | `apache/hive:4.1.0` | linux/amd64 + linux/arm64 |
| HiveServer2 | `apache/hive:4.1.0` | linux/amd64 + linux/arm64 |
| Hue | `gethue/hue:4.11.0` | linux/amd64 (Rosetta on Apple Silicon) |
| Hue PostgreSQL | `postgres:16-alpine` | linux/amd64 + linux/arm64 |

## Exposed Ports

| Service | Port | URL |
| --- | --- | --- |
| NameNode Web UI | 9870 | http://localhost:9870 |
| DataNode Web UI | 9864 | http://localhost:9864 |
| HDFS RPC | 9900 | — |
| Hive Metastore Thrift | 9083 | — |
| HiveServer2 JDBC | 10000 | `jdbc:hive2://localhost:10000/` |
| HiveServer2 Web UI | 10002 | http://localhost:10002 |
| Hue Web UI | 8888 | http://localhost:8888 |

## Default Credentials

| Service | Username | Password |
| --- | --- | --- |
| HiveServer2 (Beeline) | hive | (no password) |
| Hue | admin | admin (set on first visit) |
| Hue PostgreSQL | hue | hue |

These credentials are for local testing only.

## Connecting to Hive

```bash
# Via Beeline inside the container (recommended)
docker exec -it hiveserver2 beeline -u 'jdbc:hive2://hiveserver2:10000/'

# Via Beeline from host (if installed)
beeline -u 'jdbc:hive2://localhost:10000/'
```

## Sample Data

After running `./scripts/init-data.sh`, the following is available:

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

```sql
USE test_db;
SELECT COUNT(*) FROM customer_transactions;
SELECT status, COUNT(*) FROM customer_transactions GROUP BY status;
SHOW CREATE TABLE customer_transactions;
DESCRIBE FORMATTED customer_transactions;
```

## Hive-to-Snowflake Iceberg Migration

Export Hive metadata and generate Snowflake-managed Iceberg DDL:

```bash
# Generate Snowflake DDL + DCM manifests + tags from HMS metadata
python3 scripts/hive_hms_to_horizon_zero_copy.py \
  --database test_db \
  --external-volume HAM_ICEBERG_VOL \
  --object-store-prefix s3://mdaeppen/hadoop-root \
  --domain HAM --env DEV --component I --maturity RAW --version 001

# Export Parquet from HDFS to S3
./scripts/export-to-s3.sh
```

**Generated output** (`workspace/output/`):

```
workspace/output/
├── manifest.json                    # Full inventory
├── dcm_manifest.yml                 # DCM declarative manifest
├── summary.txt                      # Human-readable report
├── customers/
│   ├── create_iceberg_table.sql     # CREATE ICEBERG TABLE (imperative)
│   ├── define_table.sql             # DEFINE ICEBERG TABLE (DCM)
│   ├── copy_into_add_files_reference.sql
│   ├── copy_into_full_ingest.sql
│   ├── distcp.sh                    # hadoop distcp HDFS -> S3
│   ├── tags.sql                     # CREATE TAG + SET TAG (table + column PII)
│   └── properties.json              # Raw TBLPROPERTIES
├── customer_transactions/           # Same structure
└── transaction_disputes/            # Same structure
```

**Snowflake naming convention**:

| Object | Name |
| --- | --- |
| Database | `HAM_DEV` |
| Schema | `HAM_RAW_V001` |
| Tables | `HAMI_RAW_TB_CUSTOMERS`, `HAMI_RAW_TB_CUSTOMER_TRANSACTIONS`, `HAMI_RAW_TB_TRANSACTION_DISPUTES` |
| Stage | `HAMI_RAW_ST_ICEBERG` |
| External Volume | `HAM_ICEBERG_VOL` |

## Project Structure

```
hadoop/
├── docker-compose.yml              # Stack definition (6 containers)
├── .env                            # Externalized configuration
├── requirements.txt                # Python dependencies (hmsclient, thrift)
├── hadoop_test_stack_requirements.md
├── README.md
├── config/
│   ├── core-site.xml               # HDFS NameNode address
│   ├── hdfs-site.xml               # Replication factor
│   ├── hive-site.xml               # HiveServer2 web UI settings
│   └── hue.ini                     # Hue Hive/PostgreSQL connector config
├── dcm/
│   ├── manifest.yml                # Static DCM manifest template
│   ├── tables.sql                  # DEFINE TABLE statements
│   └── stages.sql                  # DEFINE STAGE statements
├── scripts/
│   ├── generate-fake-data.py       # Generates 1650 rows across 3 tables
│   ├── init-data.sh                # Loads data into HDFS + Hive + TBLPROPERTIES
│   ├── hive_hms_to_horizon_zero_copy.py  # HMS export -> Snowflake DDL + DCM + tags
│   ├── export-to-s3.sh             # HDFS -> S3 upload
│   ├── extract-metadata.sh         # SHOW CREATE TABLE + DESCRIBE
│   ├── validate.sh                 # Full acceptance checklist
│   └── run-migration-test.sh       # Migration script runner
└── workspace/
    ├── data/                       # Generated Parquet partitions
    ├── export/                     # HDFS export staging
    └── output/                     # Generated DDL, DCM, tags, manifests
```

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

Hue uses PostgreSQL as its backend DB to avoid SQLite locking. If errors persist, restart Hue:

```bash
docker compose restart hue
```

### Hue cannot connect to Hive

Verify HiveServer2 is healthy first:

```bash
docker compose ps hiveserver2
docker exec hiveserver2 beeline -u 'jdbc:hive2://hiveserver2:10000/' -e 'SHOW DATABASES;'
```

### Hue shows empty results for queries

This is a known Hue bug under Rosetta emulation. Use Beeline or the HiveServer2 Web UI (http://localhost:10002) for reliable query results.

### Port conflicts

Edit `.env` to change exposed ports if defaults conflict with local services. The HDFS RPC port defaults to 9900 (not 9000) to avoid conflicts.

## Extending the Stack

The network model supports adding containers without redesign. Examples:

```yaml
# Add to docker-compose.yml
spark-master:
  image: apache/spark:3.5.0
  networks:
    - hadoop-test-net

trino:
  image: trinodb/trino:440
  networks:
    - hadoop-test-net
```

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

## Known Limitations

- Hue runs under Rosetta on Apple Silicon (no ARM64 image available) and may show empty query results
- HiveServer2 Web UI (http://localhost:10002) is the most reliable query interface
- Stack startup takes ~60s on first boot (NameNode format + Derby init)
- Subsequent starts with existing volumes are faster (~30s)
