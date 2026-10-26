import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import json

from build_task_set import EXCLUDED_TASKS, manifest_entry, prune_jsonl, select_tables, select_tasks


def test_select_tables_ranks_by_task_count_then_name():
    table_sets = {
        "t1": {"A", "B"},
        "t2": {"A", "C"},
        "t3": {"B", "D"},
        "t4": {"A"},
    }
    assert select_tables(table_sets, k=3) == ["A", "B", "C"]


def test_select_tasks_keeps_only_subsets_in_source_order():
    table_sets = {
        "dw_5": {"A", "B"},
        "dw_1": {"A", "C"},
        "dw_3": {"B"},
    }
    assert select_tasks(table_sets, ["A", "B"]) == ["dw_5", "dw_3"]


def test_select_tasks_drops_excluded_tasks():
    table_sets = {"dw_5": {"A"}, "dw_1": {"A"}}
    assert select_tasks(table_sets, ["A"], excluded={"dw_1"}) == ["dw_5"]


def test_excluded_tasks_record_a_reason_for_each_suspect_gold():
    assert set(EXCLUDED_TASKS) == {
        "dw_72", "dw_579", "dw_5147",
        "dw_390", "dw_520", "dw_2859", "dw_4611", "dw_4810", "dw_5152",
    }
    assert all(reason.strip() for reason in EXCLUDED_TASKS.values())


def test_prune_jsonl_keeps_only_listed_tasks(tmp_path):
    path = tmp_path / "gold_results.jsonl"
    path.write_text(
        "".join(json.dumps({"task_id": task_id}) + "\n" for task_id in ("dw_1", "dw_2", "dw_3")),
        encoding="utf-8",
    )
    assert prune_jsonl(path, {"dw_1", "dw_3"}) == 1
    assert [json.loads(line)["task_id"] for line in path.read_text().splitlines()] == ["dw_1", "dw_3"]


def test_manifest_entry_exposes_only_agent_safe_fields():
    row = {"id": "dw_1", "question": "Q?", "db": "dw", "sql": "SELECT 1", "tables": "[]"}
    assert manifest_entry(row, database="db_agent_view", seed=0) == {
        "task_id": "dw_1",
        "question": "Q?",
        "database": "db_agent_view",
        "seed": 0,
    }
