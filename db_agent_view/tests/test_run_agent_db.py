import configparser
import json
import stat
import subprocess
from pathlib import Path

import pytest

import run_agent
from common import ContractError
from run_agent import _prompt, build_parser, redact_trace_text, run_one_task
from test_run_agent import FakeDocker, _valid_final


def _run_db_agent_view_task(
    tmp_path: Path, task_context: str | None = None, **run_kwargs
) -> FakeDocker:
    manifest_path = tmp_path / "manifest.jsonl"
    manifest_path.write_text(
        json.dumps(
            {"task_id": "dw_6", "question": "How many rows?", "database": "db_agent_view", "seed": 0}
        )
        + "\n",
        encoding="utf-8",
    )
    docker = FakeDocker(_valid_final())
    run_one_task(
        manifest_path=manifest_path,
        run_root=tmp_path / "run",
        task_id="dw_6",
        seed=0,
        image="beaver-c0-agent:test",
        mysql_host="beaver-c0-mysql",
        mysql_port=3306,
        mysql_user="agent_view_agent",
        mysql_password="agent-secret",
        custom_base_url="https://api.openlux.ai/v1",
        custom_api_key="model-secret",
        model="glm-5.2",
        docker_runner=docker,
        gateway_ready_seconds=0,
        task_context=task_context,
        **run_kwargs,
    )
    return docker


def test_prompt_restricts_agent_to_the_task_database():
    prompt = _prompt(
        {"task_id": "dw_6", "question": "Count rows.", "database": "db_agent_view", "seed": 0}
    )

    assert "All tables you need are in the `db_agent_view` database." in prompt
    assert "Do not query other databases." in prompt


def test_run_one_task_sets_container_database_from_the_manifest(tmp_path: Path) -> None:
    docker = _run_db_agent_view_task(tmp_path)

    create = next(command for command in docker.commands if command[:2] == ["docker", "create"])
    assert "MYSQL_DATABASE=db_agent_view" in create
    assert "MYSQL_DATABASE=dw" not in create


def test_run_one_task_configures_utf8mb4_mysql_client_before_the_agent_runs(
    tmp_path: Path,
) -> None:
    docker = _run_db_agent_view_task(tmp_path)

    flattened = [" ".join(command) for command in docker.commands]
    config_index = next(
        index
        for index, command in enumerate(flattened)
        if "/root/.my.cnf" in command and "default-character-set=utf8mb4" in command
    )
    agent_index = next(index for index, command in enumerate(flattened) if "openclaw agent" in command)
    assert config_index < agent_index


def test_mysql_client_config_connects_as_the_agent_account_and_is_not_world_writable(
    tmp_path: Path,
) -> None:
    docker = _run_db_agent_view_task(tmp_path)
    config_command = next(
        command[-1] for command in docker.commands if "/root/.my.cnf" in command[-1]
    )
    config_path = tmp_path / "my.cnf"

    subprocess.run(
        ["/bin/bash", "-c", config_command.replace("/root/.my.cnf", str(config_path))],
        check=True,
    )

    assert stat.S_IMODE(config_path.stat().st_mode) == 0o600
    parser = configparser.ConfigParser()
    parser.read(config_path)
    assert dict(parser["client"]) == {
        "user": "agent_view_agent",
        "host": "beaver-c0-mysql",
        "port": "3306",
        "default-character-set": "utf8mb4",
    }
    assert dict(parser["mysql"]) == {"database": "db_agent_view"}
    assert "agent-secret" not in config_command


def test_redact_trace_text_removes_the_agent_view_password_assignment():
    redacted = redact_trace_text("AGENT_VIEW_AGENT_PASSWORD=abc123", secrets=())

    assert "abc123" not in redacted


def test_cli_defaults_to_the_db_agent_view_agent_account(monkeypatch) -> None:
    monkeypatch.setenv("AGENT_VIEW_AGENT_PASSWORD", "from-env")
    args = build_parser().parse_args(["--run-root", "runs/x"])

    assert args.mysql_user == "agent_view_agent"
    assert args.mysql_password == "from-env"
    assert args.manifest_path.name == "manifest.jsonl"
    assert not hasattr(args, "condition_manifest")


def _write_contexts(path: Path, records) -> Path:
    path.write_text("".join(json.dumps(record) + "\n" for record in records), encoding="utf-8")
    return path


def test_load_task_contexts_maps_task_ids_to_context_text(tmp_path: Path) -> None:
    path = _write_contexts(tmp_path / "contexts.jsonl", [{"task_id": "dw_1", "context": "# DK\n- a\n"}])

    assert run_agent.load_task_contexts(path, task_ids={"dw_1", "dw_2"}) == {"dw_1": "# DK\n- a\n"}


def test_load_task_contexts_rejects_tasks_missing_from_the_manifest(tmp_path: Path) -> None:
    path = _write_contexts(tmp_path / "contexts.jsonl", [{"task_id": "dw_9", "context": "x"}])

    with pytest.raises(ContractError, match="dw_9"):
        run_agent.load_task_contexts(path, task_ids={"dw_1"})


def test_load_task_contexts_rejects_duplicate_tasks(tmp_path: Path) -> None:
    path = _write_contexts(
        tmp_path / "contexts.jsonl",
        [{"task_id": "dw_1", "context": "x"}, {"task_id": "dw_1", "context": "y"}],
    )

    with pytest.raises(ContractError, match="dw_1"):
        run_agent.load_task_contexts(path, task_ids={"dw_1"})


def test_run_one_task_keeps_the_injected_context_with_the_task_logs(tmp_path: Path) -> None:
    _run_db_agent_view_task(tmp_path, task_context="# DK\n- injected\n")

    task_root = tmp_path / "run" / "tasks" / "dw_6" / "0"
    assert (task_root / "context.md").read_text(encoding="utf-8") == "# DK\n- injected\n"
    assert json.loads((task_root / "run_metadata.json").read_text())["task_context"] is True


def test_run_one_task_without_context_records_none(tmp_path: Path) -> None:
    _run_db_agent_view_task(tmp_path)

    task_root = tmp_path / "run" / "tasks" / "dw_6" / "0"
    assert not (task_root / "context.md").exists()
    assert json.loads((task_root / "run_metadata.json").read_text())["task_context"] is False


def test_cli_context_path_injects_contexts_into_the_batch(tmp_path: Path, monkeypatch) -> None:
    manifest = tmp_path / "manifest.jsonl"
    manifest.write_text(
        "".join(
            json.dumps({"task_id": task_id, "question": "q", "database": "db_agent_view", "seed": 0}) + "\n"
            for task_id in ("dw_1", "dw_2")
        ),
        encoding="utf-8",
    )
    contexts = _write_contexts(tmp_path / "contexts.jsonl", [{"task_id": "dw_1", "context": "# DK\n"}])
    captured = {}

    def fake_run_manifest(**kwargs):
        captured.update(kwargs)
        return {
            "task_count": 2, "ok_count": 0, "failed_count": 0, "ran_count": 0, "skipped_count": 0,
            "pending_task_ids": [], "complete": True, "stopped_early": False,
        }

    monkeypatch.setattr(run_agent, "run_manifest", fake_run_manifest)
    run_root = tmp_path / "run"
    run_agent.main([
        "--manifest-path", str(manifest), "--run-root", str(run_root), "--mysql-password", "pw",
        "--context-path", str(contexts), "--skip-environment-preflight",
    ])

    assert captured["task_contexts"] == {"dw_1": "# DK\n"}
    record = json.loads((run_root / "task_contexts.json").read_text())
    assert record["context_path"] == str(contexts)
    assert record["task_ids"] == ["dw_1"]
    assert len(record["sha256"]) == 64


def _agent_commands(docker: FakeDocker) -> list[str]:
    return [" ".join(command) for command in docker.commands if "openclaw agent" in " ".join(command)]


def test_run_one_task_marks_the_custom_model_as_reasoning_with_reasoning_effort(tmp_path: Path) -> None:
    docker = _run_db_agent_view_task(tmp_path)

    flattened = [" ".join(command) for command in docker.commands]
    model_path = 'models.providers["custom-api-openlux-ai"].models[0]'

    def position(suffix: str) -> int:
        return next(index for index, command in enumerate(flattened) if command.endswith(suffix))

    reasoning = position(f"openclaw config set {model_path}.reasoning true --strict-json")
    effort = position(f"openclaw config set {model_path}.compat.supportsReasoningEffort true --strict-json")
    first_agent = next(index for index, command in enumerate(flattened) if "openclaw agent" in command)
    assert max(reasoning, effort) < first_agent


def test_run_one_task_defaults_to_medium_thinking(tmp_path: Path) -> None:
    docker = _run_db_agent_view_task(tmp_path)

    assert all("--thinking medium " in command for command in _agent_commands(docker))
    metadata = json.loads((tmp_path / "run" / "tasks" / "dw_6" / "0" / "run_metadata.json").read_text())
    assert metadata["thinking"] == "medium"


def test_run_one_task_passes_the_requested_thinking_level(tmp_path: Path) -> None:
    docker = _run_db_agent_view_task(tmp_path, thinking="high")

    assert all("--thinking high " in command for command in _agent_commands(docker))
    metadata = json.loads((tmp_path / "run" / "tasks" / "dw_6" / "0" / "run_metadata.json").read_text())
    assert metadata["thinking"] == "high"


def test_run_one_task_rejects_unknown_thinking_levels(tmp_path: Path) -> None:
    with pytest.raises(ContractError, match="thinking"):
        _run_db_agent_view_task(tmp_path, thinking="extreme")


def test_cli_thinking_reaches_the_batch(tmp_path: Path, monkeypatch) -> None:
    manifest = tmp_path / "manifest.jsonl"
    manifest.write_text(
        json.dumps({"task_id": "dw_1", "question": "q", "database": "db_agent_view", "seed": 0}) + "\n",
        encoding="utf-8",
    )
    captured = {}

    def fake_run_manifest(**kwargs):
        captured.update(kwargs)
        return {
            "task_count": 1, "ok_count": 0, "failed_count": 0, "ran_count": 0, "skipped_count": 0,
            "pending_task_ids": [], "complete": True, "stopped_early": False,
        }

    monkeypatch.setattr(run_agent, "run_manifest", fake_run_manifest)
    base = ["--manifest-path", str(manifest), "--run-root", str(tmp_path / "run"),
            "--mysql-password", "pw", "--skip-environment-preflight"]
    run_agent.main(base)
    assert captured["thinking"] == "medium"
    run_agent.main([*base, "--thinking", "low"])
    assert captured["thinking"] == "low"
