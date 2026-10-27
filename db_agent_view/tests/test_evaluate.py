import json
from pathlib import Path

import pytest

import evaluate
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


@pytest.mark.parametrize(
    "question",
    [
        "List each department and its total units in descending order. Do not return any rounded answers.",
        "Show the subjects in alphabetical order.",
        "For each school, give the number of subjects. Sort the table by academic year and term code.",
        "Compute the ratio for each department, ordering the results by this ratio in descending order.",
        "List the departments (excluding political science), ranked by the range of total units.",
        "Order the results by enrollment, highest first.",
        "Give the totals, sorted by department name.",
        "List the results in order of decreasing variance. Do not return any rounded answers.",
        "Give the standard deviation, ordered from highest to lowest standard deviation.",
    ],
)
def test_question_requests_order_detects_requested_row_order(question: str) -> None:
    assert evaluate.question_requests_order(question)


@pytest.mark.parametrize(
    "question",
    [
        "List the columns in the following order: department name, average enrollment.",
        "Give the department name and the number of enrolled students, in that order. Do not return any rounded answers.",
        "Give the average over the current and 2 preceding rows ordered by the department's budget code.",
        "Show the subject code, school name, and the dense rank of each course considering the units.",
        "Within each school name group ordered by subject code, count the subjects.",
        "From the top 10 departments with the highest total number of enrolled students, show each name.",
        "Join the tables in order to count the subjects per department.",
        "For each department, what is the average number of enrolled students?",
    ],
)
def test_question_requests_order_ignores_column_order_window_frames_and_top_n(question: str) -> None:
    assert not evaluate.question_requests_order(question)


def _evaluate_one_ordered_task(tmp_path: Path, question: str):
    data = tmp_path / "data"
    data.mkdir()
    _write_jsonl(data / "manifest.jsonl", [{"task_id": "dw_1", "question": question, "database": "db_agent_view", "seed": 0}])
    _write_jsonl(data / "tasks_gold.jsonl", [{"id": "dw_1", "sql": "SELECT d, n FROM t ORDER BY n DESC"}])
    _write_jsonl(
        data / "gold_results.jsonl",
        [{"task_id": "dw_1", "ordered": True, "result": table(["d", "n"], [["A", "2"], ["B", "1"]])}],
    )
    task_dir = tmp_path / "run" / "tasks" / "dw_1" / "0"
    task_dir.mkdir(parents=True)
    (task_dir / "final.json").write_text(
        json.dumps({
            "status": "answered",
            "result": table(["d", "n"], [["B", "1"], ["A", "2"]]),
            "answer": "",
            "final_sql": "SELECT 1",
        }),
        encoding="utf-8",
    )
    records, _ = evaluate_run(data_dir=data, run_root=tmp_path / "run")
    return records[0]


def test_relaxed_ex_ignores_gold_order_the_question_never_asked_for(tmp_path: Path) -> None:
    record = _evaluate_one_ordered_task(tmp_path, "For each department, what is the total?")

    assert (record["strict_ex"], record["relaxed_ex"]) == (0, 1)
    assert record["question_requests_order"] is False
    assert record["order_check"] == "unordered"


def test_relaxed_ex_checks_order_the_question_asks_for(tmp_path: Path) -> None:
    record = _evaluate_one_ordered_task(tmp_path, "List each department's total in descending order.")

    assert (record["strict_ex"], record["relaxed_ex"]) == (0, 0)
    assert record["question_requests_order"] is True
    assert record["order_check"] == "order_keys"
