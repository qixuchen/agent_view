import json
from pathlib import Path

from run_agent import _prompt, build_parser, redact_trace_text, run_one_task
from test_run_agent import FakeDocker, _valid_final


def _run_db_agent_view_task(tmp_path: Path) -> FakeDocker:
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
