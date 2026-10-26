import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from run_gold import check_task, classify_difference, execute_sql


def fake_runner(outputs):
    calls = []

    def run(command, **kwargs):
        calls.append(command)
        return subprocess.CompletedProcess(command, 0, stdout=outputs.pop(0), stderr="")

    return run, calls


XML_ONE_ROW = (
    '<?xml version="1.0"?><resultset><row>'
    '<field name="N">1</field><field name="M" xsi:nil="true" '
    'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" /></row></resultset>'
)


def test_execute_sql_uses_requested_database_and_parses_xml():
    run, calls = fake_runner([XML_ONE_ROW])
    result = execute_sql(
        "SELECT 1", database="db_agent_view", container="c", user="u", password="p", runner=run
    )
    assert result == {"columns": ["N", "M"], "rows": [["1", None]]}
    assert "--database=db_agent_view" in calls[0]
    assert "--default-character-set=utf8mb4" in calls[0]
    assert len(calls) == 1


def test_execute_sql_reads_headers_when_result_is_empty():
    run, calls = fake_runner(['<?xml version="1.0"?><resultset></resultset>', "N\tM\n"])
    result = execute_sql(
        "SELECT 1", database="db_agent_view", container="c", user="u", password="p", runner=run
    )
    assert result == {"columns": ["N", "M"], "rows": []}
    assert "--batch" in calls[1]


def test_check_task_matches_when_both_databases_agree():
    table = {"columns": ["N"], "rows": [["2"], ["1"]]}
    record = check_task(
        {"task_id": "dw_1", "sql": "SELECT N FROM T"},
        execute={"db_agent_view": lambda sql: table, "dw": lambda sql: table},
    )
    assert record["status"] == "ok"
    assert record["matches_dw"] is True
    assert record["ordered"] is False
    assert record["row_count"] == 2
    assert record["result"] == table


def test_check_task_flags_difference_from_dw():
    record = check_task(
        {"task_id": "dw_1", "sql": "SELECT N FROM T ORDER BY N"},
        execute={
            "db_agent_view": lambda sql: {"columns": ["N"], "rows": [["1"]]},
            "dw": lambda sql: {"columns": ["N"], "rows": [["1"], ["2"]]},
        },
    )
    assert record["status"] == "ok"
    assert record["ordered"] is True
    assert record["matches_dw"] is False
    assert record["dw_comparison"] == "different"


def test_classify_tolerates_float_tail_noise():
    a = {"columns": ["X", "V"], "rows": [["a", "3565.2422963432464"]]}
    b = {"columns": ["X", "V"], "rows": [["a", "3565.242296343227"]]}
    assert classify_difference(a, b, ordered=True) == "float_tolerance"


def test_classify_detects_order_only_difference():
    a = {"columns": ["X"], "rows": [["1"], ["2"]]}
    b = {"columns": ["X"], "rows": [["2"], ["1"]]}
    assert classify_difference(a, b, ordered=True) == "order_only"


def test_classify_detects_real_difference():
    a = {"columns": ["X"], "rows": [["1"]]}
    b = {"columns": ["X"], "rows": [["1.1"]]}
    assert classify_difference(a, b, ordered=True) == "different"


def test_classify_exact():
    a = {"columns": ["X"], "rows": [["1"]]}
    assert classify_difference(a, a, ordered=True) == "exact"


def test_check_task_records_execution_error():
    def fail(sql):
        raise RuntimeError("ERROR 1146: Table doesn't exist")

    record = check_task(
        {"task_id": "dw_1", "sql": "SELECT 1"},
        execute={"db_agent_view": fail, "dw": lambda sql: {"columns": ["N"], "rows": []}},
    )
    assert record["status"] == "error"
    assert "1146" in record["error"]
    assert record["matches_dw"] is False
