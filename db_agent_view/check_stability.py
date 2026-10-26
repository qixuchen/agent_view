#!/usr/bin/env python3
"""Re-execute every gold SQL several times and report tasks whose result differs from the recorded one."""

from __future__ import annotations

import argparse
import json
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Mapping, Sequence

from run_gold import DATABASE, HERE, classify_difference, execute_sql


def unstable_tasks(
    reference: Mapping[str, Mapping[str, Any]], reruns: Sequence[Mapping[str, Mapping[str, Any]]]
) -> dict[str, list[str]]:
    unstable: dict[str, list[str]] = {}
    for task_id, record in reference.items():
        kinds = [
            classify_difference(run[task_id], record["result"], ordered=record["ordered"])
            for run in reruns
        ]
        differing = [kind for kind in kinds if kind != "exact"]
        if differing:
            unstable[task_id] = sorted(set(differing))
    return unstable


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=HERE / "data")
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--parallelism", type=int, default=6)
    parser.add_argument("--container", default=os.environ.get("BEAVER_C0_MYSQL_CONTAINER", "beaver-c0-mysql"))
    parser.add_argument("--user", default=os.environ.get("BEAVER_C0_EVALUATOR_USER", "beaver_evaluator"))
    parser.add_argument("--password", default=os.environ.get("BEAVER_C0_EVALUATOR_PASSWORD"))
    args = parser.parse_args()
    if not args.password:
        parser.error("--password or BEAVER_C0_EVALUATOR_PASSWORD is required")

    sql_by_task = {
        row["id"]: row["sql"]
        for row in map(json.loads, (args.data_dir / "tasks_gold.jsonl").read_text(encoding="utf-8").splitlines())
    }
    reference = {}
    with (args.data_dir / "gold_results.jsonl").open(encoding="utf-8") as gold_file:
        for line in gold_file:
            record = json.loads(line)
            if record["task_id"] in sql_by_task:
                reference[record["task_id"]] = {"ordered": record["ordered"], "result": record["result"]}

    def execute(task_id: str) -> tuple[str, dict[str, Any]]:
        return task_id, execute_sql(
            sql_by_task[task_id], database=DATABASE,
            container=args.container, user=args.user, password=args.password,
        )

    reruns = []
    for _ in range(args.runs):
        with ThreadPoolExecutor(max_workers=args.parallelism) as pool:
            reruns.append(dict(pool.map(execute, reference)))

    unstable = unstable_tasks(reference, reruns)
    report = {"database": DATABASE, "runs": args.runs, "parallelism": args.parallelism,
              "task_count": len(reference), "unstable": unstable}
    (args.data_dir / "stability.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
