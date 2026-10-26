#!/usr/bin/env python3
"""Score agent result tables against the stored db_agent_view gold results, strictly and relaxed.

Strict EX is the semantic-catalog C0 rule: numbers must match digit for digit and ordered
tasks must match row for row. Relaxed EX accepts numbers within float noise of a gold number
(relative 1e-9, absolute 1e-12, never between two integers) and, for ordered tasks, only
requires the sequence of ORDER BY key values to match, so rows with tied sort keys may appear
in any order. Text keys are tied the way MySQL ties them: case- and accent-insensitively.
"""

from __future__ import annotations

import argparse
import itertools
import json
import re
import sys
import unicodedata
from collections import Counter
from decimal import Decimal
from pathlib import Path
from typing import Any, Iterator, Mapping, NamedTuple, Sequence

import sqlglot
from sqlglot import exp

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "runner"))

from common import (  # noqa: E402
    ContractError,
    _canonical_cell,
    _canonical_column_name,
    compare_result_details,
    validate_final_response,
)

RELATIVE_TOLERANCE = Decimal("1e-9")
ABSOLUTE_TOLERANCE = Decimal("1e-12")
INTEGER_LITERAL = re.compile(r"\s*[+-]?\d+\s*")
COARSE_DIGITS = 10
MAX_COLUMN_MAPPINGS = 1000


def outer_order_keys(sql: str, columns: Sequence[str]) -> list[int] | None:
    """Indices of the result columns that the outermost ORDER BY sorts on, if all resolvable."""
    try:
        tree = sqlglot.parse_one(sql, read="mysql")
    except sqlglot.errors.ParseError:
        return None
    if not isinstance(tree, exp.Select) or not tree.args.get("order"):
        return None
    projections = tree.expressions if len(tree.expressions) == len(columns) else []
    names = [column.upper() for column in columns]
    keys = []
    for ordered in tree.args["order"].expressions:
        key = _resolve_order_key(ordered.this, projections, names)
        if key is None:
            return None
        keys.append(key)
    return keys


def _resolve_order_key(
    expression: exp.Expression, projections: Sequence[exp.Expression], names: Sequence[str]
) -> int | None:
    if isinstance(expression, exp.Literal) and expression.is_int:
        position = int(expression.this) - 1
        return position if 0 <= position < len(names) else None
    for index, projection in enumerate(projections):
        is_alias_reference = (
            isinstance(expression, exp.Column)
            and not expression.table
            and isinstance(projection, exp.Alias)
            and expression.name.upper() == projection.alias.upper()
        )
        if is_alias_reference or projection.unalias() == expression:
            return index
    if isinstance(expression, exp.Column) and expression.name.upper() in names:
        return names.index(expression.name.upper())
    return None


class _Cell(NamedTuple):
    canonical: tuple[str, str | None]
    number: Decimal | None
    integral: bool
    coarse: tuple[str, str | None]


def _cell(value: Any) -> _Cell:
    canonical = _canonical_cell(value)
    if canonical[0] != "number":
        return _Cell(canonical, None, False, canonical)
    number = Decimal(canonical[1])
    if isinstance(value, int) or (isinstance(value, str) and INTEGER_LITERAL.fullmatch(value)):
        return _Cell(canonical, number, True, canonical)
    return _Cell(canonical, number, False, ("number", format(number, f".{COARSE_DIGITS}g")))


def _collated(cell: _Cell) -> _Cell:
    """Approximate utf8mb4_0900_ai_ci, the collation of every db_agent_view text column."""
    if cell.canonical[0] != "string":
        return cell
    decomposed = unicodedata.normalize("NFKD", cell.canonical[1])
    key = "".join(char for char in decomposed if not unicodedata.combining(char)).casefold()
    return cell._replace(canonical=("string", key), coarse=("string", key))


def _cells_match(actual: _Cell, gold: _Cell) -> bool:
    if actual.canonical == gold.canonical:
        return True
    if actual.number is None or gold.number is None:
        return False
    if actual.integral and gold.integral:
        return False
    difference = abs(actual.number - gold.number)
    return difference <= ABSOLUTE_TOLERANCE or difference <= RELATIVE_TOLERANCE * max(
        abs(actual.number), abs(gold.number)
    )


def _sequences_match(
    actual: Sequence[Sequence[_Cell]], gold: Sequence[Sequence[_Cell]], *, ordered: bool
) -> bool:
    """Row-wise tolerant equality; unordered rows are paired by sorting on their coarse values."""
    if len(actual) != len(gold):
        return False
    if not ordered:
        actual = sorted(actual, key=lambda row: tuple(cell.coarse for cell in row))
        gold = sorted(gold, key=lambda row: tuple(cell.coarse for cell in row))
    return all(
        all(_cells_match(a, g) for a, g in zip(actual_row, gold_row))
        for actual_row, gold_row in zip(actual, gold)
    )


def _project(rows: Sequence[Sequence[_Cell]], positions: Sequence[int]) -> list[tuple[_Cell, ...]]:
    return [tuple(row[position] for position in positions) for row in rows]


def _column_mappings(
    actual_columns: Sequence[str],
    actual_rows: Sequence[Sequence[_Cell]],
    gold_columns: Sequence[str],
    gold_rows: Sequence[Sequence[_Cell]],
) -> Iterator[list[int]]:
    """Yield actual-column positions for each gold column: by name if possible, else by values."""
    actual_names = [_canonical_column_name(column) for column in actual_columns]
    gold_names = [_canonical_column_name(column) for column in gold_columns]
    if (
        len(set(actual_names)) == len(actual_names)
        and len(set(gold_names)) == len(gold_names)
        and set(actual_names) == set(gold_names)
    ):
        yield [actual_names.index(name) for name in gold_names]
        return
    candidates = [
        [
            actual_index
            for actual_index in range(len(actual_columns))
            if _sequences_match(
                _project(actual_rows, [actual_index]), _project(gold_rows, [gold_index]), ordered=False
            )
        ]
        for gold_index in range(len(gold_columns))
    ]
    yielded = 0
    for positions in itertools.product(*candidates):
        if len(set(positions)) != len(positions):
            continue
        yield list(positions)
        yielded += 1
        if yielded >= MAX_COLUMN_MAPPINGS:
            return


def relaxed_compare(
    actual: Mapping[str, Any],
    gold: Mapping[str, Any],
    *,
    ordered: bool,
    order_keys: Sequence[int] | None,
) -> tuple[bool, str]:
    mode = "unordered" if not ordered else "strict_fallback" if order_keys is None else "order_keys"
    actual_rows = [[_cell(value) for value in row] for row in actual["rows"]]
    gold_rows = [[_cell(value) for value in row] for row in gold["rows"]]
    if len(actual["columns"]) != len(gold["columns"]) or len(actual_rows) != len(gold_rows):
        return False, mode
    for positions in _column_mappings(actual["columns"], actual_rows, gold["columns"], gold_rows):
        aligned = _project(actual_rows, positions)
        if mode == "strict_fallback":
            matches = _sequences_match(aligned, gold_rows, ordered=True)
        else:
            matches = _sequences_match(aligned, gold_rows, ordered=False)
            if matches and mode == "order_keys":
                matches = _sequences_match(
                    [tuple(map(_collated, row)) for row in _project(aligned, order_keys)],
                    [tuple(map(_collated, row)) for row in _project(gold_rows, order_keys)],
                    ordered=True,
                )
        if matches:
            return True, mode
    return False, mode


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def evaluate_run(*, data_dir: Path, run_root: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    manifest = _read_jsonl(data_dir / "manifest.jsonl")
    gold_sql = {row["id"]: row["sql"] for row in _read_jsonl(data_dir / "tasks_gold.jsonl")}
    gold_results = {row["task_id"]: row for row in _read_jsonl(data_dir / "gold_results.jsonl")}

    records = []
    for entry in manifest:
        task_id, seed = entry["task_id"], entry["seed"]
        gold = gold_results[task_id]
        record: dict[str, Any] = {
            "task_id": task_id,
            "seed": seed,
            "ordered": gold["ordered"],
            "failure_reason": None,
            "column_alignment": None,
            "order_check": None,
            "strict_ex": 0,
            "relaxed_ex": 0,
        }
        records.append(record)
        try:
            response = json.loads(
                (run_root / "tasks" / task_id / str(seed) / "final.json").read_text(encoding="utf-8")
            )
            if isinstance(response, dict) and response.get("status") == "failed":
                record["failure_reason"] = response.get("failure_reason") or "failed"
                continue
            final = validate_final_response(response)
        except (OSError, json.JSONDecodeError, ContractError, AttributeError):
            record["failure_reason"] = "invalid_final_json"
            continue

        try:
            strict = compare_result_details(final["result"], gold["result"], ordered=gold["ordered"])
            matches, order_check = relaxed_compare(
                final["result"],
                gold["result"],
                ordered=gold["ordered"],
                order_keys=outer_order_keys(gold_sql[task_id], gold["result"]["columns"])
                if gold["ordered"]
                else None,
            )
        except ContractError:
            record["failure_reason"] = "invalid_result"
            continue
        record["column_alignment"] = strict.column_alignment
        record["strict_ex"] = int(strict.matches)
        record["relaxed_ex"] = int(matches)
        record["order_check"] = order_check
        if not matches:
            record["failure_reason"] = "result_mismatch"

    count = len(records)
    strict_sum = sum(record["strict_ex"] for record in records)
    relaxed_sum = sum(record["relaxed_ex"] for record in records)
    aggregate = {
        "task_count": count,
        "strict_ex_sum": strict_sum,
        "strict_ex_accuracy": strict_sum / count if count else None,
        "relaxed_ex_sum": relaxed_sum,
        "relaxed_ex_accuracy": relaxed_sum / count if count else None,
        "failure_reason_counts": dict(Counter(r["failure_reason"] for r in records if r["failure_reason"])),
        "order_check_counts": dict(Counter(r["order_check"] for r in records if r["order_check"])),
    }
    output_dir = run_root / "evaluation"
    output_dir.mkdir(parents=True, exist_ok=True)
    with (output_dir / "evaluator_results.jsonl").open("w", encoding="utf-8") as output:
        for record in records:
            output.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
    (output_dir / "aggregate_metrics.json").write_text(
        json.dumps(aggregate, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return records, aggregate


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--data-dir", type=Path, default=HERE / "data")
    args = parser.parse_args()
    _, aggregate = evaluate_run(data_dir=args.data_dir, run_root=args.run_root)
    print(json.dumps(aggregate, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
