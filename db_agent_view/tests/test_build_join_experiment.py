import json
import re
from pathlib import Path

import pytest

import build_join_experiment
from build_join_experiment import EXPERIMENTS, HERE, build, domain_knowledge_context, join_path, select_join_path_tasks

PATH = {
    "tables": ["A", "B", "C"],
    "join_keys": [["A.x", "B.x"], ["B.y", "C.y"]],
}


def _row(task_id, tables, join_keys, domain_knowledge=()):
    return {
        "id": task_id,
        "question": f"question {task_id}",
        "db": "db_agent_view",
        "sql": "SELECT 1",
        "tables": json.dumps(tables),
        "join_keys": json.dumps(join_keys),
        "column_mapping": json.dumps({"x": ["A.x"]}),
        "domain_knowledge": json.dumps(list(domain_knowledge)),
    }


def test_join_path_ignores_table_order_and_join_key_orientation():
    assert join_path(_row("dw_1", ["C", "A", "B"], [["C.y", "B.y"], ["B.x", "A.x"]])) == join_path(
        _row("dw_2", ["A", "B", "C"], [["A.x", "B.x"], ["B.y", "C.y"]])
    )


def test_select_join_path_tasks_requires_the_same_tables_and_the_same_join_keys():
    rows = [
        _row("dw_1", ["A", "B", "C"], [["A.x", "B.x"], ["B.y", "C.y"]]),
        _row("dw_2", ["A", "B", "C", "D"], [["A.x", "B.x"], ["B.y", "C.y"], ["C.z", "D.z"]]),
        _row("dw_3", ["A", "B", "C"], [["A.x", "B.x"], ["A.w", "C.w"]]),
        _row("dw_4", ["B", "C", "A"], [["C.y", "B.y"], ["B.x", "A.x"]]),
    ]
    assert select_join_path_tasks(rows, tables=PATH["tables"], join_keys=PATH["join_keys"]) == [
        "dw_1",
        "dw_4",
    ]


def test_domain_knowledge_context_lists_items_verbatim():
    row = _row("dw_1", ["A"], [], ['"math" is predicated by "TABLE.NAME = \'Mathematics\'"'])
    context = domain_knowledge_context(row)
    assert context.startswith("# Task-specific domain knowledge\n")
    assert '- "math" is predicated by "TABLE.NAME = \'Mathematics\'"\n' in context


def test_domain_knowledge_context_explains_the_table_placeholder():
    row = _row("dw_1", ["A"], [], ['"math" is predicated by "TABLE.NAME = \'Mathematics\'"'])
    assert "`TABLE` stands for whichever table has that column" in domain_knowledge_context(row)


def test_domain_knowledge_context_is_none_without_domain_knowledge():
    assert domain_knowledge_context(_row("dw_1", ["A"], [])) is None


def test_domain_knowledge_context_does_not_leak_other_annotations():
    row = _row("dw_1", ["A", "B"], [["A.x", "B.x"]], ["k is predicated by TABLE.K = 1"])
    context = domain_knowledge_context(row)
    assert "A.x" not in context and "SELECT" not in context


def test_build_writes_manifest_contexts_and_provenance(tmp_path: Path):
    tasks_gold = tmp_path / "tasks_gold.jsonl"
    rows = [
        _row("dw_1", ["A", "B", "C"], PATH["join_keys"], ["k1 is predicated by TABLE.K = 1"]),
        _row("dw_2", ["A", "B", "C"], PATH["join_keys"]),
        _row("dw_3", ["A", "B"], [["A.x", "B.x"]], ["k3 is predicated by TABLE.K = 3"]),
    ]
    tasks_gold.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    output_dir = tmp_path / "exp"

    provenance = build(
        name="exp", tasks_gold=tasks_gold, output_dir=output_dir, **PATH
    )

    manifest = [json.loads(line) for line in (output_dir / "manifest.jsonl").read_text().splitlines()]
    assert manifest == [
        {"task_id": "dw_1", "question": "question dw_1", "database": "db_agent_view", "seed": 0},
        {"task_id": "dw_2", "question": "question dw_2", "database": "db_agent_view", "seed": 0},
    ]
    contexts = [
        json.loads(line)
        for line in (output_dir / "domain_knowledge_contexts.jsonl").read_text().splitlines()
    ]
    assert [context["task_id"] for context in contexts] == ["dw_1"]
    assert "k1 is predicated by TABLE.K = 1" in contexts[0]["context"]
    assert provenance["task_ids"] == ["dw_1", "dw_2"]
    assert provenance["tasks_with_domain_knowledge"] == ["dw_1"]
    assert json.loads((output_dir / "provenance.json").read_text())["join_path"] == {
        "tables": ["A", "B", "C"],
        "join_keys": [["A.x", "B.x"], ["B.y", "C.y"]],
    }
    assert not (output_dir / "view_contexts.jsonl").exists()


def _contexts(path: Path) -> dict[str, str]:
    return {json.loads(line)["task_id"]: json.loads(line)["context"] for line in path.read_text().splitlines()}


def _write_tasks_gold(tmp_path: Path, rows) -> Path:
    tasks_gold = tmp_path / "tasks_gold.jsonl"
    tasks_gold.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    return tasks_gold


def test_build_writes_one_context_file_per_arm_note_before_the_unchanged_domain_knowledge(tmp_path: Path):
    tasks_gold = _write_tasks_gold(tmp_path, [
        _row("dw_1", ["A", "B", "C"], PATH["join_keys"], ["k1 is predicated by TABLE.K = 1"]),
        _row("dw_2", ["A", "B", "C"], PATH["join_keys"]),
    ])
    output_dir = tmp_path / "exp"
    notes = {"view": "# Agent views\nSee av_catalog.\n", "join_text": "# Join knowledge\nJoin A to B.\n"}

    provenance = build(name="exp", tasks_gold=tasks_gold, output_dir=output_dir, arm_notes=notes, **PATH)

    baseline = _contexts(output_dir / "domain_knowledge_contexts.jsonl")
    for arm, note in notes.items():
        assert _contexts(output_dir / f"{arm}_contexts.jsonl") == {
            "dw_1": note + "\n" + baseline["dw_1"],
            "dw_2": note,
        }
        assert f"{arm}_contexts.jsonl" in provenance["files"]
    assert provenance["arm_notes"] == notes


def test_build_drops_excluded_tasks_from_the_manifest_and_every_context_file(tmp_path: Path):
    tasks_gold = _write_tasks_gold(tmp_path, [
        _row("dw_1", ["A", "B", "C"], PATH["join_keys"], ["k1 is predicated by TABLE.K = 1"]),
        _row("dw_2", ["A", "B", "C"], PATH["join_keys"], ["k2 is predicated by TABLE.K = 2"]),
        _row("dw_3", ["A", "B", "C"], PATH["join_keys"]),
    ])
    output_dir = tmp_path / "exp"

    provenance = build(
        name="exp",
        tasks_gold=tasks_gold,
        output_dir=output_dir,
        arm_notes={"view": "note\n"},
        excluded_tasks={"dw_2": "gold contradicts the question"},
        **PATH,
    )

    manifest = [json.loads(line)["task_id"] for line in (output_dir / "manifest.jsonl").read_text().splitlines()]
    assert manifest == ["dw_1", "dw_3"]
    assert set(_contexts(output_dir / "domain_knowledge_contexts.jsonl")) == {"dw_1"}
    assert set(_contexts(output_dir / "view_contexts.jsonl")) == {"dw_1", "dw_3"}
    assert provenance["task_ids"] == ["dw_1", "dw_3"]
    assert provenance["task_count"] == 2
    assert provenance["excluded_tasks"] == {"dw_2": "gold contradicts the question"}


def test_build_rejects_an_excluded_task_that_is_not_on_the_join_path(tmp_path: Path):
    tasks_gold = _write_tasks_gold(tmp_path, [_row("dw_1", ["A", "B", "C"], PATH["join_keys"])])
    with pytest.raises(ValueError, match="dw_9"):
        build(
            name="exp",
            tasks_gold=tasks_gold,
            output_dir=tmp_path / "exp",
            excluded_tasks={"dw_9": "typo"},
            **PATH,
        )


VIEW_SQL = """-- comment
CREATE OR REPLACE SQL SECURITY DEFINER VIEW av_x AS
SELECT
    a.K,
    b.V AS B_V
FROM A a
JOIN B b ON a.K = b.K;

INSERT INTO av_catalog (object_name, column_name, description) VALUES
('av_x', '*',
 'A joined with B: A.K = B.K.'),
('av_x', 'B_V', 'V of B.');
"""


def test_view_as_sql_note_inlines_the_view_query_as_a_cte_with_its_catalog_notes():
    note = build_join_experiment.view_as_sql_note(VIEW_SQL, view_name="av_x", cte_name="x_rows", instruction="Use x_rows.")

    assert note.startswith("# Join knowledge\nUse x_rows.\n")
    assert "WITH x_rows AS (\nSELECT\n    a.K,\n    b.V AS B_V\nFROM A a\nJOIN B b ON a.K = b.K\n)" in note
    assert "- Whole query: A joined with B: A.K = B.K.\n" in note
    assert "- B_V: V of B.\n" in note
    assert "av_" not in note


def _experiment_arm_notes():
    return EXPERIMENTS["join3_course_number"]["arm_notes"]


def test_join3_excludes_exactly_the_three_tasks_whose_gold_contradicts_the_question():
    assert set(EXPERIMENTS["join3_course_number"]["excluded_tasks"]) == {"dw_356", "dw_1303", "dw_2593"}


def test_join3_join_sql_note_carries_the_view_query_and_every_catalog_description_verbatim():
    view_sql = (HERE / "views" / "join3_course_number.sql").read_text(encoding="utf-8")
    note = _experiment_arm_notes()["join_sql"]
    select_body = view_sql.split("VIEW av_library_offering_course AS\n", 1)[1].split(";", 1)[0]
    assert select_body in note
    descriptions = re.findall(r"\('av_library_offering_course',\s*'([^']*)',\s*'([^']*)'\)", view_sql)
    assert len(descriptions) == 5
    for _, description in descriptions:
        assert description in note


def test_join3_text_arms_never_mention_the_view_or_the_catalog():
    notes = _experiment_arm_notes()
    for arm in ("join_text", "join_sql"):
        assert "av_" not in notes[arm]


def test_join3_join_text_note_states_both_gold_join_conditions_and_the_offering_table():
    note = _experiment_arm_notes()["join_text"]
    assert "LIBRARY_SUBJECT_OFFERED.COURSE_NUMBER = SIS_SUBJECT_CODE.COURSE_NUMBER" in note
    assert "SIS_COURSE_DESCRIPTION.COURSE = SIS_SUBJECT_CODE.COURSE_NUMBER" in note
    assert "SELECT" not in note
