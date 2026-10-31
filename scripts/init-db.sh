#!/bin/sh
set -eu
# Values arrive through the container environment; psql variables quote literals safely.
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname postgres \
  -v core_password="$CORE_DB_PASSWORD" -v agent_password="$AGENT_DB_PASSWORD" \
  -v activity_password="$ACTIVITY_DB_PASSWORD" <<'SQL'
CREATE USER core PASSWORD :'core_password';
CREATE USER agent PASSWORD :'agent_password';
CREATE USER activity PASSWORD :'activity_password';
CREATE DATABASE core OWNER core;
CREATE DATABASE agent OWNER agent;
CREATE DATABASE activity OWNER activity;
REVOKE CONNECT ON DATABASE core FROM PUBLIC;
REVOKE CONNECT ON DATABASE agent FROM PUBLIC;
REVOKE CONNECT ON DATABASE activity FROM PUBLIC;
GRANT CONNECT ON DATABASE core TO core;
GRANT CONNECT ON DATABASE agent TO agent;
GRANT CONNECT ON DATABASE activity TO activity;
SQL
