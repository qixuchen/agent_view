"""Pure contracts shared by the BEAVER C0 runner and evaluator."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any, Mapping
import unicodedata


class ContractError(ValueError):
    """Raised when agent/evaluator data violates the C0 interface."""


def project_manifest_entry(source: Mapping[str, Any], *, seed: int) -> dict[str, Any]:
    """Project one BEAVER row into the only fields visible to the agent runner."""
    required = {"id": "task_id", "question": "question", "db": "database"}
    output: dict[str, Any] = {}

    for source_key, output_key in required.items():
        value = source.get(source_key)
        if not isinstance(value, str) or not value.strip():
            raise ContractError(f"Missing or invalid required field: {source_key}")
        output[output_key] = value

    if not isinstance(seed, int) or isinstance(seed, bool) or seed < 0:
        raise ContractError("seed must be a non-negative integer")

    output["seed"] = seed
    return output


def validate_final_response(response: Mapping[str, Any]) -> dict[str, Any]:
    """Validate the structured C0 final response without judging correctness."""
    if response.get("status") != "answered":
        raise ContractError("status must be 'answered'")

    result = response.get("result")
    if not isinstance(result, Mapping):
        raise ContractError("result must be an object")

    columns = result.get("columns")
    rows = result.get("rows")
    if not isinstance(columns, list) or not all(
        isinstance(column, str) and column.strip() for column in columns
    ):
        raise ContractError("result.columns must be a non-empty list of strings")
    if not isinstance(rows, list):
        raise ContractError("result.rows must be a list")
    if any(not isinstance(row, list) or len(row) != len(columns) for row in rows):
        raise ContractError("each result row must align with result.columns")

    final_sql = response.get("final_sql")
    if not isinstance(final_sql, str) or not final_sql.strip():
        raise ContractError("final_sql must be a non-empty string")

    answer = response.get("answer")
    if not isinstance(answer, str):
        raise ContractError("answer must be a string")

    evidence = response.get("evidence_tool_call_ids", [])
    if not isinstance(evidence, list) or not all(isinstance(item, str) for item in evidence):
        raise ContractError("evidence_tool_call_ids must be a list of strings")

    return {
        "status": "answered",
        "result": {"columns": columns, "rows": rows},
        "answer": answer,
        "final_sql": final_sql,
        "evidence_tool_call_ids": evidence,
    }


def _canonical_cell(value: Any) -> tuple[str, str | None]:
    if value is None:
        return ("null", None)
    if isinstance(value, bool):
        return ("boolean", str(value).lower())
    if isinstance(value, (int, float, Decimal)) and not isinstance(value, bool):
        return _canonical_number(value)
    if isinstance(value, str):
        try:
            return _canonical_number(value)
        except ContractError:
            return ("string", unicodedata.normalize("NFC", value))
    raise ContractError(f"Unsupported result cell type: {type(value).__name__}")


def _canonical_number(value: Any) -> tuple[str, str]:
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError) as error:
        raise ContractError("not a numeric value") from error
    if not number.is_finite():
        raise ContractError("numbers must be finite")
    normalized = format(number.normalize(), "f")
    if "." in normalized:
        normalized = normalized.rstrip("0").rstrip(".")
    return ("number", normalized or "0")


def canonicalize_result(
    result: Mapping[str, Any], *, ordered: bool
) -> tuple[tuple[str, ...], tuple[tuple[tuple[str, str | None], ...], ...]]:
    """Return a deterministic typed representation of an agent result table."""
    validated = validate_final_response(
        {
            "status": "answered",
            "result": result,
            "answer": "",
            "final_sql": "validation placeholder",
        }
    )["result"]
    columns = tuple(_canonical_column_name(column) for column in validated["columns"])
    rows = tuple(tuple(_canonical_cell(cell) for cell in row) for row in validated["rows"])
    return columns, rows if ordered else tuple(sorted(rows))


def _canonical_column_name(column: str) -> str:
    return unicodedata.normalize("NFC", column).strip().upper()


@dataclass(frozen=True)
class ResultComparison:
    """Result-equivalence decision plus its auditable column-alignment mode."""

    matches: bool
    column_alignment: str


def _rows_match(
    actual_rows: tuple[tuple[tuple[str, str | None], ...], ...],
    expected_rows: tuple[tuple[tuple[str, str | None], ...], ...],
    *,
    ordered: bool,
) -> bool:
    return actual_rows == expected_rows if ordered else tuple(sorted(actual_rows)) == tuple(
        sorted(expected_rows)
    )


def _permute_rows(
    rows: tuple[tuple[tuple[str, str | None], ...], ...], positions: list[int]
) -> tuple[tuple[tuple[str, str | None], ...], ...]:
    return tuple(tuple(row[position] for position in positions) for row in rows)


def _column_signature(
    rows: tuple[tuple[tuple[str, str | None], ...], ...], index: int, *, ordered: bool
) -> tuple[tuple[str, str | None], ...]:
    values = tuple(row[index] for row in rows)
    return values if ordered else tuple(sorted(values))


def compare_result_details(
    actual: Mapping[str, Any], expected: Mapping[str, Any], *, ordered: bool
) -> ResultComparison:
    """Compare result relations while permitting value-proven column permutations."""
    actual_columns, actual_rows = canonicalize_result(actual, ordered=True)
    expected_columns, expected_rows = canonicalize_result(expected, ordered=True)
    if len(actual_columns) != len(expected_columns):
        return ResultComparison(False, "arity_mismatch")

    names_are_unique = len(set(actual_columns)) == len(actual_columns) and len(
        set(expected_columns)
    ) == len(expected_columns)
    if names_are_unique and set(actual_columns) == set(expected_columns):
        positions = [actual_columns.index(column) for column in expected_columns]
        alignment = "exact_name" if positions == list(range(len(positions))) else "name_reordered"
        return ResultComparison(
            _rows_match(
                _permute_rows(actual_rows, positions), expected_rows, ordered=ordered
            ),
            alignment,
        )

    if not actual_rows and not expected_rows:
        return ResultComparison(True, "positional_fallback_for_empty_result")
    if len(actual_rows) != len(expected_rows):
        return ResultComparison(False, "value_matched")

    candidates = [
        [
            actual_index
            for actual_index in range(len(actual_columns))
            if _column_signature(actual_rows, actual_index, ordered=ordered)
            == _column_signature(expected_rows, expected_index, ordered=ordered)
        ]
        for expected_index in range(len(expected_columns))
    ]
    if any(not options for options in candidates):
        return ResultComparison(False, "value_matched")

    valid_mapping_count = 0
    used_positions: set[int] = set()
    positions = [-1] * len(expected_columns)
    expected_indices = sorted(range(len(expected_columns)), key=lambda index: len(candidates[index]))

    def visit(cursor: int) -> None:
        nonlocal valid_mapping_count
        if valid_mapping_count > 1:
            return
        if cursor == len(expected_indices):
            if _rows_match(
                _permute_rows(actual_rows, positions), expected_rows, ordered=ordered
            ):
                valid_mapping_count += 1
            return
        expected_index = expected_indices[cursor]
        for actual_index in candidates[expected_index]:
            if actual_index in used_positions:
                continue
            used_positions.add(actual_index)
            positions[expected_index] = actual_index
            visit(cursor + 1)
            used_positions.remove(actual_index)
            positions[expected_index] = -1

    visit(0)
    if valid_mapping_count > 1:
        return ResultComparison(True, "ambiguous_value_matching")
    return ResultComparison(bool(valid_mapping_count), "value_matched")


def compare_results(
    actual: Mapping[str, Any], expected: Mapping[str, Any], *, ordered: bool
) -> bool:
    """Compare typed result tables according to the frozen ordering policy."""
    return compare_result_details(actual, expected, ordered=ordered).matches
