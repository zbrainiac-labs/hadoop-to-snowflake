# Docker Compose Requirements for Hadoop Test Stack

## Scope

Local, containerized Hadoop test stack for validating the Hive-to-Iceberg migration workflow. The stack must run with Docker Compose using multiple containers and include HDFS, Hive Metastore, Hive, and Hue.

**This stack is non-production and suitable only for functional and integration testing.**

---

## 1. Orchestration and Networking

| Id | Short Description | Status |
| --- | --- | --- |
| RQ-001 | Use Docker Compose as the orchestration mechanism for the local test stack. | Implemented |
| RQ-002 | Deploy the stack as multiple containers, with each major service isolated in its own container. | Implemented |
| RQ-012 | Configure all containers to communicate over a dedicated Docker Compose network. | Implemented |
| RQ-013 | Use container names or DNS-resolvable service names for all inter-service connections. | Implemented |
| RQ-030 | Keep the stack runnable on a single developer workstation without requiring Kubernetes. | Implemented |
| RQ-038 | Support extension with additional containers later, such as Spark, Trino, or MinIO, without redesigning the network model. | Implemented |
| RQ-039 | Ensure the Compose file structure is readable and maintainable, with environment variables externalized where practical. | Implemented |
| RQ-045 | Provide a `.env` file externalizing all image tags, exposed ports, and configurable paths. | Implemented |

---

## 2. HDFS Services

| Id | Short Description | Status |
| --- | --- | --- |
| RQ-003 | Provide an HDFS NameNode container. | Implemented |
| RQ-004 | Provide at least one HDFS DataNode container. | Implemented |
| RQ-005 | Expose HDFS over the standard service ports required for CLI and service integration. | Implemented |
| RQ-014 | Persist HDFS metadata and data across container restarts using Docker volumes. | Implemented |
| RQ-041 | Use `sbloodys/hadoop:3.3.6` (ARM64-native) as the base image for HDFS NameNode and DataNode. | Implemented |

---

## 3. Hive Services

| Id | Short Description | Status |
| --- | --- | --- |
| RQ-006 | Include a Hive Metastore service as a dedicated container. | Implemented |
| RQ-008 | Include a HiveServer2 container for executing Hive SQL and DDL. | Implemented |
| RQ-009 | Provide Hive CLI access via `docker exec` into the HiveServer2 container using Beeline for running automated setup and test scripts. | Implemented |
| RQ-015 | Persist Hive Metastore database state (Derby) across container restarts using Docker volumes. | Implemented |
| RQ-016 | Persist Hive warehouse data in a Docker volume or mounted host path. | Implemented |
| RQ-017 | Support deterministic startup order so that HDFS and Metastore are available before HiveServer2 starts. | Implemented |
| RQ-019 | Hive Metastore schema is auto-created on first startup via embedded Derby (no manual schematool bootstrap required). | Implemented |
| RQ-042 | Use `apache/hive:4.1.0` (ARM64-native) for Hive Metastore and HiveServer2 containers. | Implemented |
| RQ-043 | Use embedded Apache Derby as the Hive Metastore database (no external RDBMS required for testing). | Implemented |

---

## 4. Hue and UI

| Id | Short Description | Status |
| --- | --- | --- |
| RQ-010 | Include a Hue container as the web interface for browsing HDFS and querying Hive metadata. | Implemented |
| RQ-011 | Expose the Hue web UI on a host port suitable for local browser access. | Implemented |
| RQ-044 | Use `gethue/hue:4.11.0` (amd64 only, runs via Rosetta on Apple Silicon) for the Hue web UI container, backed by PostgreSQL to avoid SQLite locking. | Implemented |

---

## 5. Data and Testing

| Id | Short Description | Status |
| --- | --- | --- |
| RQ-020 | Support automated creation of one or more sample Hive databases and tables for test execution. Depends on HiveServer2 being healthy (RQ-018). | Implemented |
| RQ-021 | Support loading sample Parquet test data into HDFS. | Implemented |
| RQ-022 | Ensure the sample Hive tables point to HDFS-backed data locations. | Implemented |
| RQ-023 | Provide a repeatable way to execute `SHOW CREATE TABLE` or equivalent DDL extraction against Hive. | Implemented |
| RQ-024 | Provide a repeatable way to query Hive Metastore metadata for table locations, schemas, and partition definitions. | Implemented |
| RQ-025 | Support test execution of the migration script that reads Hive metadata and generates Snowflake Iceberg DDL. | Implemented |
| RQ-026 | Support exporting or copying HDFS table data from containerized HDFS paths to mounted target paths for test validation. | Implemented |
| RQ-048 | Generate exactly 1 test table (`TEST_DB.CUSTOMER_TRANSACTIONS`) with 1000 rows of fake transactional data in Parquet format stored on HDFS. | Implemented |
| RQ-049 | The fake data table must be partitioned (by STATUS) and queryable via HiveServer2 immediately after bootstrap. | Implemented |
| RQ-050 | The migration test script accepts a Beeline JDBC URL and an output directory path, mounted from the local workspace (ref RQ-027). | Implemented |

---

## 6. Operations and Lifecycle

| Id | Short Description | Status |
| --- | --- | --- |
| RQ-018 | Add health checks with interval 10s, timeout 30s, and 5 retries for HDFS, Hive Metastore, HiveServer2, and Hue. | Implemented |
| RQ-027 | Allow mounting a local workspace into one or more containers for scripts, test fixtures, and generated output. | Implemented |
| RQ-028 | Store logs from all containers in a way that is accessible with standard Docker Compose commands. | Implemented |
| RQ-029 | Use pinned image tags rather than floating latest tags to ensure reproducibility. | Implemented |
| RQ-031 | Provide a single command to start the full environment (`docker compose up -d`). | Implemented |
| RQ-032 | Provide a single command to stop and remove the environment (`docker compose down`). | Implemented |
| RQ-033 | Provide an optional command or profile to reset volumes and reinitialize the environment from scratch (`docker compose down -v`). | Implemented |
| RQ-040 | Provide a validation checklist confirming HDFS, Hive Metastore, HiveServer2, and Hue are all operational after startup. | Implemented |
| RQ-046 | Define container resource limits appropriate for a single developer workstation (max 2GB RAM per container). | Implemented |
| RQ-047 | Define health check intervals (10s), timeouts (30s), and retries (5) for all critical services. | Implemented |

---

## 7. Documentation and Governance

| Id | Short Description | Status |
| --- | --- | --- |
| RQ-034 | Document all required host prerequisites, including Docker Engine 24+, Docker Compose v2, 8GB RAM, and 10GB disk. | Implemented |
| RQ-035 | Document all exposed ports and default credentials used only for local testing. | Implemented |
| RQ-036 | Mark the stack as non-production and suitable only for functional and integration testing. | Implemented |
| RQ-037 | Keep security settings pragmatic for local testing, but avoid unnecessary anonymous access between services. | Implemented |

---

## 8. Hive-to-Snowflake Iceberg Export (Zero-Copy Migration)

| Id | Short Description | Status |
| --- | --- | --- |
| RQ-051 | Provide a Python script (`hive_hms_to_horizon_zero_copy.py`) that reads table metadata from the Hive Metastore via Thrift (hmsclient). | Implemented |
| RQ-052 | The export script must dynamically discover and process ALL tables within the specified database (no hardcoded table names). | Implemented |
| RQ-053 | The export script must extract full metadata per table: column names, data types, column comments, table comment, partition keys, storage format, HDFS location, SerDe, and table properties. | Implemented |
| RQ-054 | The export script must generate `CREATE ICEBERG TABLE ... CATALOG='SNOWFLAKE'` DDL for each source Hive table, including column names, types, and comments. | Implemented |
| RQ-055 | The export script must generate `hadoop distcp` commands to copy Parquet files from the Hive table HDFS location to the target Iceberg base path on object storage. | Implemented |
| RQ-056 | The export script must generate `COPY INTO ... LOAD_MODE = ADD_FILES_REFERENCE` statements to register existing Parquet files in Snowflake without re-ingesting data (zero-copy pattern). | Implemented |
| RQ-057 | The export script must accept CLI parameters: `--hms-host`, `--hms-port`, `--database`, `--external-volume`, `--base-root`, `--object-store-prefix`, `--stage-name`, `--snowflake-schema`. | Implemented |
| RQ-058 | The export script must support an optional `--tables` filter (comma-separated) to process a subset of tables; if omitted, ALL tables in the database are processed. | Implemented |
| RQ-059 | The export script must support emit-only mode (default) that writes SQL files and a manifest without executing anything. | Implemented |
| RQ-060 | The export script must support execution mode (`--execute-distcp`, `--execute-sql`) for running distcp and Snowflake SQL commands directly. | Implemented |
| RQ-061 | The export script must produce a `manifest.json` file listing all discovered tables, processing status (exported/skipped), source locations, target Iceberg paths, partition info, and generated SQL file paths. | Implemented |
| RQ-062 | The export script must flag partitioned Hive tables in the manifest for manual validation before execution. | Implemented |
| RQ-063 | The export script must only process Parquet-backed Hive tables; non-Parquet tables (ORC, TEXTFILE, AVRO, etc.) must be skipped with a warning in the manifest. | Implemented |
| RQ-064 | The export script must map Hive data types to Snowflake Iceberg-compatible types (STRING->VARCHAR, INT->INT, DOUBLE->DOUBLE, DECIMAL->NUMBER, BIGINT->BIGINT, BOOLEAN->BOOLEAN, TIMESTAMP->TIMESTAMP_NTZ, DATE->DATE, BINARY->BINARY, ARRAY->ARRAY, MAP->OBJECT, STRUCT->OBJECT). | Implemented |
| RQ-065 | The export script must be testable against the local Docker Compose test stack (HMS at `metastore:9083`, HDFS at `namenode:9000`). | Implemented |
| RQ-066_a | Provide a `requirements.txt` or inline dependency list for the export script: `hmsclient`, `thrift-sasl`, `sasl`. | Implemented |
| RQ-066_b | The export script must handle tables with no data gracefully (emit DDL but skip distcp/COPY INTO, noted in manifest). | Implemented |
| RQ-066_c | The export script must preserve table and column comments from Hive metadata in the generated Snowflake DDL. | Implemented |
| RQ-066_d | The export script must export table properties (TBLPROPERTIES) as a JSON sidecar file per table for reference during migration review. | Implemented |
| RQ-066_e | The export script must produce a summary report at the end: total tables found, exported, skipped, with reasons. | Implemented |

---

## 9. Hive-to-Snowflake Managed Iceberg Migration

**Purpose**: Migrate Hive table data (Parquet on HDFS) directly into Snowflake-managed Iceberg tables. Snowflake manages the Iceberg catalog, metadata, and lifecycle — the Parquet files are copied to S3 and registered via `COPY INTO ... ADD_FILES_REFERENCE` (zero-copy) or loaded via `COPY INTO` (full ingest). No intermediate Iceberg catalog (Glue, Hive, MinIO) is needed.

| Id | Short Description | Status |
| --- | --- | --- |
| RQ-066 | Export Parquet data files from HDFS to a local staging path (`workspace/export/`) accessible from the host. | Implemented |
| RQ-067 | Provide a script (`scripts/export-from-hdfs.sh`) that copies Parquet files from HDFS to the local export directory, preserving partition structure. | Implemented |
| RQ-068 | The export script must generate a Snowflake `CREATE ICEBERG TABLE ... CATALOG='SNOWFLAKE'` DDL referencing an external volume and base location on S3. | Implemented |
| RQ-069 | The generated Snowflake DDL must use the Snowflake-managed Iceberg pattern: `EXTERNAL_VOLUME`, `CATALOG='SNOWFLAKE'`, `BASE_LOCATION`. | Implemented |
| RQ-070 | The generated DDL must include all column definitions with Snowflake-compatible types mapped from Hive (STRING->VARCHAR, INT->INT, DOUBLE->DOUBLE, DECIMAL->NUMBER, TIMESTAMP->TIMESTAMP_NTZ, BOOLEAN->BOOLEAN, BIGINT->BIGINT, BINARY->BINARY). | Implemented |
| RQ-071 | The generated DDL must preserve table-level and column-level comments from Hive metadata. | Implemented |
| RQ-072 | Provide a `COPY INTO` statement using `LOAD_MODE = ADD_FILES_REFERENCE` for zero-copy registration of Parquet files already uploaded to S3. | Implemented |
| RQ-073 | Provide an alternative `COPY INTO` statement using `LOAD_MODE = FULL_INGEST` for cases where data transformation or compaction is needed. | Implemented |
| RQ-074 | Document the prerequisite Snowflake objects: external volume, stage, and IAM role/policy for S3 access. | Implemented |
| RQ-075 | Provide a migration demo script (`scripts/migrate-to-snowflake-iceberg.sh`) that orchestrates the full flow: extract metadata, export Parquet, generate DDL, and output ready-to-run Snowflake SQL. | Implemented |

---

## 10. Naming Standards, Tags, and Deployment Model

| Id | Short Description | Status |
| --- | --- | --- |
| RQ-076 | Extract and preserve tags/labels from Hive table properties (TBLPROPERTIES), HMS metadata, and HDFS attributes during export. | Implemented |
| RQ-077 | All Snowflake artifacts must follow naming standards: Database=`{DOMAIN}_{ENV}`, Schema=`{DOMAIN}_{MATURITY}_V{NNN}`, Objects=`{DOMAIN}{COMP}_{MATURITY}_{TYPE}_{TEXT}`. Domain=HAM, ENV=DEV, COMP=I, MATURITY=RAW, VERSION=001, TYPE: TB=table, ST=stage. | Implemented |
| RQ-078 | The export script must generate object names conforming to the naming standard, accepting `--domain`, `--component`, `--maturity`, `--version`, `--env` CLI parameters. | Implemented |
| RQ-079 | Use Snowflake DCM (Database Change Management) model for deployment — generate declarative YAML manifests instead of imperative CREATE OR REPLACE DDL. | Implemented |
| RQ-080 | Data loading uses standard `COPY INTO` with `MATCH_BY_COLUMN_NAME = CASE_INSENSITIVE` into Snowflake-managed Iceberg tables. Note: `ADD_FILES_REFERENCE` is not supported for Snowflake-managed Iceberg (only for externally-managed Iceberg). | Implemented |
| RQ-081 | Create a dedicated external volume (`HAM_ICEBERG_VOL`) pointing to `s3://mdaeppen/hadoop-root/` — do not reuse GLUE-related volumes. | Implemented |
| RQ-082 | Each Hive source table must have TBLPROPERTIES set as the root-source for governance metadata: `domain`, `data_owner`, `sensitivity`, `source_system`. | Implemented |
| RQ-083 | Each Hive source table must have a `pii_map` TBLPROPERTY containing a JSON object mapping column names to their PII masking method (e.g. `{"email": "sha2", "first_name": "mask"}`). | Implemented |
| RQ-084 | The export script must parse `pii_map` from TBLPROPERTIES and generate Snowflake column-level `ALTER TABLE ... ALTER COLUMN ... SET TAG PII = '<method>'` statements. | Implemented |
| RQ-085 | The export script must parse table-level governance TBLPROPERTIES (`domain`, `data_owner`, `sensitivity`, `source_system`) and generate Snowflake table-level `ALTER TABLE ... SET TAG` statements. | Implemented |
| RQ-086 | The export script must generate `CREATE TAG IF NOT EXISTS` DDL for all referenced tag keys before the `SET TAG` statements. | Implemented |
| RQ-087 | The generated tag DDL must be written to a separate file per table (`tags.sql`) in the output directory. | Implemented |
| --- | --- | --- | --- | --- |
| MC-001 | NameNode | `sbloodys/hadoop:3.3.6` | amd64 + arm64 | Implemented |
| MC-002 | DataNode | `sbloodys/hadoop:3.3.6` | amd64 + arm64 | Implemented |
| MC-003 | Hive Metastore (Derby) | `apache/hive:4.1.0` | amd64 + arm64 | Implemented |
| MC-004 | HiveServer2 | `apache/hive:4.1.0` | amd64 + arm64 | Implemented |
| MC-005 | Hue | `gethue/hue:4.11.0` | amd64 only | Implemented |
| MC-006 | Hue PostgreSQL | `postgres:16-alpine` | amd64 + arm64 | Implemented |

---

## Completed Fixes (no formal RQ needed)

| # | Fix | Status |
| --- | --- | --- |
| FIX-001 | Dropped database `HADOOP_MIGRATION` and all artifacts. | Done |
| FIX-002 | Data stored at `s3://mdaeppen/hadoop-root/` (not `s3://mdaeppen/glue/hadoop-root/`). | Done |
| FIX-003 | `ADD_FILES_REFERENCE` not supported for Snowflake-managed Iceberg. Using standard `COPY INTO` with `MATCH_BY_COLUMN_NAME`. | Done |
| FIX-004 | External volume is `HAM_ICEBERG_VOL` (not `GLUE_ICEBERG_VOL`). Points to `s3://mdaeppen/hadoop-root/`. | Done |
| FIX-005 | IAM role trust policy updated with new external ID for `HAM_ICEBERG_VOL`. | Done |
| FIX-006 | IAM role permission policy updated to allow `s3://mdaeppen/hadoop-root/*`. | Done |
| FIX-007 | Storage integration `MDAEPPEN_S3_INTEGRATION` updated to allow `s3://mdaeppen/hadoop-root/`. | Done |

| Id | Short Description | Validates | Status |
| --- | --- | --- | --- |
| AC-001 | `docker compose up -d` starts the full stack successfully and all containers report healthy within 2 minutes. | RQ-001, RQ-017, RQ-018, RQ-031 | Passed |
| AC-002 | Hue opens in the browser at `http://localhost:8888` and can connect to Hive. | RQ-010, RQ-011, RQ-044 | Passed |
| AC-003 | Hive can list databases and tables stored in the Metastore via Beeline. | RQ-006, RQ-008, RQ-020 | Passed |
| AC-004 | HDFS can store and return sample Parquet files via `hdfs dfs` commands. | RQ-003, RQ-004, RQ-021 | Passed |
| AC-005 | The migration test script can read Hive metadata and generate table-level DDL output against the test stack. | RQ-025, RQ-050 | Passed |
| AC-006 | `SELECT COUNT(*) FROM test_db.customer_transactions` returns 1000 rows. | RQ-048, RQ-049 | Passed |
| AC-007 | The export script connects to the test stack HMS and generates a valid `CREATE ICEBERG TABLE` DDL for `customer_transactions`. | RQ-051, RQ-052, RQ-062 | Passed |
| AC-008 | The export script generates a `manifest.json` listing the table, source HDFS path, target Iceberg path, and partition flag. | RQ-058, RQ-059 | Passed |
| AC-009 | The generated DDL includes correct Snowflake type mappings and preserves table/column comments from Hive. | RQ-061, RQ-065 | Passed |
| AC-010 | Parquet files are exported from HDFS to `workspace/export/` with partition structure preserved. | RQ-066, RQ-067 | Passed |
| AC-011 | Generated Snowflake DDL uses `CATALOG='SNOWFLAKE'`, `EXTERNAL_VOLUME`, `BASE_LOCATION` and includes correct type mappings and comments. | RQ-068, RQ-069, RQ-070, RQ-071 | Passed |
| AC-012 | Generated `COPY INTO` uses `LOAD_MODE = ADD_FILES_REFERENCE` for zero-copy registration. | RQ-072 | Passed |
| AC-013 | The migration demo script produces a complete set of ready-to-run Snowflake SQL in `workspace/output/`. | RQ-075 | Passed |

---

## 11. Documentation and Positioning

| Id | Short Description | Status |
| --- | --- | --- |
| RQ-088 | README positions the repo as a migration showcase (not a test stack) with a clear one-sentence value proposition in the title and opening paragraph. | Implemented |
| RQ-089 | README includes a "Why Migrate" section explaining operational and architectural benefits of moving from Hadoop/Hive to Snowflake. | Implemented |
| RQ-090 | README includes a numbered migration flow (5 steps) with a visual diagram showing the end-to-end conversion path from HMS metadata to Snowflake artifacts. | Implemented |
| RQ-091 | README includes a formal naming convention reference table documenting all CLI parameters and their mapping to Snowflake object names. | Implemented |
| RQ-092 | README project structure section matches the actual repository layout (no phantom files, no incorrect root prefix). | Implemented |
| RQ-093 | Terminology is consistent: one canonical term ("Hive/HMS to Snowflake Managed Iceberg Migration") is defined and used throughout README and script docstrings. | Implemented |
| RQ-094 | GitHub repository has a description and at least 5 relevant topics set for discoverability. | Implemented |
| RQ-095 | README separates migration showcase content (value, flow, artifacts, naming) from operational how-to (quickstart, environment, troubleshooting). | Implemented |

---

## Change Log

| Version | Date | Change |
| --- | --- | --- |
| 0.1 | 2026-05-25 | Initial draft (40 requirements). |
| 0.2 | 2026-05-25 | Removed PostgreSQL dependency (use embedded Derby). Removed original RQ-007 and old MC-003. Added RQ-041 through RQ-050. Reorganized by category. Added AC-006. Added implementation phases. |
| 0.3 | 2026-05-25 | Switched HDFS images to `sbloodys/hadoop:3.3.6` (ARM64 native). Added Hue PostgreSQL backend (MC-006). Changed HDFS RPC host port to 9900. Added `hive-site.xml` for HiveServer2 web UI config. Added table/column comments to sample data. |
| 0.4 | 2026-05-25 | Added Section 8: Hive-to-Snowflake Iceberg Export requirements (RQ-051 through RQ-065). Added Phase 6. Added AC-007 through AC-009. |
| 0.5 | 2026-05-26 | Replaced MinIO migration demo (Section 9) with Snowflake-managed Iceberg migration (CATALOG='SNOWFLAKE'). Removed MC-007 (MinIO). Phase 5 now exports Parquet from HDFS to S3 and generates Snowflake-managed Iceberg DDL + COPY INTO with ADD_FILES_REFERENCE. |
| 0.6 | 2026-05-26 | Added Section 10: Naming Standards, Tags, DCM (RQ-076 through RQ-081). Applied naming: HAM_DEV.HAM_RAW_V001.HAMI_RAW_TB_*. Created HAM_ICEBERG_VOL for s3://mdaeppen/hadoop-root/. Dropped HADOOP_MIGRATION. Cleaned s3://mdaeppen/glue/hadoop-root/. Note: ADD_FILES_REFERENCE not supported for Snowflake-managed Iceberg — using standard COPY INTO. |
| 0.7 | 2026-05-26 | Added RQ-082 through RQ-087 (TBLPROPERTIES tags, pii_map, tag DDL generation). All implemented. Export script now generates `tags.sql` per table with CREATE TAG + table-level SET TAG + column-level PII SET TAG. DCM manifest (dcm_manifest.yml) and DEFINE statements generated automatically. TBLPROPERTIES set inline in CREATE TABLE (init-data.sh). |
| 0.8 | 2026-05-28 | Added Section 11: Documentation and Positioning (RQ-088 through RQ-095). README rewritten as migration showcase. Added "Why Migrate" section, migration flow diagram, naming convention reference, terminology glossary. Fixed project structure. Set GitHub description and topics. Added DataOpsBackbone CI/CD workflow. |

---

## Implementation Phases

### Phase 1: Infrastructure (Foundation)

**Goal**: All containers start and pass health checks.

| Step | Description |
| --- | --- |
| 1.1 | Create `docker-compose.yml` with 5 containers (NameNode, DataNode, Metastore, HiveServer2, Hue). |
| 1.2 | Create `.env` file with pinned image versions and port mappings. |
| 1.3 | Configure Docker network `hadoop-test-net`. |
| 1.4 | Configure Docker volumes (hdfs-namenode, hdfs-datanode, hive-warehouse, metastore-derby). |
| 1.5 | Add health checks for all services. |
| 1.6 | Add `depends_on` with `condition: service_healthy` for startup ordering. |

**Gate**: `docker compose up -d && docker compose ps` — all containers report "healthy".

---

### Phase 2: Data Bootstrap (1 Table, 1000 Rows)

**Goal**: Fake data is loaded and queryable in Hive.

| Step | Description |
| --- | --- |
| 2.1 | Create `scripts/generate-fake-data.py` — generates 1000 rows of CUSTOMER_TRANSACTIONS as Parquet files. |
| 2.2 | Create `scripts/init-data.sh` — uploads Parquet to HDFS, creates Hive database and external table DDL. |
| 2.3 | Execute via `docker exec` into HiveServer2 after stack is healthy. |
| 2.4 | Verify: `SELECT COUNT(*) FROM test_db.customer_transactions` returns 1000. |

**Fake Data Specification**:

```
Database: test_db
Table: customer_transactions
Columns:
  - transaction_id  STRING   (UUID)
  - customer_id     INT      (1-500)
  - amount          DOUBLE   (1.00 - 10000.00)
  - currency        STRING   (USD, EUR, GBP, CHF, JPY)
  - transaction_date STRING  (2024-01-01 to 2024-12-31)
  - category        STRING   (TRANSFER, PAYMENT, WITHDRAWAL, DEPOSIT, FEE)
Format: Parquet
Location: hdfs://namenode:9000/user/hive/warehouse/test_db.db/customer_transactions
Partitioned by: status (COMPLETED, PENDING, FAILED)
Total rows: 1000
```

**Gate**: Beeline query returns 1000 rows.

---

### Phase 3: Migration Testing

**Goal**: Migration script can extract metadata and generate DDL.

| Step | Description |
| --- | --- |
| 3.1 | Mount `./workspace` into HiveServer2 container. |
| 3.2 | Create `scripts/extract-metadata.sh` — runs SHOW CREATE TABLE, DESCRIBE FORMATTED. |
| 3.3 | Create `scripts/run-migration-test.sh` — placeholder for migration script execution. |
| 3.4 | Verify HDFS data export to mounted path works. |

**Gate**: DDL extraction produces valid output file in `./workspace/output/`.

---

### Phase 4: Documentation and Validation

**Goal**: Fully documented and all acceptance criteria pass.

| Step | Description |
| --- | --- |
| 4.1 | Create `README.md` with architecture diagram, quickstart, exposed ports, credentials, troubleshooting. |
| 4.2 | Create `scripts/validate.sh` — automated full acceptance checklist (AC-001 through AC-006). |
| 4.3 | Run full validation and confirm all acceptance criteria pass. |

**Gate**: All acceptance criteria (AC-001 through AC-009) pass.

---

### Phase 5: Hive-to-Snowflake Managed Iceberg Migration

**Goal**: Export Hive data from HDFS, generate Snowflake-managed Iceberg DDL, and produce ready-to-run SQL for loading into Snowflake.

| Step | Description |
| --- | --- |
| 5.1 | Create `scripts/export-from-hdfs.sh` — copies Parquet files from HDFS to `workspace/export/` preserving partition structure. |
| 5.2 | Create `scripts/migrate-to-snowflake-iceberg.sh` — orchestrates full migration flow. |
| 5.3 | Read HMS metadata (columns, types, comments, partitions, HDFS location) for each table. |
| 5.4 | Map Hive types to Snowflake types. |
| 5.5 | Generate `CREATE ICEBERG TABLE` DDL with `CATALOG='SNOWFLAKE'`, `EXTERNAL_VOLUME`, `BASE_LOCATION`. |
| 5.6 | Generate `COPY INTO ... LOAD_MODE = ADD_FILES_REFERENCE` for zero-copy registration. |
| 5.7 | Generate alternative `COPY INTO ... LOAD_MODE = FULL_INGEST` for transformation scenarios. |
| 5.8 | Write all SQL to `workspace/output/` for review and execution against Snowflake. |
| 5.9 | Test against local stack: verify export and DDL generation for `test_db.customer_transactions`. |

**Gate**: AC-010, AC-011, AC-012, AC-013 pass.

**Migration flow**:

```
┌─────────────────────┐       ┌──────────────┐       ┌─────────────────────────────┐
│  Hive Table (HDFS)  │       │  S3 Bucket   │       │  Snowflake Managed Iceberg  │
│  customer_          │ ───>  │  (Parquet    │ ───>  │  customer_transactions      │
│  transactions       │ copy  │   files)     │ COPY  │                             │
│                     │       │              │ INTO  │  CATALOG = 'SNOWFLAKE'      │
│  Format: Parquet    │       │              │       │  EXTERNAL_VOLUME = '...'    │
│  Storage: HDFS      │       │              │       │  BASE_LOCATION = '...'      │
│  Catalog: Hive HMS  │       │              │       │                             │
└─────────────────────┘       └──────────────┘       └─────────────────────────────┘
```

**Generated Snowflake DDL example**:

```sql
CREATE OR REPLACE ICEBERG TABLE TEST_DB.CUSTOMER_TRANSACTIONS (
    TRANSACTION_ID VARCHAR COMMENT 'Unique transaction identifier (UUID v4)',
    CUSTOMER_ID INT COMMENT 'Customer reference ID (1-500)',
    AMOUNT DOUBLE COMMENT 'Transaction amount in the specified currency',
    CURRENCY VARCHAR COMMENT 'ISO 4217 currency code (USD, EUR, GBP, CHF, JPY)',
    TRANSACTION_DATE VARCHAR COMMENT 'Transaction date in ISO 8601 format (YYYY-MM-DD)',
    CATEGORY VARCHAR COMMENT 'Transaction type: TRANSFER, PAYMENT, WITHDRAWAL, DEPOSIT, or FEE',
    STATUS VARCHAR COMMENT 'Processing status: COMPLETED, PENDING, or FAILED'
)
COMMENT = 'Sample customer transaction data for migration testing.'
CATALOG = 'SNOWFLAKE'
EXTERNAL_VOLUME = 'ICEBERG_EXT_VOL'
BASE_LOCATION = 'iceberg/test_db/customer_transactions';
```

**Generated COPY INTO example (zero-copy)**:

```sql
COPY INTO TEST_DB.CUSTOMER_TRANSACTIONS
FROM @RAW_ICEBERG_STAGE/iceberg/test_db/customer_transactions/
FILE_FORMAT = (TYPE = PARQUET)
LOAD_MODE = ADD_FILES_REFERENCE
MATCH_BY_COLUMN_NAME = CASE_INSENSITIVE;
```

**Snowflake prerequisites** (documented, not created by this stack):

```sql
-- External volume pointing to S3
CREATE EXTERNAL VOLUME ICEBERG_EXT_VOL
  STORAGE_LOCATIONS = (
    (NAME = 'S3_LAKE' STORAGE_BASE_URL = 's3://my-bucket/lake/'
     STORAGE_PROVIDER = 'S3' STORAGE_AWS_ROLE_ARN = 'arn:aws:iam::...:role/...')
  );

-- Stage for file registration
CREATE STAGE RAW_ICEBERG_STAGE
  URL = 's3://my-bucket/lake/'
  STORAGE_INTEGRATION = MY_S3_INTEGRATION;
```

---

### Phase 6: Hive-to-Snowflake Iceberg Export Script

**Goal**: Export script dynamically discovers and processes ALL tables in a Hive database, extracts full metadata, and generates Snowflake-managed Iceberg DDL + data copy commands.

| Step | Description |
| --- | --- |
| 6.1 | Create `scripts/hive_hms_to_horizon_zero_copy.py` with HMS Thrift client connection. |
| 6.2 | Implement dynamic table discovery: list ALL tables in the specified `--database`. |
| 6.3 | For each table, extract full metadata: columns, types, comments, partition keys, storage format, HDFS location, SerDe, table properties. |
| 6.4 | Filter: process only Parquet-backed tables; skip others with reason logged. |
| 6.5 | Implement Hive-to-Snowflake type mapping (STRING->VARCHAR, INT->INT, DOUBLE->DOUBLE, DECIMAL->NUMBER, BIGINT->BIGINT, BOOLEAN->BOOLEAN, TIMESTAMP->TIMESTAMP_NTZ, DATE->DATE, BINARY->BINARY, ARRAY->ARRAY, MAP->OBJECT, STRUCT->OBJECT). |
| 6.6 | Generate per-table `CREATE ICEBERG TABLE` DDL with `CATALOG='SNOWFLAKE'`, `EXTERNAL_VOLUME`, `BASE_LOCATION`, column comments, table comment. |
| 6.7 | Generate per-table `hadoop distcp` commands from source HDFS path to target S3 path. |
| 6.8 | Generate per-table `COPY INTO ... LOAD_MODE = ADD_FILES_REFERENCE` statements. |
| 6.9 | Export table properties as JSON sidecar files (`<table>_properties.json`). |
| 6.10 | Write `manifest.json` with full inventory: all tables found, status (exported/skipped), metadata, paths, partition flags. |
| 6.11 | Print summary report: total tables, exported count, skipped count with reasons. |
| 6.12 | Support optional `--tables` filter for subset processing. |
| 6.13 | Add `--execute-distcp` and `--execute-sql` flags for optional live execution. |
| 6.14 | Test against local stack: connect to `metastore:9083`, process all tables in `test_db`. |

**Gate**: AC-007, AC-008, AC-009 pass.

**Script CLI interface**:

```
python3 scripts/hive_hms_to_horizon_zero_copy.py \
  --hms-host metastore \
  --hms-port 9083 \
  --database test_db \
  --external-volume ICEBERG_EXT_VOL \
  --base-root iceberg \
  --object-store-prefix s3a://my-bucket/lake \
  --stage-name RAW_ICEBERG_STAGE \
  --snowflake-schema TEST_DB
```

**Output files** (emit-only mode, per database):

```
workspace/output/
├── manifest.json                              (full inventory of all tables)
├── summary.txt                                (human-readable report)
├── customer_transactions/
│   ├── create_iceberg_table.sql               (CREATE ICEBERG TABLE DDL)
│   ├── distcp.sh                              (hadoop distcp command)
│   ├── copy_into_add_files_reference.sql      (zero-copy COPY INTO)
│   ├── copy_into_full_ingest.sql              (alternative full ingest)
│   └── properties.json                        (Hive TBLPROPERTIES sidecar)
├── another_table/
│   ├── create_iceberg_table.sql
│   ├── distcp.sh
│   ├── copy_into_add_files_reference.sql
│   ├── copy_into_full_ingest.sql
│   └── properties.json
└── ...                                        (one directory per table)
```

**Dependencies**:

```
hmsclient
thrift-sasl
sasl
```

**Design notes**:

- Emit-only is the default (safe). Execution requires explicit `--execute-distcp` and/or `--execute-sql` flags.
- Partitioned tables are flagged in manifest as `"partitioned": true` for manual review before execution.
- Non-Parquet tables are skipped with `"skipped": true, "reason": "not_parquet"` in the manifest.
- `ADD_FILES_REFERENCE` is used for zero-copy (files remain immutable in place). Use `FULL_INGEST` if files need transformation.
- Table/column comments from Hive are preserved as `COMMENT` clauses in the Snowflake DDL.
