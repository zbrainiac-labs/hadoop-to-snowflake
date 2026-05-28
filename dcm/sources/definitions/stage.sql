DEFINE STAGE {{domain}}_{{env}}.{{domain}}_{{maturity}}_V{{version}}.{{domain}}{{component}}_{{maturity}}_ST_ICEBERG
  URL = '{{s3_prefix}}/'
  STORAGE_INTEGRATION = {{storage_integration}}
  FILE_FORMAT = (TYPE = PARQUET);
