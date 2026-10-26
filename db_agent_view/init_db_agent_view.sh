#!/usr/bin/env bash
# Build db_agent_view: copies of the selected dw tables, plus an agent account that can read only this database.
# Artifacts created later live in the same database and must use the prefix recorded in provenance.json (av_).
set -euo pipefail

require_env() {
  local name="$1"
  if [[ -z "${!name:-}" ]]; then
    echo "Missing required environment variable: ${name}" >&2
    exit 2
  fi
}

require_env BEAVER_C0_MYSQL_ROOT_PASSWORD
require_env AGENT_VIEW_AGENT_PASSWORD

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROVENANCE="${SCRIPT_DIR}/data/provenance.json"
MYSQL_CONTAINER="${BEAVER_C0_MYSQL_CONTAINER:-beaver-c0-mysql}"
DATABASE="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["database"])' "${PROVENANCE}")"
SOURCE_DATABASE="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["source_database"])' "${PROVENANCE}")"
mapfile -t TABLES < <(python3 -c 'import json,sys; [print(t["table"]) for t in json.load(open(sys.argv[1]))["tables"]]' "${PROVENANCE}")

mysql_root() {
  docker exec --interactive \
    --env "MYSQL_PWD=${BEAVER_C0_MYSQL_ROOT_PASSWORD}" \
    "${MYSQL_CONTAINER}" mysql --protocol=socket --user=root "$@"
}

{
  echo "CREATE DATABASE IF NOT EXISTS \`${DATABASE}\`;"
  for table in "${TABLES[@]}"; do
    echo "DROP TABLE IF EXISTS \`${DATABASE}\`.\`${table}\`;"
    echo "CREATE TABLE \`${DATABASE}\`.\`${table}\` LIKE \`${SOURCE_DATABASE}\`.\`${table}\`;"
    echo "INSERT INTO \`${DATABASE}\`.\`${table}\` SELECT * FROM \`${SOURCE_DATABASE}\`.\`${table}\`;"
  done
  echo "CREATE USER IF NOT EXISTS 'agent_view_agent'@'%' IDENTIFIED BY '${AGENT_VIEW_AGENT_PASSWORD}';"
  echo "ALTER USER 'agent_view_agent'@'%' IDENTIFIED BY '${AGENT_VIEW_AGENT_PASSWORD}';"
  echo "GRANT SELECT, SHOW VIEW ON \`${DATABASE}\`.* TO 'agent_view_agent'@'%';"
  echo "GRANT SELECT, SHOW VIEW ON \`${DATABASE}\`.* TO 'beaver_evaluator'@'%';"
  echo "FLUSH PRIVILEGES;"
} | mysql_root

mysql_root --table -e "
  SELECT TABLE_NAME, TABLE_TYPE FROM INFORMATION_SCHEMA.TABLES
  WHERE TABLE_SCHEMA = '${DATABASE}' ORDER BY TABLE_NAME;
  SHOW GRANTS FOR 'agent_view_agent'@'%';"
