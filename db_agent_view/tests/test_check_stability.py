import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from check_stability import unstable_tasks


def test_unstable_tasks_reports_every_non_exact_rerun():
    reference = {
        "dw_1": {"ordered": True, "result": {"columns": ["X"], "rows": [["1"], ["2"]]}},
        "dw_2": {"ordered": True, "result": {"columns": ["X"], "rows": [["0.30000000000000004"]]}},
        "dw_3": {"ordered": False, "result": {"columns": ["X"], "rows": [["a"]]}},
    }
    reruns = [
        {
            "dw_1": {"columns": ["X"], "rows": [["2"], ["1"]]},
            "dw_2": {"columns": ["X"], "rows": [["0.3"]]},
            "dw_3": {"columns": ["X"], "rows": [["a"]]},
        },
        {
            "dw_1": {"columns": ["X"], "rows": [["1"], ["2"]]},
            "dw_2": {"columns": ["X"], "rows": [["0.30000000000000004"]]},
            "dw_3": {"columns": ["X"], "rows": [["a"]]},
        },
    ]
    assert unstable_tasks(reference, reruns) == {
        "dw_1": ["order_only"],
        "dw_2": ["float_tolerance"],
    }
