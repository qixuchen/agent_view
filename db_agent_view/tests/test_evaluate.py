import json
from pathlib import Path

from evaluate import evaluate_run, outer_order_keys, relaxed_compare


def table(columns, rows):
    return {"columns": columns, "rows": rows}


def test_outer_order_keys_resolves_aliases_positions_and_expressions():
    sql = "SELECT d.NAME AS dept, COUNT(*) AS n, AVG(x) FROM t d GROUP BY d.NAME ORDER BY n DESC, 1, AVG(x)"
    assert outer_order_keys(sql, ["dept", "n", "AVG(x)"]) == [1, 0, 2]


def test_outer_order_keys_resolves_unaliased_column_by_output_name():
    sql = "WITH c AS (SELECT a FROM t) SELECT c.a FROM c ORDER BY c.a"
    assert outer_order_keys(sql, ["a"]) == [0]


def test_outer_order_keys_is_none_when_key_is_not_in_output():
    assert outer_order_keys("SELECT a FROM t ORDER BY b", ["a"]) is None


def test_outer_order_keys_is_none_without_outer_order_by():
    assert outer_order_keys("SELECT a FROM (SELECT a FROM t ORDER BY a) s", ["a"]) is None


def test_relaxed_compare_tolerates_float_tail_noise():
    gold = table(["dept", "v"], [["Math", "3565.2422963432464"]])
    actual = table(["dept", "v"], [["Math", 3565.242296343227]])
    assert relaxed_compare(actual, gold, ordered=True, order_keys=[0]) == (True, "order_keys")


def test_relaxed_compare_tolerates_noise_across_a_rounding_boundary():
    gold = table(["v"], [["18.40886713445001"]])
    actual = table(["v"], [["18.40886713444999"]])
    assert relaxed_compare(actual, gold, ordered=False, order_keys=None) == (True, "unordered")


def test_relaxed_compare_matches_noise_within_the_same_row_when_gold_values_are_close():
    gold = table(["school", "cv"], [["Hum", "0.47024815257136215"], [None, "0.47024815257135977"]])
    actual = table(["school", "cv"], [["Hum", "0.4702481525713622"], [None, "0.47024815257136215"]])
    assert relaxed_compare(actual, gold, ordered=False, order_keys=None) == (True, "unordered")


def test_relaxed_compare_tolerates_noise_in_large_floats_written_in_exponent_form():
    gold = table(["v"], [["3.792431535378356e18"]])
    actual = table(["v"], [["3.792431535378394e+18"]])
    assert relaxed_compare(actual, gold, ordered=False, order_keys=None) == (True, "unordered")


def test_relaxed_compare_does_not_merge_nearby_integers():
    gold = table(["id"], [["1234567890123"]])
    actual = table(["id"], [["1234567890124"]])
    assert relaxed_compare(actual, gold, ordered=False, order_keys=None) == (False, "unordered")


def test_relaxed_compare_rejects_values_rounded_by_the_agent():
    gold = table(["v"], [["10.96036252727634"]])
    actual = table(["v"], [["10.9604"]])
    assert relaxed_compare(actual, gold, ordered=False, order_keys=None) == (False, "unordered")


def test_relaxed_compare_allows_reordering_rows_with_tied_sort_keys():
    gold = table(["n", "dept"], [["2", "A"], ["1", "B"], ["1", "C"]])
    actual = table(["n", "dept"], [["2", "A"], ["1", "C"], ["1", "B"]])
    assert relaxed_compare(actual, gold, ordered=True, order_keys=[0]) == (True, "order_keys")


def test_relaxed_compare_treats_keys_equal_under_mysql_ci_collation_as_ties():
    gold = table(["title", "n"], [["Adv for", "1"], ["Adv For", "2"], ["Adv fór", "3"], ["B", "4"]])
    actual = table(["title", "n"], [["Adv fór", "3"], ["Adv For", "2"], ["Adv for", "1"], ["B", "4"]])
    assert relaxed_compare(actual, gold, ordered=True, order_keys=[0]) == (True, "order_keys")


def test_relaxed_compare_keeps_exact_values_under_ci_collation():
    gold = table(["title"], [["Adv for"], ["B"]])
    actual = table(["title"], [["Adv For"], ["B"]])
    assert relaxed_compare(actual, gold, ordered=True, order_keys=[0]) == (False, "order_keys")


def test_relaxed_compare_rejects_wrong_sort_key_order():
    gold = table(["n", "dept"], [["2", "A"], ["1", "B"]])
    actual = table(["n", "dept"], [["1", "B"], ["2", "A"]])
    assert relaxed_compare(actual, gold, ordered=True, order_keys=[0]) == (False, "order_keys")


def test_relaxed_compare_maps_sort_key_through_renamed_and_reordered_columns():
    gold = table(["n", "dept"], [["2", "A"], ["1", "B"], ["1", "C"]])
    actual = table(["department", "total"], [["A", "2"], ["C", "1"], ["B", "1"]])
    assert relaxed_compare(actual, gold, ordered=True, order_keys=[0]) == (True, "order_keys")


def test_relaxed_compare_falls_back_to_strict_order_when_keys_are_unknown():
    gold = table(["dept"], [["A"], ["B"]])
    actual = table(["dept"], [["B"], ["A"]])
    assert relaxed_compare(actual, gold, ordered=True, order_keys=None) == (False, "strict_fallback")


def test_relaxed_compare_ignores_order_for_unordered_tasks():
    gold = table(["dept"], [["A"], ["B"]])
    actual = table(["dept"], [["B"], ["A"]])
    assert relaxed_compare(actual, gold, ordered=False, order_keys=None) == (True, "unordered")


def _write_jsonl(path: Path, rows) -> None:
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")


def test_evaluate_run_reports_strict_and_relaxed_accuracy(tmp_path: Path) -> None:
    data = tmp_path / "data"
    data.mkdir()
    _write_jsonl(
        data / "manifest.jsonl",
        [
            {"task_id": "dw_1", "question": "q", "database": "db_agent_view", "seed": 0},
            {"task_id": "dw_2", "question": "q", "database": "db_agent_view", "seed": 0},
            {"task_id": "dw_3", "question": "q", "database": "db_agent_view", "seed": 0},
        ],
    )
    _write_jsonl(
        data / "tasks_gold.jsonl",
        [
            {"id": "dw_1", "sql": "SELECT v FROM t"},
            {"id": "dw_2", "sql": "SELECT n, d FROM t ORDER BY n DESC"},
            {"id": "dw_3", "sql": "SELECT v FROM t"},
        ],
    )
    _write_jsonl(
        data / "gold_results.jsonl",
        [
            {"task_id": "dw_1", "ordered": False, "result": table(["v"], [["1.00000000000001"]])},
            {"task_id": "dw_2", "ordered": True, "result": table(["n", "d"], [["1", "A"], ["1", "B"]])},
            {"task_id": "dw_3", "ordered": False, "result": table(["v"], [["5"]])},
        ],
    )
    run_root = tmp_path / "run"
    answers = {
        "dw_1": table(["v"], [["1"]]),
        "dw_2": table(["n", "d"], [["1", "B"], ["1", "A"]]),
    }
    for task_id, result in answers.items():
        task_dir = run_root / "tasks" / task_id / "0"
        task_dir.mkdir(parents=True)
        (task_dir / "final.json").write_text(
            json.dumps(
                {"status": "answered", "result": result, "answer": "", "final_sql": "SELECT 1"}
            ),
            encoding="utf-8",
        )
    failed_dir = run_root / "tasks" / "dw_3" / "0"
    failed_dir.mkdir(parents=True)
    (failed_dir / "final.json").write_text(
        json.dumps({"status": "failed", "failure_reason": "agent_timeout"}), encoding="utf-8"
    )

    records, aggregate = evaluate_run(data_dir=data, run_root=run_root)

    by_id = {record["task_id"]: record for record in records}
    assert (by_id["dw_1"]["strict_ex"], by_id["dw_1"]["relaxed_ex"]) == (0, 1)
    assert (by_id["dw_2"]["strict_ex"], by_id["dw_2"]["relaxed_ex"]) == (0, 1)
    assert (by_id["dw_3"]["strict_ex"], by_id["dw_3"]["relaxed_ex"]) == (0, 0)
    assert by_id["dw_3"]["failure_reason"] == "agent_timeout"
    assert aggregate["task_count"] == 3
    assert aggregate["strict_ex_sum"] == 0
    assert aggregate["relaxed_ex_sum"] == 2
    assert (run_root / "evaluation" / "evaluator_results.jsonl").exists()
    assert (run_root / "evaluation" / "aggregate_metrics.json").exists()
