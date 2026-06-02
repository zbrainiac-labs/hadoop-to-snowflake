CREATE DATABASE IF NOT EXISTS {{domain}}_{{env}}
    COMMENT = 'HAM domain - Hadoop migration showcase';

CREATE SCHEMA IF NOT EXISTS {{domain}}_{{env}}.HAM_DCM
    COMMENT = 'DCM project schema for Hadoop migration';
CREATE SCHEMA IF NOT EXISTS {{domain}}_{{env}}.{{domain}}_{{maturity}}_V{{version}}
    COMMENT = 'RAW ingestion layer - migrated Hive/HMS tables';

CREATE DCM PROJECT IF NOT EXISTS {{domain}}_{{env}}.HAM_DCM.HAM_DCM_PROJECT;
