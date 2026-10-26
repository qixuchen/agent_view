#!/usr/bin/env python3
"""Freeze the db_agent_view task set: the top-k dw tables and the tasks using only them."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import AbstractSet as Set
from typing import Any, Mapping, Sequence

import pyarrow.parquet as pq

BEAVER_QUERY_DIR = Path.home() / "semantic-catalog" / "data" / "beaver" / "query" / "data"
DEFAULT_SOURCE = BEAVER_QUERY_DIR / "dw_filtered.parquet"
DEFAULT_AUDIT = BEAVER_QUERY_DIR / "dw_filtered_audit.jsonl"
DEFAULT_OUTPUT_DIR = Path(__file__).resolve().parent / "data"
DATABASE = "db_agent_view"
ARTIFACT_PREFIX = "av_"
_CURDATE = "gold SQL filters on YEAR(CURDATE()); the answer depends on the run date (empty in 2026-10)"
_LIMIT_TIE = (
    "outer ORDER BY ... LIMIT 10 cuts through tied sort keys; the returned row set is not unique"
)
EXCLUDED_TASKS = {
    "dw_72": _CURDATE,
    "dw_579": _CURDATE,
    "dw_5147": _CURDATE,
    "dw_390": _LIMIT_TIE,
    "dw_520": _LIMIT_TIE,
    "dw_2859": _LIMIT_TIE,
    "dw_4611": _LIMIT_TIE,
    "dw_4810": _LIMIT_TIE,
    "dw_5152": _LIMIT_TIE,
}


def select_tables(table_sets: Mapping[str, set[str]], *, k: int) -> list[str]:
    counts = Counter(table for tables in table_sets.values() for table in tables)
    return [table for table, _ in sorted(counts.items(), key=lambda item: (-item[1], item[0]))[:k]]


def select_tasks(
    table_sets: Mapping[str, set[str]], tables: Sequence[str], *, excluded: Set[str] = frozenset()
) -> list[str]:
    allowed = set(tables)
    return [
        task_id for task_id, used in table_sets.items() if used <= allowed and task_id not in excluded
    ]


def prune_jsonl(path: Path, keep_ids: Set[str]) -> int:
    """Drop records whose task_id is not kept; return how many were dropped."""
    lines = path.read_text(encoding="utf-8").splitlines()
    kept = [line for line in lines if json.loads(line)["task_id"] in keep_ids]
    path.write_text("".join(line + "\n" for line in kept), encoding="utf-8")
    return len(lines) - len(kept)


def manifest_entry(row: Mapping[str, Any], *, database: str, seed: int) -> dict[str, Any]:
    return {"task_id": row["id"], "question": row["question"], "database": database, "seed": seed}


def _sha256(path: Path) -> str:
    return hashlib.file_digest(path.open("rb"), "sha256").hexdigest()


def _write_jsonl(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as output:
        for row in rows:
            output.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def build(*, source: Path, audit: Path, output_dir: Path, k: int) -> dict[str, Any]:
    rows = pq.read_table(source).to_pylist()
    audit_tables = {}
    for line in audit.read_text(encoding="utf-8").splitlines():
        record = json.loads(line)
        audit_tables[record["id"]] = set(record["sql_tables"])
    table_sets = {row["id"]: audit_tables[row["id"]] for row in rows}

    tables = select_tables(table_sets, k=k)
    candidate_ids = select_tasks(table_sets, tables)
    task_ids = select_tasks(table_sets, tables, excluded=set(EXCLUDED_TASKS))
    selected = set(task_ids)
    task_rows = [{**row, "db": DATABASE} for row in rows if row["id"] in selected]

    output_dir.mkdir(parents=True, exist_ok=True)
    tasks_path = output_dir / "tasks_gold.jsonl"
    manifest_path = output_dir / "manifest.jsonl"
    _write_jsonl(tasks_path, task_rows)
    _write_jsonl(manifest_path, [manifest_entry(row, database=DATABASE, seed=0) for row in task_rows])
    gold_results_path = output_dir / "gold_results.jsonl"
    if gold_results_path.exists():
        prune_jsonl(gold_results_path, selected)

    all_counts = Counter(table for used in table_sets.values() for table in used)
    subset_counts = Counter(table for task_id in task_ids for table in table_sets[task_id])
    provenance = {
        "database": DATABASE,
        "source_database": "dw",
        "artifact_prefix": ARTIFACT_PREFIX,
        "selection_rule": (
            f"Top {k} dw tables by number of dw_filtered tasks whose gold SQL uses them "
            "(ties broken by table name); keep tasks whose gold-SQL table set is a subset of them."
        ),
        "table_source": "sql_tables in dw_filtered_audit.jsonl (parsed from gold SQL)",
        "source_parquet": str(source),
        "source_parquet_sha256": _sha256(source),
        "audit_jsonl": str(audit),
        "audit_jsonl_sha256": _sha256(audit),
        "source_task_count": len(rows),
        "candidate_task_count": len(candidate_ids),
        "excluded_tasks": {
            task_id: reason for task_id, reason in EXCLUDED_TASKS.items() if task_id in set(candidate_ids)
        },
        "task_count": len(task_ids),
        "tables": [
            {"table": table, "tasks_in_source": all_counts[table], "tasks_in_set": subset_counts[table]}
            for table in tables
        ],
        "files": {
            "tasks_gold.jsonl": {
                "visibility": "evaluator-only (contains gold SQL and annotations)",
                "sha256": _sha256(tasks_path),
            },
            "manifest.jsonl": {
                "visibility": "agent-safe (task_id, question, database, seed)",
                "sha256": _sha256(manifest_path),
            },
        },
        "task_ids": task_ids,
    }
    (output_dir / "provenance.json").write_text(
        json.dumps(provenance, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return provenance


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--audit", type=Path, default=DEFAULT_AUDIT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--k", type=int, default=10)
    args = parser.parse_args()
    provenance = build(source=args.source, audit=args.audit, output_dir=args.output_dir, k=args.k)
    print(json.dumps({key: provenance[key] for key in ("task_count", "tables")}, indent=2))


if __name__ == "__main__":
    main()
