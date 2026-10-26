#!/usr/bin/env python3
"""Execute every gold SQL on db_agent_view and dw, record reference results, and compare them."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Callable, Mapping

SEMANTIC_CATALOG = Path.home() / "semantic-catalog"
sys.path.insert(0, str(SEMANTIC_CATALOG))

from scripts.beaver_c0.common import ContractError, compare_result_details  # noqa: E402
from scripts.beaver_c0.evaluate_c0 import has_outer_order_by, parse_mysql_xml_result  # noqa: E402

HERE = Path(__file__).resolve().parent
DATABASE = "db_agent_view"
SOURCE_DATABASE = "dw"
QUERY_TIMEOUT_SECONDS = 300

Executor = Callable[[str], Mapping[str, Any]]


def execute_sql(
    sql: str,
    *,
    database: str,
    container: str,
    user: str,
    password: str,
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> dict[str, Any]:
    prefix = [
        "docker", "exec", "--env", f"MYSQL_PWD={password}", container,
        "mysql", "--protocol=tcp", "--host=127.0.0.1", f"--user={user}",
        f"--database={database}", "--default-character-set=utf8mb4", "--raw", "--execute", sql,
    ]

    def run(flag: str) -> str:
        try:
            return runner(
                [*prefix, flag], check=True, capture_output=True, text=True,
                timeout=QUERY_TIMEOUT_SECONDS,
            ).stdout
        except subprocess.CalledProcessError as error:
            raise RuntimeError((error.stderr or error.stdout or "MySQL query failed").strip()) from error

    result = parse_mysql_xml_result(run("--xml"), fallback_columns=[])
    if not result["rows"]:
        headers = run("--batch").splitlines()
        result["columns"] = headers[0].split("\t") if headers else []
    return result


FLOAT_RELATIVE_TOLERANCE = 1e-9


def _cells_close(a: Any, b: Any) -> bool:
    if a == b:
        return True
    try:
        x, y = float(a), float(b)
    except (TypeError, ValueError):
        return False
    return abs(x - y) <= FLOAT_RELATIVE_TOLERANCE * max(abs(x), abs(y), 1.0)


def _rows_close(rows_a: list[list[Any]], rows_b: list[list[Any]]) -> bool:
    return len(rows_a) == len(rows_b) and all(
        len(ra) == len(rb) and all(_cells_close(a, b) for a, b in zip(ra, rb))
        for ra, rb in zip(rows_a, rows_b)
    )


def _sort_key(row: list[Any]) -> tuple[str, ...]:
    def cell(value: Any) -> str:
        try:
            return f"{float(value):.9g}"
        except (TypeError, ValueError):
            return "" if value is None else str(value)

    return tuple(cell(value) for value in row)


def classify_difference(a: Mapping[str, Any], b: Mapping[str, Any], *, ordered: bool) -> str:
    """How a result differs from a reference: exact, float_tolerance, order_only, or different."""
    if compare_result_details(a, b, ordered=ordered).matches:
        return "exact"
    if len(a["columns"]) != len(b["columns"]):
        return "different"
    if _rows_close(a["rows"], b["rows"]):
        return "float_tolerance"
    if _rows_close(sorted(a["rows"], key=_sort_key), sorted(b["rows"], key=_sort_key)):
        return "order_only"
    return "different"


def _result_sha256(result: Mapping[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(result, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()


def check_task(task: Mapping[str, Any], *, execute: Mapping[str, Executor]) -> dict[str, Any]:
    sql = task["sql"]
    record: dict[str, Any] = {
        "task_id": task["task_id"],
        "ordered": has_outer_order_by(sql),
        "status": "ok",
        "error": None,
        "matches_dw": False,
        "dw_comparison": None,
        "row_count": None,
        "result_sha256": None,
        "result": None,
    }
    results = {}
    for database in (DATABASE, SOURCE_DATABASE):
        try:
            results[database] = execute[database](sql)
        except Exception as error:  # noqa: BLE001 - recorded per task
            record["status"] = "error"
            record["error"] = f"{database}: {str(error)[:500]}"
            return record

    result = results[DATABASE]
    record["result"] = result
    record["row_count"] = len(result["rows"])
    record["result_sha256"] = _result_sha256(result)
    try:
        record["dw_comparison"] = classify_difference(
            result, results[SOURCE_DATABASE], ordered=record["ordered"]
        )
        record["matches_dw"] = record["dw_comparison"] == "exact"
    except ContractError as error:
        record["status"] = "invalid_result"
        record["error"] = str(error)[:500]
    return record


def table_fingerprints(
    tables: list[str], *, container: str, user: str, password: str
) -> list[dict[str, Any]]:
    rows = []
    for table in tables:
        entry: dict[str, Any] = {"table": table}
        for database in (DATABASE, SOURCE_DATABASE):
            count = execute_sql(
                f"SELECT COUNT(*) AS n FROM `{table}`",
                database=database, container=container, user=user, password=password,
            )["rows"][0][0]
            checksum = execute_sql(
                f"CHECKSUM TABLE `{table}`",
                database=database, container=container, user=user, password=password,
            )["rows"][0][1]
            entry[database] = {"rows": int(count), "checksum": checksum}
        entry["identical"] = entry[DATABASE] == entry[SOURCE_DATABASE]
        rows.append(entry)
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=HERE / "data")
    parser.add_argument("--container", default=os.environ.get("BEAVER_C0_MYSQL_CONTAINER", "beaver-c0-mysql"))
    parser.add_argument("--user", default=os.environ.get("BEAVER_C0_EVALUATOR_USER", "beaver_evaluator"))
    parser.add_argument("--password", default=os.environ.get("BEAVER_C0_EVALUATOR_PASSWORD"))
    parser.add_argument("--parallelism", type=int, default=6)
    args = parser.parse_args()
    if not args.password:
        parser.error("--password or BEAVER_C0_EVALUATOR_PASSWORD is required")

    provenance = json.loads((args.data_dir / "provenance.json").read_text(encoding="utf-8"))
    tasks = [
        {"task_id": row["id"], "sql": row["sql"]}
        for row in map(json.loads, (args.data_dir / "tasks_gold.jsonl").read_text(encoding="utf-8").splitlines())
    ]
    connection = {"container": args.container, "user": args.user, "password": args.password}
    executors = {
        database: (lambda sql, database=database: execute_sql(sql, database=database, **connection))
        for database in (DATABASE, SOURCE_DATABASE)
    }
    with ThreadPoolExecutor(max_workers=args.parallelism) as pool:
        records = list(pool.map(lambda task: check_task(task, execute=executors), tasks))

    with (args.data_dir / "gold_results.jsonl").open("w", encoding="utf-8") as output:
        for record in records:
            output.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")

    tables = [entry["table"] for entry in provenance["tables"]]
    fingerprints = table_fingerprints(tables, **connection)
    row_counts = [record["row_count"] for record in records if record["row_count"] is not None]
    summary = {
        "task_count": len(records),
        "status_counts": dict(Counter(record["status"] for record in records)),
        "dw_comparison_counts": dict(Counter(record["dw_comparison"] for record in records)),
        "non_exact_task_ids": {
            kind: [r["task_id"] for r in records if r["dw_comparison"] == kind]
            for kind in ("float_tolerance", "order_only", "different")
        },
        "error_task_ids": [r["task_id"] for r in records if r["status"] != "ok"],
        "empty_result_task_ids": [r["task_id"] for r in records if r["row_count"] == 0],
        "ordered_task_count": sum(record["ordered"] for record in records),
        "row_count_distribution": {
            "min": min(row_counts, default=None),
            "median": sorted(row_counts)[len(row_counts) // 2] if row_counts else None,
            "max": max(row_counts, default=None),
        },
        "tables": fingerprints,
        "all_tables_identical": all(entry["identical"] for entry in fingerprints),
    }
    (args.data_dir / "gold_check.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({k: v for k, v in summary.items() if k != "tables"}, indent=2))


if __name__ == "__main__":
    main()
