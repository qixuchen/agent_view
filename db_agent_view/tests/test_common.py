import pytest

from common import (
    ContractError,
    canonicalize_result,
    compare_result_details,
    compare_results,
    project_manifest_entry,
    validate_final_response,
)


def test_manifest_projection_exposes_only_agent_safe_fields():
    source = {
        "id": "dw_0001",
        "question": "How many active students are there?",
        "db": "dw",
        "sql": "SELECT COUNT(*) FROM STUDENT",
        "tables": '["STUDENT"]',
        "join_keys": "[]",
        "domain_knowledge": "[]",
    }

    assert project_manifest_entry(source, seed=7) == {
        "task_id": "dw_0001",
        "question": "How many active students are there?",
        "database": "dw",
        "seed": 7,
    }


def test_manifest_projection_rejects_missing_required_fields():
    with pytest.raises(ContractError, match="question"):
        project_manifest_entry({"id": "dw_0001", "db": "dw"}, seed=0)


def test_final_response_requires_result_and_final_sql():
    response = {
        "status": "answered",
        "result": {"columns": ["COUNT"], "rows": [[42]]},
        "answer": "42",
        "evidence_tool_call_ids": ["mysql_1"],
    }

    with pytest.raises(ContractError, match="final_sql"):
        validate_final_response(response)


def test_final_response_accepts_a_structured_table():
    response = {
        "status": "answered",
        "result": {
            "columns": ["DEPARTMENT_NAME", "EMPLOYEE_COUNT"],
            "rows": [["Engineering", 42], ["Sales", 31]],
        },
        "answer": "Engineering has 42 employees.",
        "final_sql": "SELECT department_name, COUNT(*) FROM employee GROUP BY 1",
        "evidence_tool_call_ids": ["mysql_3"],
    }

    validated = validate_final_response(response)

    assert validated["result"]["rows"][1] == ["Sales", 31]


def test_unordered_result_comparison_ignores_row_order_but_preserves_duplicates():
    expected = {
        "columns": ["department", "count"],
        "rows": [["Sales", 1], ["Engineering", 2], ["Sales", 1]],
    }
    actual = {
        "columns": ["DEPARTMENT", "COUNT"],
        "rows": [["Sales", 1], ["Sales", 1], ["Engineering", 2]],
    }

    assert compare_results(actual, expected, ordered=False)
    assert not compare_results(actual, {**expected, "rows": expected["rows"][:-1]}, ordered=False)


def test_ordered_result_comparison_preserves_row_order():
    expected = {"columns": ["name"], "rows": [["Engineering"], ["Sales"]]}
    actual = {"columns": ["NAME"], "rows": [["Sales"], ["Engineering"]]}

    assert not compare_results(actual, expected, ordered=True)


def test_canonicalization_treats_equivalent_numeric_json_values_consistently():
    result = {"columns": ["value"], "rows": [["1.00"], [2], [None]]}

    assert canonicalize_result(result, ordered=True) == (
        ("VALUE",),
        (
            (("number", "1"),),
            (("number", "2"),),
            (("null", None),),
        ),
    )


def test_canonicalization_does_not_drop_trailing_integer_zeroes():
    result = {"columns": ["value"], "rows": [[10], ["10.0"]]}

    assert canonicalize_result(result, ordered=True)[1] == (
        (("number", "10"),),
        (("number", "10"),),
    )


def test_comparison_reorders_unique_agent_columns_into_gold_column_order():
    expected = {
        "columns": ["organization", "employee_count"],
        "rows": [["Engineering", 42], ["Sales", 31]],
    }
    actual = {
        "columns": [" EMPLOYEE_COUNT ", "ORGANIZATION"],
        "rows": [[42, "Engineering"], [31, "Sales"]],
    }

    assert compare_results(actual, expected, ordered=True)


def test_comparison_value_matches_duplicate_normalized_column_names():
    expected = {"columns": ["value", "VALUE"], "rows": [[1, 2]]}
    actual = {"columns": ["VALUE", "value"], "rows": [[2, 1]]}

    assert compare_results(actual, expected, ordered=True)


def test_comparison_accepts_different_aliases_when_values_match_positionally():
    expected = {"columns": ["avg_dept_code", "dept_code_variance"], "rows": [[4, 2]]}
    actual = {
        "columns": ["average_hr_department_code", "variance_hr_department_code"],
        "rows": [[4, 2]],
    }

    assert compare_results(actual, expected, ordered=True)


def test_comparison_accepts_empty_equal_arity_results_with_different_aliases():
    expected = {"columns": ["gold_name", "gold_count"], "rows": []}
    actual = {"columns": ["agent_label", "total"], "rows": []}

    assert compare_results(actual, expected, ordered=False)


def test_comparison_rejects_different_column_counts_even_for_empty_results():
    expected = {"columns": ["gold_name", "gold_count"], "rows": []}
    actual = {"columns": ["agent_label"], "rows": []}

    assert not compare_results(actual, expected, ordered=False)


def test_unordered_value_match_with_permuted_rows_columns_and_aliases():
    expected = {
        "columns": ["org", "year", "count", "active", "score"],
        "rows": [
            ["MIT", 2019, 10, True, "1.50"],
            ["Harvard", 2020, 3, False, 2],
            ["Yale", 2018, None, True, 0],
            ["Stanford", 2021, 10, True, 1.5],
            ["Princeton", 2019, 7, False, "4.00"],
        ],
    }
    actual = {
        "columns": ["pts", "school", "is_active", "n", "yr"],
        "rows": [
            [1.5, "Stanford", True, 10, 2021],
            [4, "Princeton", False, 7, 2019],
            [0, "Yale", True, None, 2018],
            ["2.0", "Harvard", False, 3, 2020],
            [1.5, "MIT", True, 10, 2019],
        ],
    }

    details = compare_result_details(actual, expected, ordered=False)

    assert details.matches
    assert details.column_alignment == "value_matched"


def test_unordered_rejects_broken_row_pairing_when_column_multisets_still_match():
    expected = {
        "columns": ["org", "year", "count", "active", "score"],
        "rows": [
            ["MIT", 2019, 10, True, "1.50"],
            ["Harvard", 2020, 3, False, 2],
            ["Yale", 2018, None, True, 0],
            ["Stanford", 2021, 10, True, 1.5],
            ["Princeton", 2019, 7, False, "4.00"],
        ],
    }
    actual = {
        "columns": ["pts", "school", "is_active", "n", "yr"],
        "rows": [
            [1.5, "Stanford", True, 10, 2021],
            [4, "Princeton", False, 7, 2019],
            [0, "Yale", True, None, 2018],
            ["2.0", "Harvard", False, 3, 2019],
            [1.5, "MIT", True, 10, 2020],
        ],
    }

    details = compare_result_details(actual, expected, ordered=False)

    assert not details.matches
    assert details.column_alignment == "value_matched"


def test_unordered_value_match_preserves_duplicate_rows_after_permutation():
    expected = {
        "columns": ["department", "count", "campus"],
        "rows": [
            ["Sales", 1, "East"],
            ["Sales", 1, "East"],
            ["Engineering", 2, "West"],
            ["Sales", 3, "West"],
        ],
    }
    actual = {
        "columns": ["site", "total", "unit"],
        "rows": [
            ["West", 3, "Sales"],
            ["East", 1, "Sales"],
            ["West", 2, "Engineering"],
            ["East", 1, "Sales"],
        ],
    }

    details = compare_result_details(actual, expected, ordered=False)

    assert details.matches
    assert details.column_alignment == "value_matched"
    assert not compare_results(
        {"columns": actual["columns"], "rows": actual["rows"][:-1]},
        expected,
        ordered=False,
    )


def test_ordered_value_match_allows_column_permutation_but_not_row_permutation():
    expected = {
        "columns": ["name", "units", "term"],
        "rows": [
            ["Algebra", 12, "Fall"],
            ["Biology", 9, "Spring"],
            ["Chemistry", 15, "Fall"],
        ],
    }
    matching = {
        "columns": ["semester", "course", "credits"],
        "rows": [
            ["Fall", "Algebra", 12],
            ["Spring", "Biology", 9],
            ["Fall", "Chemistry", 15],
        ],
    }
    row_shuffled = {
        "columns": matching["columns"],
        "rows": list(reversed(matching["rows"])),
    }

    matched = compare_result_details(matching, expected, ordered=True)
    mismatched = compare_result_details(row_shuffled, expected, ordered=True)

    assert matched.matches
    assert matched.column_alignment == "value_matched"
    assert not mismatched.matches
    assert mismatched.column_alignment == "value_matched"


def test_unordered_value_match_with_nulls_and_mixed_numeric_forms():
    expected = {
        "columns": ["label", "qty", "flag"],
        "rows": [
            ["alpha", "1.00", None],
            ["beta", 2, True],
            ["gamma", 2, False],
            ["delta", None, True],
        ],
    }
    actual = {
        "columns": ["enabled", "amount", "key"],
        "rows": [
            [False, 2.0, "gamma"],
            [True, None, "delta"],
            [None, 1, "alpha"],
            [True, "2.00", "beta"],
        ],
    }

    details = compare_result_details(actual, expected, ordered=False)

    assert details.matches
    assert details.column_alignment == "value_matched"


def test_canonicalization_unicode_normalizes_but_does_not_trim_data_values():
    expected = {"columns": ["name"], "rows": [["Café"]]}
    equivalent = {"columns": ["name"], "rows": [["Cafe\u0301"]]}
    padded = {"columns": ["name"], "rows": [[" Café"]]}

    assert compare_results(equivalent, expected, ordered=True)
    assert not compare_results(padded, expected, ordered=True)


def test_canonicalization_keeps_boolean_and_numeric_values_distinct():
    expected = {"columns": ["enabled"], "rows": [[True]]}
    actual = {"columns": ["enabled"], "rows": [[1]]}

    assert not compare_results(actual, expected, ordered=True)


def test_canonicalization_requires_exact_iso_temporal_representation():
    expected = {"columns": ["occurred_at"], "rows": [["2026-09-02T06:45:09"]]}
    equivalent = {"columns": ["occurred_at"], "rows": [["2026-09-02T06:45:09"]]}
    locale_form = {"columns": ["occurred_at"], "rows": [["09/02/2026 06:45:09"]]}

    assert compare_results(equivalent, expected, ordered=True)
    assert not compare_results(locale_form, expected, ordered=True)


def test_canonicalization_rejects_non_finite_numbers_and_misaligned_rows():
    with pytest.raises(ContractError, match="numbers must be finite"):
        canonicalize_result({"columns": ["value"], "rows": [[float("nan")]]}, ordered=True)
    with pytest.raises(ContractError, match="align"):
        canonicalize_result({"columns": ["value"], "rows": [[1, 2]]}, ordered=True)
