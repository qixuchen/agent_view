#!/usr/bin/env python3
"""Freeze a join-path experiment: the db_agent_view tasks whose gold SQL uses exactly one join path.

A join path is the gold SQL's table set plus its equality join keys, both from the Beaver
annotations (dw_filtered guarantees they match the gold SQL). The experiment directory gets an
agent-safe manifest, the per-task domain-knowledge contexts to inject, and a provenance record.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any, Mapping, Sequence

from build_task_set import manifest_entry

HERE = Path(__file__).resolve().parent
DEFAULT_TASKS_GOLD = HERE / "data" / "tasks_gold.jsonl"
DEFAULT_EXPERIMENTS_DIR = HERE / "experiments"


def view_as_sql_note(view_sql: str, *, view_name: str, cte_name: str, instruction: str) -> str:
    """Render a view's query and its av_catalog descriptions as prompt text, without the view's name."""
    body = view_sql.split(f"VIEW {view_name} AS\n", 1)[1].split(";", 1)[0].rstrip()
    descriptions = re.findall(rf"\('{re.escape(view_name)}',\s*'([^']*)',\s*'([^']*)'\)", view_sql)
    notes = "".join(
        f"- {'Whole query' if column == '*' else column}: {description}\n" for column, description in descriptions
    )
    return (
        f"# Join knowledge\n{instruction}\n\n"
        f"```sql\nWITH {cte_name} AS (\n{body}\n)\n```\n\n"
        f"Notes on {cte_name}:\n{notes}"
    )


JOIN3_VIEW_SQL = (HERE / "views" / "join3_course_number.sql").read_text(encoding="utf-8")
EXPERIMENTS = {
    "join3_course_number": {
        "tables": ["LIBRARY_SUBJECT_OFFERED", "SIS_COURSE_DESCRIPTION", "SIS_SUBJECT_CODE"],
        "join_keys": [
            ["LIBRARY_SUBJECT_OFFERED.COURSE_NUMBER", "SIS_SUBJECT_CODE.COURSE_NUMBER"],
            ["SIS_COURSE_DESCRIPTION.COURSE", "SIS_SUBJECT_CODE.COURSE_NUMBER"],
        ],
        "excluded_tasks": {
            "dw_356": (
                "Asks for one row per department; gold groups by department and subject, returning "
                "2376 per-subject rows whose variance is always 0."
            ),
            "dw_1303": "Contains the same per-subject subquery as dw_356; gold returns 822 rows with variance 0.",
            "dw_2593": (
                "Gold takes the variance of each department's single variance value inside WITH ROLLUP, "
                "so all 15 department rows have variance 0."
            ),
        },
        "arm_notes": {
            "view": (
                "# Agent views\n"
                "This database also has pre-joined views whose names start with `av_`. The table "
                "`av_catalog` documents each view: its source tables, join conditions, and where every "
                "column comes from. Read `av_catalog` before choosing tables.\n"
                "For any question about offered subjects (enrollments, offering departments, terms), "
                "prefer the view `av_library_offering_course` over joining base tables yourself.\n"
            ),
            "join_text": (
                "# Join knowledge\n"
                "For any question about offered subjects (enrollments, offering departments, terms), use the "
                "table LIBRARY_SUBJECT_OFFERED for the offerings, and join it to SIS_SUBJECT_CODE and "
                "SIS_COURSE_DESCRIPTION instead of using other offering tables:\n"
                "- LIBRARY_SUBJECT_OFFERED.COURSE_NUMBER = SIS_SUBJECT_CODE.COURSE_NUMBER\n"
                "- SIS_COURSE_DESCRIPTION.COURSE = SIS_SUBJECT_CODE.COURSE_NUMBER\n"
                "(both inner joins).\n"
                "\n"
                "Grain of the joined rows: one row per offering and matching course-description row. "
                "SIS_COURSE_DESCRIPTION can hold several rows for one COURSE, so an offering can appear "
                "more than once.\n"
                "\n"
                "Column sources: offering columns (term, subject, offering department and school, enrolled "
                "students) come from LIBRARY_SUBJECT_OFFERED. SUBJECT_CODE, SUBJECT_CODE_DESC, "
                "DEPARTMENT_CODE and SCHOOL_CODE come from SIS_SUBJECT_CODE. Course-level columns "
                "(department, school, degree-granting flag, course level, CIP code) come from "
                "SIS_COURSE_DESCRIPTION. On joined rows, SIS_COURSE_DESCRIPTION.DEPARTMENT_NAME and "
                "SCHOOL_NAME equal SIS_SUBJECT_CODE.DEPARTMENT_NAME and SCHOOL_NAME.\n"
            ),
            "join_sql": view_as_sql_note(
                JOIN3_VIEW_SQL,
                view_name="av_library_offering_course",
                cte_name="library_offering_course",
                instruction=(
                    "For any question about offered subjects (enrollments, offering departments, terms), "
                    "build on the query below (for example as a WITH clause named library_offering_course) "
                    "instead of joining base tables yourself."
                ),
            ),
        },
    },
}

JoinPath = tuple[tuple[str, ...], tuple[tuple[str, str], ...]]


def _canonical_path(tables: Sequence[str], join_keys: Sequence[Sequence[str]]) -> JoinPath:
    return (
        tuple(sorted(tables)),
        tuple(sorted((min(pair), max(pair)) for pair in join_keys)),
    )


def join_path(row: Mapping[str, Any]) -> JoinPath:
    return _canonical_path(json.loads(row["tables"]), json.loads(row["join_keys"]))


def select_join_path_tasks(
    rows: Sequence[Mapping[str, Any]], *, tables: Sequence[str], join_keys: Sequence[Sequence[str]]
) -> list[str]:
    target = _canonical_path(tables, join_keys)
    return [row["id"] for row in rows if join_path(row) == target]


def domain_knowledge_context(row: Mapping[str, Any]) -> str | None:
    items = json.loads(row["domain_knowledge"])
    if not items:
        return None
    lines = [
        "# Task-specific domain knowledge",
        "In these predicates, `TABLE` stands for whichever table has that column.",
        "",
        *(f"- {item}" for item in items),
    ]
    return "\n".join(lines) + "\n"


def _sha256(path: Path) -> str:
    return hashlib.file_digest(path.open("rb"), "sha256").hexdigest()


def _write_jsonl(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as output:
        for row in rows:
            output.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def build(
    *,
    name: str,
    tasks_gold: Path,
    output_dir: Path,
    tables: Sequence[str],
    join_keys: Sequence[Sequence[str]],
    arm_notes: Mapping[str, str] | None = None,
    excluded_tasks: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    arm_notes = dict(arm_notes or {})
    excluded_tasks = dict(excluded_tasks or {})
    rows = [json.loads(line) for line in tasks_gold.read_text(encoding="utf-8").splitlines() if line]
    path_task_ids = select_join_path_tasks(rows, tables=tables, join_keys=join_keys)
    unknown = sorted(set(excluded_tasks) - set(path_task_ids))
    if unknown:
        raise ValueError(f"excluded tasks are not on the join path: {', '.join(unknown)}")
    task_ids = [task_id for task_id in path_task_ids if task_id not in excluded_tasks]
    selected = [row for row in rows if row["id"] in set(task_ids)]
    contexts = [
        {"task_id": row["id"], "context": context}
        for row in selected
        if (context := domain_knowledge_context(row)) is not None
    ]

    output_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = output_dir / "manifest.jsonl"
    contexts_path = output_dir / "domain_knowledge_contexts.jsonl"
    _write_jsonl(manifest_path, [manifest_entry(row, database=row["db"], seed=0) for row in selected])
    _write_jsonl(contexts_path, contexts)
    domain_knowledge = {context["task_id"]: context["context"] for context in contexts}
    arm_paths = {}
    for arm, note in arm_notes.items():
        arm_paths[arm] = output_dir / f"{arm}_contexts.jsonl"
        _write_jsonl(arm_paths[arm], [
            {
                "task_id": task_id,
                "context": note + ("\n" + domain_knowledge[task_id] if task_id in domain_knowledge else ""),
            }
            for task_id in task_ids
        ])

    canonical_tables, canonical_keys = _canonical_path(tables, join_keys)
    provenance = {
        "experiment": name,
        "join_path": {"tables": list(canonical_tables), "join_keys": [list(pair) for pair in canonical_keys]},
        "selection_rule": (
            "Tasks whose annotated table set and annotated equality join keys both equal the join "
            "path exactly (order- and orientation-insensitive)."
        ),
        "source_tasks_gold": str(tasks_gold),
        "source_tasks_gold_sha256": _sha256(tasks_gold),
        "join_path_task_ids": path_task_ids,
        "excluded_tasks": excluded_tasks,
        "task_count": len(task_ids),
        "task_ids": task_ids,
        "tasks_with_domain_knowledge": [context["task_id"] for context in contexts],
        "files": {
            "manifest.jsonl": {
                "visibility": "agent-safe (task_id, question, database, seed)",
                "sha256": _sha256(manifest_path),
            },
            "domain_knowledge_contexts.jsonl": {
                "visibility": "agent-visible when injected (domain_knowledge annotation only)",
                "sha256": _sha256(contexts_path),
            },
        },
    }
    provenance["arm_notes"] = arm_notes
    for arm, path in arm_paths.items():
        provenance["files"][path.name] = {
            "visibility": f"agent-visible in the {arm} arm (arm note, then the same domain knowledge)",
            "sha256": _sha256(path),
        }
    (output_dir / "provenance.json").write_text(
        json.dumps(provenance, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return provenance


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("experiment", choices=sorted(EXPERIMENTS))
    parser.add_argument("--tasks-gold", type=Path, default=DEFAULT_TASKS_GOLD)
    parser.add_argument("--experiments-dir", type=Path, default=DEFAULT_EXPERIMENTS_DIR)
    args = parser.parse_args()
    provenance = build(
        name=args.experiment,
        tasks_gold=args.tasks_gold,
        output_dir=args.experiments_dir / args.experiment,
        **EXPERIMENTS[args.experiment],
    )
    print(json.dumps(
        {key: provenance[key] for key in ("experiment", "task_count", "tasks_with_domain_knowledge")},
        indent=2,
    ))


if __name__ == "__main__":
    main()
