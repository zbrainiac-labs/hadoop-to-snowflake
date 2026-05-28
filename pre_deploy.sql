CREATE DATABASE IF NOT EXISTS {{ sf_db }}
    COMMENT = 'HAM domain - Hadoop migration showcase';

CREATE SCHEMA IF NOT EXISTS {{ sf_db }}.HAM_DCM
    COMMENT = 'DCM project schema for Hadoop migration';
CREATE SCHEMA IF NOT EXISTS {{ sf_db }}.HAM_RAW_V001
    COMMENT = 'RAW ingestion layer - migrated Hive/HMS tables';

CREATE DCM PROJECT IF NOT EXISTS {{ sf_db }}.HAM_DCM.HAM_DCM_PROJECT;
