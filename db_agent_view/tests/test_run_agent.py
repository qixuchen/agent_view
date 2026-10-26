import io
import json
from pathlib import Path
import subprocess
import sys
import time

import pytest

from common import ContractError
from run_agent import _prompt, redact_trace_text, run_one_task


def _write_manifest(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "task_id": "smoke_001",
                "question": "How many rows are in the example table?",
                "database": "dw",
                "seed": 0,
            }
        )
        + "\n",
        encoding="utf-8",
    )


def _valid_final() -> dict[str, object]:
    return {
        "status": "answered",
        "result": {"columns": ["row_count"], "rows": [[3]]},
        "answer": "There are 3 rows.",
        "final_sql": "SELECT COUNT(*) AS row_count FROM example",
        "evidence_tool_call_ids": ["mysql_1"],
    }


TRAJECTORY_EXPORT_DIR = "/tmp/c0-output/.openclaw/trajectory-exports/trace"


def _trajectory_events(command: str = 'mysql -e "SELECT COUNT(*) FROM example"') -> str:
    """Event shapes as OpenClaw 2026.8.2 `sessions export-trajectory` writes them."""
    events: list[dict[str, object]] = [
        {"traceSchema": "openclaw-trajectory", "type": "session.started", "seq": 2, "data": {}},
        {
            "traceSchema": "openclaw-trajectory",
            "type": "user.message",
            "seq": 7,
            "data": {"message": {"role": "user", "content": "How many rows?"}},
        },
        {
            "traceSchema": "openclaw-trajectory",
            "type": "assistant.message",
            "seq": 8,
            "data": {
                "message": {
                    "role": "assistant",
                    "content": [
                        {
                            "type": "toolCall",
                            "id": "call_1",
                            "name": "exec",
                            "arguments": {"command": command},
                        }
                    ],
                    "usage": {"input": 100, "output": 20, "totalTokens": 120},
                    "stopReason": "toolUse",
                }
            },
        },
        {
            "traceSchema": "openclaw-trajectory",
            "type": "tool.call",
            "seq": 9,
            "data": {"toolCallId": "call_1", "name": "exec", "arguments": {"command": command}},
        },
        {
            "traceSchema": "openclaw-trajectory",
            "type": "tool.result",
            "seq": 10,
            "data": {
                "message": {
                    "role": "toolResult",
                    "toolCallId": "call_1",
                    "toolName": "exec",
                    "content": [{"type": "text", "text": "3"}],
                    "isError": False,
                }
            },
        },
        {
            "traceSchema": "openclaw-trajectory",
            "type": "model.completed",
            "seq": 13,
            "data": {"timedOut": False, "stopReason": "stop"},
        },
    ]
    return "".join(json.dumps(event) + "\n" for event in events)


def test_prompt_forbids_exposing_database_or_model_credentials():
    prompt = _prompt(
        {
            "task_id": "smoke_001",
            "question": "Count rows.",
            "database": "dw",
            "seed": 0,
        }
    )

    assert "Never inspect, print, write, or return credential values." in prompt
    assert "MYSQL_PWD" in prompt
    assert "OPENCLAW_CUSTOM_API_KEY" in prompt
    assert "test -s /tmp/c0-output/final.json" in prompt


def test_prompt_forbids_stopping_before_the_final_artifact_exists():
    prompt = _prompt(
        {
            "task_id": "smoke_001",
            "question": "Count rows.",
            "database": "dw",
            "seed": 0,
        }
    )

    assert "Do not stop, summarize, or reply with only a plan" in prompt
    assert "Start by running commands" in prompt


def test_prompt_forbids_passing_the_password_as_a_command_line_argument():
    prompt = _prompt(
        {
            "task_id": "smoke_001",
            "question": "Count rows.",
            "database": "dw",
            "seed": 0,
        }
    )

    assert "Do not pass the password as a command-line argument" in prompt
    assert "--password" in prompt
    assert "reads MYSQL_PWD" in prompt


def test_prompt_includes_explicit_task_context_only_when_provided():
    task = {
        "task_id": "smoke_001",
        "question": "Count rows.",
        "database": "dw",
        "seed": 0,
    }

    assert "Task-specific annotation guidance" not in _prompt(task)
    prompt = _prompt(task, task_context="## Task-specific annotation guidance\n- trusted")

    assert "Read /tmp/c0-task/context.md" in prompt
    assert "Treat it as guidance" in prompt
    assert "Task-specific annotation guidance" not in prompt


def test_redact_trace_text_removes_configured_and_environment_secrets():
    trace = (
        'MYSQL_PWD=mysql-secret\n'
        'OPENCLAW_CUSTOM_API_KEY=api-secret\n'
        '{"command":"echo BEAVER_C0_AGENT_PASSWORD=unrecognised-secret"}\n'
    )

    redacted = redact_trace_text(trace, secrets=("mysql-secret", "api-secret"))

    assert "mysql-secret" not in redacted
    assert "api-secret" not in redacted
    assert "unrecognised-secret" not in redacted
    assert "MYSQL_PWD=<redacted>" in redacted
    assert "OPENCLAW_CUSTOM_API_KEY=<redacted>" in redacted


class FakeDocker:
    def __init__(self, final: dict[str, object]) -> None:
        self.final = final
        self.commands: list[list[str]] = []
        self.command_kwargs: list[dict[str, object]] = []
        self.task_package: dict[str, object] | None = None
        self.task_package_path: Path | None = None

    def __call__(self, command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        self.commands.append(command)
        self.command_kwargs.append(dict(kwargs))
        if command[:2] == ["docker", "exec"] and "openclaw agent" in command[-1]:
            return subprocess.CompletedProcess(
                command,
                0,
                stdout=json.dumps(
                    {
                        "status": "ok",
                        "result": {
                            "meta": {
                                "agentMeta": {
                                    "sessionId": "session-abc",
                                    "sessionFile": "agent:main:explicit:session-abc",
                                }
                            }
                        },
                    }
                ),
                stderr="",
            )
        if command[:2] == ["docker", "exec"] and "test -s /tmp/c0-output/final.json" in command[-1]:
            return subprocess.CompletedProcess(command, 0, stdout="ready", stderr="")
        if command[:2] == ["docker", "exec"] and "export-trajectory" in command:
            return subprocess.CompletedProcess(
                command,
                0,
                stdout=json.dumps(
                    {
                        "outputDir": TRAJECTORY_EXPORT_DIR,
                        "sessionId": "chat",
                        "eventCount": 6,
                        "files": ["manifest.json", "events.jsonl"],
                    }
                ),
                stderr="",
            )
        if command[:3] == ["docker", "exec", command[2]] and command[-1] == "/root/.openclaw/openclaw.json":
            return subprocess.CompletedProcess(
                command,
                0,
                stdout=json.dumps(
                    {
                        "models": {
                            "providers": {
                                "custom-api-openlux-ai": {
                                    "models": [{"id": "glm-5.2"}]
                                }
                            }
                        }
                    }
                ),
                stderr="",
            )
        if (
            command[:2] == ["docker", "cp"]
            and command[2].endswith("/.")
            and ":/tmp/c0-output/." not in command[2]
        ):
            task_path = Path(command[2][:-2])
            self.task_package_path = task_path
            self.task_package = json.loads((task_path / "task.json").read_text(encoding="utf-8"))
        if command[:2] == ["docker", "cp"] and command[2].endswith(":/tmp/c0-output/final.json"):
            final_path = Path(command[3])
            final_path.write_text(
                json.dumps(self.final), encoding="utf-8"
            )
        if command[:2] == ["docker", "cp"] and command[2].endswith("/events.jsonl"):
            Path(command[3]).write_text(_trajectory_events(), encoding="utf-8")
        if command[:2] == ["docker", "cp"] and command[2].endswith(":/tmp/c0-output/gateway.log"):
            Path(command[3]).write_text("gateway diagnostic\n", encoding="utf-8")
        return subprocess.CompletedProcess(command, 0, stdout="agent stdout\n", stderr="")


class MissingFinalDocker(FakeDocker):
    def __call__(self, command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        if command[:2] == ["docker", "exec"] and "test -s /tmp/c0-output/final.json" in command[-1]:
            return subprocess.CompletedProcess(command, 0, stdout="", stderr="")
        if command[:2] == ["docker", "cp"] and command[2].endswith(":/tmp/c0-output/final.json"):
            raise subprocess.CalledProcessError(1, command, "", "final artifact missing")
        return super().__call__(command, **kwargs)


class TimeoutDocker(FakeDocker):
    def __call__(self, command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        if command[:2] == ["docker", "exec"] and "openclaw agent" in command[-1]:
            raise subprocess.TimeoutExpired(command, timeout=600, output="partial agent output")
        return super().__call__(command, **kwargs)


class OpenClawTimeoutDocker(FakeDocker):
    def __call__(self, command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        if command[:2] == ["docker", "exec"] and "openclaw agent" in command[-1]:
            self.commands.append(command)
            self.command_kwargs.append(dict(kwargs))
            raise subprocess.CalledProcessError(
                1,
                command,
                output='{"status":"timeout","summary":"aborted","timeoutPhase":"provider"}',
                stderr="",
            )
        return super().__call__(command, **kwargs)


class DelayedFinalDocker(FakeDocker):
    """Report final.json only once the agent has been called enough times."""

    def __init__(self, final: dict[str, object], *, ready_after_calls: int) -> None:
        super().__init__(final)
        self.ready_after_calls = ready_after_calls
        self.agent_calls = 0

    def __call__(self, command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        if command[:2] == ["docker", "exec"] and "openclaw agent" in command[-1]:
            self.agent_calls += 1
        if command[:2] == ["docker", "exec"] and "test -s /tmp/c0-output/final.json" in command[-1]:
            self.commands.append(command)
            self.command_kwargs.append(dict(kwargs))
            ready = "ready" if self.agent_calls >= self.ready_after_calls else ""
            return subprocess.CompletedProcess(command, 0, stdout=ready, stderr="")
        return super().__call__(command, **kwargs)


class UnexportableTraceDocker(FakeDocker):
    """Refuse to export a stored trajectory."""

    def __call__(self, command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        if command[:2] == ["docker", "exec"] and "export-trajectory" in command:
            self.commands.append(command)
            self.command_kwargs.append(dict(kwargs))
            raise subprocess.CalledProcessError(
                1, command, "", "sessions session not found: agent:main:explicit:chat"
            )
        return super().__call__(command, **kwargs)


_TIMING_KEYS = frozenset(
    {
        "agent_calls",
        "agent_wall_seconds",
        "failure_reason",
        "session_trajectory",
        "trajectory_event_count",
        "wall_seconds",
    }
)


def _agent_calls(docker: FakeDocker) -> list[tuple[str, dict[str, object]]]:
    return [
        (command[-1], kwargs)
        for command, kwargs in zip(docker.commands, docker.command_kwargs)
        if command[:2] == ["docker", "exec"] and "openclaw agent" in command[-1]
    ]


class SlowFakeDocker(FakeDocker):
    def __call__(self, command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        if command[:2] == ["docker", "exec"] and "openclaw agent" in command[-1]:
            time.sleep(0.03)
        return super().__call__(command, **kwargs)


def test_run_one_task_uses_only_manifest_and_writes_valid_agent_artifacts(
    tmp_path: Path,
) -> None:
    manifest_path = tmp_path / "manifest.jsonl"
    _write_manifest(manifest_path)
    docker = FakeDocker(_valid_final())

    artifacts = run_one_task(
        manifest_path=manifest_path,
        run_root=tmp_path / "runs" / "run_001",
        task_id="smoke_001",
        seed=0,
        image="beaver-c0-agent:test",
        mysql_host="beaver-c0-mysql",
        mysql_port=3306,
        mysql_user="beaver_agent",
        mysql_password="agent-secret",
        custom_base_url="https://api.openlux.ai/v1",
        custom_api_key="model-secret",
        model="glm-5.2",
        gateway_port=3333,
        docker_runner=docker,
        gateway_ready_seconds=0,
    )

    assert docker.task_package == {
        "task_id": "smoke_001",
        "question": "How many rows are in the example table?",
        "database": "dw",
        "seed": 0,
    }
    assert docker.task_package_path is not None
    assert docker.task_package_path.parent == artifacts.task_root
    assert not docker.task_package_path.exists()
    assert json.loads(artifacts.final_path.read_text(encoding="utf-8")) == _valid_final()
    assert json.loads(artifacts.stdout_path.read_text(encoding="utf-8").splitlines()[0])["status"] == "ok"
    metadata = json.loads(artifacts.metadata_path.read_text(encoding="utf-8"))
    assert {key: metadata[key] for key in sorted(metadata) if key not in _TIMING_KEYS} == {
        "database": "dw",
        "image": "beaver-c0-agent:test",
        "mysql_host": "beaver-c0-mysql",
        "mysql_port": 3306,
        "mysql_user": "beaver_agent",
        "model_context_window": 1_000_000,
        "model_max_tokens": 32_768,
        "seed": 0,
        "task_id": "smoke_001",
    }
    assert metadata["session_trajectory"] == "exported"
    flattened_commands = "\n".join(" ".join(command) for command in docker.commands)
    assert "--network" in flattened_commands
    assert "beaver-c0-mysql" in flattened_commands
    assert "dw_filtered.parquet" not in flattened_commands
    assert "audit" not in flattened_commands
    assert "--network beaver-c0-net" in flattened_commands
    assert "openclaw onboard" in flattened_commands
    assert "--workspace /tmp/c0-task" in flattened_commands
    assert "--custom-base-url https://api.openlux.ai/v1" in flattened_commands
    assert 'openclaw config set models.providers["custom-api-openlux-ai"].models[0].contextWindow 1000000 --strict-json' in flattened_commands
    assert 'openclaw config set models.providers["custom-api-openlux-ai"].models[0].maxTokens 32768 --strict-json' in flattened_commands
    assert "openclaw config set agents.defaults.timeoutSeconds 600 --strict-json" in flattened_commands
    assert "openclaw gateway run --bind loopback --port 3333" in flattened_commands
    assert "openclaw models set custom-api-openlux-ai/glm-5.2" in flattened_commands
    assert "openclaw agent --agent main --session-id chat --timeout 600 --json" in flattened_commands
    agent_index = next(
        index
        for index, command in enumerate(docker.commands)
        if command[:2] == ["docker", "exec"] and "openclaw agent" in command[-1]
    )
    assert docker.command_kwargs[agent_index]["timeout"] == 600
    assert "test -s /tmp/c0-output/final.json" in flattened_commands
    assert "openclaw transcripts" not in flattened_commands
    assert any(command[:3] == ["docker", "rm", "--force"] for command in docker.commands)


def test_run_one_task_reports_task_start_and_periodic_heartbeat(tmp_path: Path):
    manifest_path = tmp_path / "manifest.jsonl"
    _write_manifest(manifest_path)
    progress = io.StringIO()

    run_one_task(
        manifest_path=manifest_path,
        run_root=tmp_path / "runs" / "run_001",
        task_id="smoke_001",
        seed=0,
        image="beaver-c0-agent:test",
        mysql_host="beaver-c0-mysql",
        mysql_port=3306,
        mysql_user="beaver_agent",
        mysql_password="agent-secret",
        custom_base_url="https://api.openlux.ai/v1",
        custom_api_key="model-secret",
        model="glm-5.2",
        docker_runner=SlowFakeDocker(_valid_final()),
        gateway_ready_seconds=0,
        heartbeat_seconds=0.01,
        progress_stream=progress,
    )

    assert "Starting task smoke_001 (seed=0)" in progress.getvalue()
    assert "Still running task smoke_001" in progress.getvalue()


def test_run_one_task_rejects_invalid_agent_final_but_always_removes_container(
    tmp_path: Path,
) -> None:
    manifest_path = tmp_path / "manifest.jsonl"
    _write_manifest(manifest_path)
    docker = FakeDocker({**_valid_final(), "final_sql": ""})

    with pytest.raises(ContractError, match="final_sql"):
        run_one_task(
            manifest_path=manifest_path,
            run_root=tmp_path / "runs" / "run_001",
            task_id="smoke_001",
            seed=0,
            image="beaver-c0-agent:test",
            mysql_host="beaver-c0-mysql",
            mysql_port=3306,
            mysql_user="beaver_agent",
            mysql_password="agent-secret",
            custom_base_url="https://api.openlux.ai/v1",
            custom_api_key="model-secret",
            model="glm-5.2",
            docker_runner=docker,
            gateway_ready_seconds=0,
        )

    assert any(command[:3] == ["docker", "rm", "--force"] for command in docker.commands)


def test_run_one_task_writes_terminal_failure_when_final_is_missing(
    tmp_path: Path,
) -> None:
    manifest_path = tmp_path / "manifest.jsonl"
    _write_manifest(manifest_path)
    docker = MissingFinalDocker(_valid_final())
    run_root = tmp_path / "runs" / "run_001"

    artifacts = run_one_task(
        manifest_path=manifest_path,
        run_root=run_root,
        task_id="smoke_001",
        seed=0,
        image="beaver-c0-agent:test",
        mysql_host="beaver-c0-mysql",
        mysql_port=3306,
        mysql_user="beaver_agent",
        mysql_password="agent-secret",
        custom_base_url="https://api.openlux.ai/v1",
        custom_api_key="model-secret",
        model="glm-5.2",
        docker_runner=docker,
        gateway_ready_seconds=0,
        agent_timeout_seconds=1,
        max_agent_continuations=0,
    )

    task_root = run_root / "tasks" / "smoke_001" / "0"
    assert artifacts.final_path == task_root / "final.json"
    assert json.loads(artifacts.final_path.read_text(encoding="utf-8")) == {
        "status": "failed",
        "failure_reason": "final_artifact_not_written",
    }
    assert len(_agent_calls(docker)) == 1
    assert any(
        json.loads(line)["type"] == "tool.result"
        for line in (task_root / "agent_trace.jsonl").read_text(encoding="utf-8").splitlines()
    )
    assert (task_root / "gateway.log").read_text(encoding="utf-8") == "gateway diagnostic\n"


def test_run_one_task_continues_same_session_until_final_json_exists(tmp_path: Path) -> None:
    manifest_path = tmp_path / "manifest.jsonl"
    _write_manifest(manifest_path)
    docker = DelayedFinalDocker(_valid_final(), ready_after_calls=2)

    artifacts = run_one_task(
        manifest_path=manifest_path,
        run_root=tmp_path / "runs" / "run_001",
        task_id="smoke_001",
        seed=0,
        image="beaver-c0-agent:test",
        mysql_host="beaver-c0-mysql",
        mysql_port=3306,
        mysql_user="beaver_agent",
        mysql_password="agent-secret",
        custom_base_url="https://api.openlux.ai/v1",
        custom_api_key="model-secret",
        model="glm-5.2",
        docker_runner=docker,
        gateway_ready_seconds=0,
    )

    calls = _agent_calls(docker)
    assert len(calls) == 2
    assert "/tmp/c0-task/prompt.md" in calls[0][0]
    assert "/tmp/c0-output/final.json" in calls[1][0]
    assert all("--session-id chat" in command for command, _ in calls)
    assert all(0 < float(kwargs["timeout"]) <= 600 for _, kwargs in calls)
    assert json.loads(artifacts.final_path.read_text(encoding="utf-8")) == _valid_final()


def test_run_one_task_stops_after_the_agent_continuation_safety_cap(tmp_path: Path) -> None:
    manifest_path = tmp_path / "manifest.jsonl"
    _write_manifest(manifest_path)
    docker = DelayedFinalDocker(_valid_final(), ready_after_calls=99)

    artifacts = run_one_task(
        manifest_path=manifest_path,
        run_root=tmp_path / "runs" / "run_001",
        task_id="smoke_001",
        seed=0,
        image="beaver-c0-agent:test",
        mysql_host="beaver-c0-mysql",
        mysql_port=3306,
        mysql_user="beaver_agent",
        mysql_password="agent-secret",
        custom_base_url="https://api.openlux.ai/v1",
        custom_api_key="model-secret",
        model="glm-5.2",
        docker_runner=docker,
        gateway_ready_seconds=0,
        agent_timeout_seconds=600,
        max_agent_continuations=2,
    )

    assert len(_agent_calls(docker)) == 3
    assert json.loads(artifacts.final_path.read_text(encoding="utf-8")) == {
        "status": "failed",
        "failure_reason": "final_artifact_not_written",
    }


def test_run_one_task_writes_terminal_failure_when_agent_times_out(tmp_path: Path) -> None:
    manifest_path = tmp_path / "manifest.jsonl"
    _write_manifest(manifest_path)
    run_root = tmp_path / "runs" / "run_001"

    artifacts = run_one_task(
        manifest_path=manifest_path,
        run_root=run_root,
        task_id="smoke_001",
        seed=0,
        image="beaver-c0-agent:test",
        mysql_host="beaver-c0-mysql",
        mysql_port=3306,
        mysql_user="beaver_agent",
        mysql_password="agent-secret",
        custom_base_url="https://api.openlux.ai/v1",
        custom_api_key="model-secret",
        model="glm-5.2",
        docker_runner=TimeoutDocker(_valid_final()),
        gateway_ready_seconds=0,
    )

    assert json.loads(artifacts.final_path.read_text(encoding="utf-8")) == {
        "status": "failed",
        "failure_reason": "agent_timeout",
    }
    assert "partial agent output" in artifacts.stdout_path.read_text(encoding="utf-8")


def _run_smoke_task(tmp_path: Path, docker: FakeDocker, **overrides: object):
    manifest_path = tmp_path / "manifest.jsonl"
    _write_manifest(manifest_path)
    kwargs: dict[str, object] = {
        "manifest_path": manifest_path,
        "run_root": tmp_path / "runs" / "run_001",
        "task_id": "smoke_001",
        "seed": 0,
        "image": "beaver-c0-agent:test",
        "mysql_host": "beaver-c0-mysql",
        "mysql_port": 3306,
        "mysql_user": "beaver_agent",
        "mysql_password": "agent-secret",
        "custom_base_url": "https://api.openlux.ai/v1",
        "custom_api_key": "model-secret",
        "model": "glm-5.2",
        "docker_runner": docker,
        "gateway_ready_seconds": 0,
    }
    kwargs.update(overrides)
    return run_one_task(**kwargs)


def test_run_one_task_records_per_task_timing_and_no_failure_reason_on_success(
    tmp_path: Path,
) -> None:
    artifacts = _run_smoke_task(tmp_path, SlowFakeDocker(_valid_final()))

    metadata = json.loads(artifacts.metadata_path.read_text(encoding="utf-8"))
    assert metadata["failure_reason"] is None
    assert metadata["agent_calls"] == 1
    assert metadata["agent_wall_seconds"] >= 0.03
    assert metadata["wall_seconds"] >= metadata["agent_wall_seconds"]
    assert metadata["task_id"] == "smoke_001"


def test_run_one_task_records_timing_and_failure_reason_when_the_agent_times_out(
    tmp_path: Path,
) -> None:
    artifacts = _run_smoke_task(
        tmp_path, TimeoutDocker(_valid_final()), agent_timeout_seconds=600
    )

    metadata = json.loads(artifacts.metadata_path.read_text(encoding="utf-8"))
    assert metadata["failure_reason"] == "agent_timeout"
    assert metadata["agent_calls"] == 1
    assert isinstance(metadata["agent_wall_seconds"], float)


def _trace_lines(artifacts) -> list[dict[str, object]]:
    text = artifacts.trace_path.read_text(encoding="utf-8")
    return [json.loads(line) for line in text.splitlines() if line.strip()]


def test_run_one_task_saves_the_step_by_step_execution_trace_on_success(
    tmp_path: Path,
) -> None:
    artifacts = _run_smoke_task(tmp_path, FakeDocker(_valid_final()))

    events = _trace_lines(artifacts)
    assistant = next(event for event in events if event["type"] == "assistant.message")
    result = next(event for event in events if event["type"] == "tool.result")
    assert assistant["data"]["message"]["content"][0]["name"] == "exec"
    assert result["data"]["message"]["role"] == "toolResult"
    assert artifacts.trace_path.read_text(encoding="utf-8") != artifacts.stdout_path.read_text(
        encoding="utf-8"
    )
    assert json.loads(artifacts.stdout_path.read_text(encoding="utf-8").splitlines()[0])["status"] == "ok"
    metadata = json.loads(artifacts.metadata_path.read_text(encoding="utf-8"))
    assert metadata["session_trajectory"] == "exported"
    assert metadata["trajectory_event_count"] == 6


def test_run_one_task_saves_the_execution_trace_when_the_agent_times_out(
    tmp_path: Path,
) -> None:
    artifacts = _run_smoke_task(tmp_path, TimeoutDocker(_valid_final()))

    assert json.loads(artifacts.final_path.read_text(encoding="utf-8"))["failure_reason"] == (
        "agent_timeout"
    )
    assert any(event["type"] == "tool.result" for event in _trace_lines(artifacts))
    metadata = json.loads(artifacts.metadata_path.read_text(encoding="utf-8"))
    assert metadata["session_trajectory"] == "exported"


def test_run_one_task_saves_the_execution_trace_when_the_final_response_is_invalid(
    tmp_path: Path,
) -> None:
    manifest_path = tmp_path / "manifest.jsonl"
    _write_manifest(manifest_path)
    run_root = tmp_path / "runs" / "run_001"

    with pytest.raises(ContractError):
        _run_smoke_task(
            tmp_path,
            FakeDocker({**_valid_final(), "final_sql": ""}),
            run_root=run_root,
        )

    trace = (run_root / "tasks" / "smoke_001" / "0" / "agent_trace.jsonl").read_text(
        encoding="utf-8"
    )
    assert any(json.loads(line)["type"] == "tool.result" for line in trace.splitlines())


def test_run_one_task_exports_the_trace_from_a_deterministic_session_and_path(
    tmp_path: Path,
) -> None:
    docker = FakeDocker(_valid_final())

    _run_smoke_task(tmp_path, docker)

    export = next(command for command in docker.commands if "export-trajectory" in command)
    assert export[:2] == ["docker", "exec"]
    for flag, value in (
        ("--session-key", "agent:main:explicit:chat"),
        ("--agent", "main"),
        ("--workspace", "/tmp/c0-output"),
        ("--output", "trace"),
    ):
        assert export[export.index(flag) + 1] == value
    assert "--json" in export
    copied = next(
        command
        for command in docker.commands
        if command[:2] == ["docker", "cp"] and command[2].endswith("/events.jsonl")
    )
    assert copied[2].endswith(f"{TRAJECTORY_EXPORT_DIR}/events.jsonl")


def test_run_one_task_exports_the_trace_before_removing_the_container(tmp_path: Path) -> None:
    docker = FakeDocker(_valid_final())

    _run_smoke_task(tmp_path, docker)

    export_index = next(
        index for index, command in enumerate(docker.commands) if "export-trajectory" in command
    )
    remove_index = next(
        index for index, command in enumerate(docker.commands) if command[:3] == ["docker", "rm", "--force"]
    )
    assert export_index < remove_index


def test_run_one_task_records_an_unavailable_trace_without_failing_the_task(
    tmp_path: Path,
) -> None:
    artifacts = _run_smoke_task(tmp_path, UnexportableTraceDocker(_valid_final()))

    assert artifacts.trace_path.read_text(encoding="utf-8") == ""
    assert json.loads(artifacts.final_path.read_text(encoding="utf-8")) == _valid_final()
    metadata = json.loads(artifacts.metadata_path.read_text(encoding="utf-8"))
    assert metadata["session_trajectory"] == "unavailable"


def test_run_one_task_redacts_secrets_from_the_saved_trace(tmp_path: Path) -> None:
    class LeakyTraceDocker(FakeDocker):
        def __call__(self, command: list[str], **kwargs: object):
            if command[:2] == ["docker", "cp"] and command[2].endswith("/events.jsonl"):
                self.commands.append(command)
                self.command_kwargs.append(dict(kwargs))
                Path(command[3]).write_text(
                    _trajectory_events("MYSQL_PWD=agent-secret mysql -e 'SELECT 1'"),
                    encoding="utf-8",
                )
                return subprocess.CompletedProcess(command, 0, stdout="", stderr="")
            return super().__call__(command, **kwargs)

    artifacts = _run_smoke_task(tmp_path, LeakyTraceDocker(_valid_final()))

    trace = artifacts.trace_path.read_text(encoding="utf-8")
    assert "agent-secret" not in trace
    assert "MYSQL_PWD=<redacted>" in trace


def test_run_one_task_converts_openclaw_timeout_exit_to_terminal_failure(tmp_path: Path) -> None:
    manifest_path = tmp_path / "manifest.jsonl"
    _write_manifest(manifest_path)
    run_root = tmp_path / "runs" / "run_001"
    docker = OpenClawTimeoutDocker(_valid_final())

    artifacts = run_one_task(
        manifest_path=manifest_path,
        run_root=run_root,
        task_id="smoke_001",
        seed=0,
        image="beaver-c0-agent:test",
        mysql_host="beaver-c0-mysql",
        mysql_port=3306,
        mysql_user="beaver_agent",
        mysql_password="agent-secret",
        custom_base_url="https://api.openlux.ai/v1",
        custom_api_key="model-secret",
        model="glm-5.2",
        docker_runner=docker,
        gateway_ready_seconds=0,
    )

    assert json.loads(artifacts.final_path.read_text(encoding="utf-8")) == {
        "status": "failed",
        "failure_reason": "agent_timeout",
    }
    agent_index = next(
        index
        for index, command in enumerate(docker.commands)
        if command[:2] == ["docker", "exec"] and "openclaw agent" in command[-1]
    )
    assert docker.command_kwargs[agent_index]["timeout"] == 600
