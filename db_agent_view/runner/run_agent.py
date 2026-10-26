#!/usr/bin/env python3
"""Run agent-safe db_agent_view tasks, each in a disposable Docker container."""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterator, Mapping, Sequence, TextIO

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import ContractError, validate_final_response  # noqa: E402


DockerRunner = Callable[..., subprocess.CompletedProcess[str]]
DEFAULT_NETWORK = "beaver-c0-net"
DEFAULT_MANIFEST = Path(__file__).resolve().parents[1] / "data" / "manifest.jsonl"
DEFAULT_GATEWAY_PORT = 3333
DEFAULT_AGENT_TIMEOUT_SECONDS = 600
DEFAULT_MAX_AGENT_CONTINUATIONS = 24
AGENT_NAME = "main"
AGENT_SESSION_ID = "chat"
AGENT_SESSION_KEY = f"agent:{AGENT_NAME}:explicit:{AGENT_SESSION_ID}"
TRAJECTORY_WORKSPACE = "/tmp/c0-output"
TRAJECTORY_OUTPUT_NAME = "trace"
DEFAULT_CUSTOM_CONTEXT_WINDOW = 1_000_000
DEFAULT_CUSTOM_MAX_TOKENS = 32_768
SENSITIVE_ENV_NAMES = (
    "MYSQL_PWD",
    "OPENCLAW_CUSTOM_API_KEY",
    "OPENROUTER_API_KEY",
    "BEAVER_C0_AGENT_PASSWORD",
    "AGENT_VIEW_AGENT_PASSWORD",
    "BEAVER_C0_EVALUATOR_PASSWORD",
    "BEAVER_C0_MYSQL_ROOT_PASSWORD",
)
_SENSITIVE_ASSIGNMENT = re.compile(
    rf"(?P<name>{'|'.join(SENSITIVE_ENV_NAMES)})\s*=\s*(?P<value>[^\s\"'\\]+)"
)
COST_BUDGET_KEYS = (
    "turns",
    "exec_calls",
    "db_statements",
    "input_tokens",
    "output_tokens",
    "total_tokens",
    "wall_seconds",
    "result_bytes",
)


class DockerCommandError(RuntimeError):
    """Docker command failure with its captured diagnostic output."""

    def __init__(self, message: str, *, detail: str) -> None:
        super().__init__(message)
        self.detail = detail


@dataclass(frozen=True)
class TaskArtifacts:
    """Paths to the persisted agent-visible artifacts for one execution."""

    task_root: Path
    trace_path: Path
    stdout_path: Path
    gateway_path: Path
    final_path: Path
    metadata_path: Path


def _read_manifest_entry(manifest_path: Path, task_id: str, seed: int) -> dict[str, Any]:
    matches: list[dict[str, Any]] = []
    with manifest_path.open(encoding="utf-8") as manifest_file:
        for line_number, line in enumerate(manifest_file, start=1):
            try:
                row = json.loads(line)
            except json.JSONDecodeError as error:
                raise ContractError(f"Invalid manifest JSON on line {line_number}") from error
            if not isinstance(row, dict):
                raise ContractError(f"Manifest line {line_number} must be an object")
            if row.get("task_id") == task_id and row.get("seed") == seed:
                required_fields = {"task_id", "question", "database", "seed"}
                if set(row) != required_fields:
                    raise ContractError("Manifest entry contains non-agent-safe fields")
                if not all(
                    isinstance(row[field], str) and row[field].strip()
                    for field in ("task_id", "question", "database")
                ) or not isinstance(row["seed"], int) or isinstance(row["seed"], bool):
                    raise ContractError("Manifest entry has an invalid agent-safe field")
                matches.append(row)

    if len(matches) != 1:
        raise ContractError(
            f"Expected exactly one manifest entry for task_id={task_id!r}, seed={seed}"
        )
    return matches[0]


def _read_manifest_entries(manifest_path: Path) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    with manifest_path.open(encoding="utf-8") as manifest_file:
        for line_number, line in enumerate(manifest_file, start=1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as error:
                raise ContractError(f"Invalid manifest JSON on line {line_number}") from error
            if not isinstance(row, dict):
                raise ContractError(f"Manifest line {line_number} must be an object")
            required_fields = {"task_id", "question", "database", "seed"}
            if set(row) != required_fields:
                raise ContractError("Manifest entry contains non-agent-safe fields")
            if not all(
                isinstance(row[field], str) and row[field].strip()
                for field in ("task_id", "question", "database")
            ) or not isinstance(row["seed"], int) or isinstance(row["seed"], bool):
                raise ContractError("Manifest entry has an invalid agent-safe field")
            entries.append(row)
    if not entries:
        raise ContractError("Manifest is empty")
    return entries


_REDACTED_COMMAND_PLACEHOLDERS = frozenset(
    {
        "[malformed diagnostic json redacted]",
        "[oversized diagnostic json redacted]",
    }
)


def _trace_message(event: Any) -> dict[str, Any] | None:
    """Return the chat message a trace line carries, if it carries one.

    Exported trajectories nest the message under ``data``; the flat
    ``{"message": ...}`` shape stays supported for previously captured traces.
    """
    if not isinstance(event, dict):
        return None
    message = event.get("message")
    if isinstance(message, dict):
        return message
    data = event.get("data")
    if isinstance(data, dict) and isinstance(data.get("message"), dict):
        return data["message"]
    return None


def _envelope_usage(envelope_text: str) -> dict[str, int] | None:
    """Read the run-level token usage an `openclaw agent --json` reply reports."""
    for line in envelope_text.splitlines():
        if not line.strip():
            continue
        try:
            envelope = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(envelope, dict):
            continue
        meta = ((envelope.get("result") or {}).get("meta") or {}).get("agentMeta") or {}
        usage = meta.get("usage") if isinstance(meta, dict) else None
        if not isinstance(usage, dict):
            continue
        input_tokens = int(usage.get("input") or 0)
        output_tokens = int(usage.get("output") or 0)
        total_tokens = int(usage.get("totalTokens") or input_tokens + output_tokens)
        if total_tokens or input_tokens or output_tokens:
            return {
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "total_tokens": total_tokens,
            }
    return None


def collect_task_costs(
    *,
    trace_text: str,
    final_text: str,
    wall_seconds: float,
    envelope_text: str = "",
    timed_out: bool = False,
    malformed_final_json: bool = False,
) -> dict[str, Any]:
    """Summarize observable runner costs from one trace.

    Database statements are counted only for MySQL CLI calls: semicolon-
    separated statements passed through ``mysql -e`` are counted individually;
    other MySQL invocations count as one because their SQL is not observable.

    OpenClaw replaces a whole command string with a placeholder when the string
    holds a bracket group that is not valid JSON, or when it exceeds its
    diagnostic length cap. Those calls are counted in
    ``redacted_tool_commands`` so that a low ``db_statements`` reads as
    unobservable rather than as an agent that never queried the database.
    """
    turns = 0
    exec_calls = 0
    db_statements = 0
    input_tokens = 0
    output_tokens = 0
    total_tokens = 0
    sql_errors = 0
    unparsable_trace_lines = 0
    redacted_tool_commands = 0
    for line in trace_text.splitlines():
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            unparsable_trace_lines += 1
            continue
        if isinstance(event, dict) and isinstance(event.get("result"), dict):
            result = event["result"]
            meta = result.get("meta")
            if isinstance(meta, dict):
                agent_meta = meta.get("agentMeta")
                if isinstance(agent_meta, dict):
                    turns += int(agent_meta.get("assistantTurns") or 0)
            tool_summary = result.get("toolSummary")
            if isinstance(tool_summary, dict) and "exec" in (tool_summary.get("tools") or []):
                exec_calls += int(tool_summary.get("calls") or 0)
        message = _trace_message(event)
        if message is None:
            continue
        content = message.get("content") or []
        if not isinstance(content, list):
            content = []
        if message.get("role") == "assistant":
            turns += 1
            usage = message.get("usage") or {}
            if isinstance(usage, dict):
                input_value = int(usage.get("input") or usage.get("inputTokens") or 0)
                output_value = int(usage.get("output") or usage.get("outputTokens") or 0)
                input_tokens += input_value
                output_tokens += output_value
                total_tokens += int(
                    usage.get("totalTokens")
                    or usage.get("total_tokens")
                    or input_value + output_value
                )
            for part in content:
                if not isinstance(part, dict):
                    continue
                if part.get("type") == "toolCall" and part.get("name") == "exec":
                    exec_calls += 1
                    command = str((part.get("arguments") or {}).get("command", "")).lower()
                    if command in _REDACTED_COMMAND_PLACEHOLDERS:
                        redacted_tool_commands += 1
                    elif "mysql" in command:
                        query = re.search(r"""(?:^|\s)-e\s+(['"])(.*?)\1""", command)
                        db_statements += (
                            len([statement for statement in query.group(2).split(";") if statement.strip()])
                            if query
                            else 1
                        )
        if message.get("role") == "toolResult":
            texts = [
                str(part.get("text") or "")
                for part in content
                if isinstance(part, dict)
            ]
            combined = " ".join(texts)
            if message.get("isError") or combined.startswith("ERROR "):
                sql_errors += 1
    token_source = "trace" if total_tokens or input_tokens or output_tokens else "none"
    if token_source == "none":
        envelope_usage = _envelope_usage(envelope_text)
        if envelope_usage is not None:
            input_tokens = envelope_usage["input_tokens"]
            output_tokens = envelope_usage["output_tokens"]
            total_tokens = envelope_usage["total_tokens"]
            token_source = "envelope"
    return {
        "turns": turns,
        "exec_calls": exec_calls,
        "db_statements": db_statements,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": total_tokens,
        "token_source": token_source,
        "sql_errors": sql_errors,
        "unparsable_trace_lines": unparsable_trace_lines,
        "redacted_tool_commands": redacted_tool_commands,
        "timeouts": int(bool(timed_out)),
        "malformed_final_json": int(bool(malformed_final_json)),
        "wall_seconds": wall_seconds,
        "result_bytes": len(final_text.encode("utf-8")),
    }


def propose_budgets(task_records: Sequence[Mapping[str, Any]]) -> dict[str, dict[str, float]]:
    """Register shared constrained/standard caps from successful calibration tasks."""
    observed = [
        record["costs"]
        for record in task_records
        if record.get("status") == "ok" and isinstance(record.get("costs"), dict)
    ]
    if not observed:
        raise ContractError("Cannot propose budgets without successful task costs")

    budgets: dict[str, dict[str, float]] = {"constrained": {}, "standard": {}}
    for key in COST_BUDGET_KEYS:
        values = [float(row[key]) for row in observed]
        constrained = min(values)
        standard = max(values) * 2
        if key != "wall_seconds":
            constrained = int(constrained)
            standard = int(standard)
        budgets["constrained"][key] = constrained
        budgets["standard"][key] = max(standard, constrained)
    return budgets


def _cost_distribution(task_records: Sequence[Mapping[str, Any]]) -> dict[str, dict[str, float]]:
    observed = [
        record["costs"]
        for record in task_records
        if record.get("status") == "ok" and isinstance(record.get("costs"), dict)
    ]
    distribution: dict[str, dict[str, float]] = {}
    for key in (
        *COST_BUDGET_KEYS,
        "sql_errors",
        "timeouts",
        "malformed_final_json",
        "unparsable_trace_lines",
        "redacted_tool_commands",
    ):
        values = sorted(float(row[key]) for row in observed)
        if not values:
            continue
        p50 = values[(len(values) - 1) // 2]
        p95 = values[min(len(values) - 1, int(len(values) * 0.95))]
        summary: dict[str, float] = {
            "count": len(values),
            "min": values[0],
            "p50": p50,
            "p95": p95,
            "max": values[-1],
        }
        if key != "wall_seconds":
            summary = {name: int(value) for name, value in summary.items()}
        distribution[key] = summary
    return distribution


def check_environment(
    *,
    docker_runner: DockerRunner = subprocess.run,
    network: str = DEFAULT_NETWORK,
    mysql_host: str,
    mysql_port: int,
    mysql_user: str,
    mysql_password: str,
    database: str = "db_agent_view",
    image: str,
    mysql_container: str | None = None,
    probe_timeout_seconds: float = 60,
) -> dict[str, Any]:
    """Verify the shared run environment before any task container is created.

    Checks run in dependency order and stop at the first failure so that a
    missing network or a stopped database never turns into a slow connection
    timeout. Details never carry credential values.
    """
    container = mysql_container or mysql_host
    checks: list[dict[str, str]] = []

    def probe(name: str, command: list[str]) -> str | None:
        try:
            result = _docker(docker_runner, command, timeout=probe_timeout_seconds)
        except DockerCommandError as error:
            detail = redact_trace_text(error.detail, secrets=(mysql_password,))[:300]
            checks.append({"name": name, "status": "failed", "detail": detail or "docker probe failed"})
            return None
        except subprocess.TimeoutExpired:
            checks.append(
                {
                    "name": name,
                    "status": "failed",
                    "detail": f"docker probe timed out after {probe_timeout_seconds:g}s",
                }
            )
            return None
        return result.stdout

    def report() -> dict[str, Any]:
        failed = any(row["status"] == "failed" for row in checks)
        return {"status": "not_run" if failed else "ok", "checks": checks}

    network_stdout = probe(
        "network", ["docker", "network", "inspect", network, "--format", "{{.Name}}"]
    )
    if network_stdout is None:
        return report()
    checks.append({"name": "network", "status": "ok", "detail": network_stdout.strip()})

    state_stdout = probe(
        "mysql_container",
        [
            "docker",
            "inspect",
            container,
            "--format",
            "{{.State.Status}} {{.State.Health.Status}}",
        ],
    )
    if state_stdout is None:
        return report()
    state, _, health = state_stdout.strip().partition(" ")
    healthy = health.strip() in {"healthy", "", "<no value>"}
    if state != "running" or not healthy:
        checks.append(
            {
                "name": "mysql_container",
                "status": "failed",
                "detail": f"{container} state={state} health={health.strip() or 'none'}",
            }
        )
        return report()
    checks.append(
        {"name": "mysql_container", "status": "ok", "detail": f"{container} state=running"}
    )

    query_stdout = probe(
        "database_query",
        [
            "docker",
            "run",
            "--rm",
            "--network",
            network,
            "--env",
            f"MYSQL_PWD={mysql_password}",
            "--entrypoint",
            "mysql",
            image,
            "-h",
            mysql_host,
            "-P",
            str(mysql_port),
            "-u",
            mysql_user,
            "-D",
            database,
            "-N",
            "-B",
            "-e",
            "SELECT 1",
        ],
    )
    if query_stdout is None:
        return report()
    if query_stdout.strip() != "1":
        checks.append(
            {
                "name": "database_query",
                "status": "failed",
                "detail": f"{mysql_user}@{mysql_host}:{mysql_port}/{database} returned no rows",
            }
        )
        return report()
    checks.append(
        {
            "name": "database_query",
            "status": "ok",
            "detail": f"{mysql_user}@{mysql_host}:{mysql_port}/{database}",
        }
    )

    containers_stdout = probe(
        "stale_containers",
        ["docker", "ps", "-a", "--filter", "name=beaver-c0-", "--format", "{{.Names}}"],
    )
    if containers_stdout is None:
        return report()
    stale = [
        name
        for name in (line.strip() for line in containers_stdout.splitlines())
        if name and name != container
    ]
    if stale:
        checks.append(
            {
                "name": "stale_containers",
                "status": "failed",
                "detail": "leaked task containers: " + ", ".join(sorted(stale)),
            }
        )
        return report()
    checks.append({"name": "stale_containers", "status": "ok", "detail": "none"})
    return report()


def _prompt(task: dict[str, Any], *, task_context: str | None = None) -> str:
    context_instructions = (
        "\nRead /tmp/c0-task/context.md for task-specific permitted guidance. "
        "Treat it as guidance, then execute SQL and return your own final result.\n"
        if task_context is not None
        else ""
    )
    return f"""You are answering one BEAVER database question.

Question: {task["question"]}
Database: {task["database"]}
All tables you need are in the `{task["database"]}` database. Do not query other databases.

Use the MySQL command-line client and the connection details supplied through
environment variables. Explore schema and data as needed. Do not use any
previous task history, external task files, gold SQL, annotations, or skills.
Never inspect, print, write, or return credential values. In particular, do
not run `env`, `printenv`, or commands that expose `MYSQL_PWD` or
`OPENCLAW_CUSTOM_API_KEY`.
Do not pass the password as a command-line argument: never write
`--password`, `--password=...`, or `-p<value>`, because the `mysql` client
already reads MYSQL_PWD from the environment.
{context_instructions}

Write exactly one JSON object to /tmp/c0-output/final.json:
{{
  "status": "answered",
  "result": {{"columns": ["column_name"], "rows": [[null]]}},
  "answer": "concise answer",
  "final_sql": "the complete SQL used to produce the result",
  "evidence_tool_call_ids": ["trace event ID"]
}}
Before you finish, run `test -s /tmp/c0-output/final.json` to verify that the
file exists and is non-empty.

Do not stop, summarize, or reply with only a plan before that file exists.
Start by running commands rather than by describing what you intend to do.
"""


def redact_trace_text(text: str, *, secrets: Sequence[str]) -> str:
    """Remove configured secrets and sensitive environment assignments from artifacts."""
    redacted = text
    for secret in secrets:
        if secret:
            redacted = redacted.replace(secret, "<redacted>")
    return _SENSITIVE_ASSIGNMENT.sub(
        lambda match: f"{match.group('name')}=<redacted>", redacted
    )


def _docker(
    docker_runner: DockerRunner,
    command: list[str],
    *,
    capture_output: bool = True,
    timeout: float | None = None,
) -> subprocess.CompletedProcess[str]:
    try:
        return docker_runner(
            command,
            check=True,
            capture_output=capture_output,
            text=True,
            timeout=timeout,
        )
    except subprocess.CalledProcessError as error:
        detail = (error.stderr or error.stdout or "").strip()
        raise DockerCommandError(
            f"Docker command failed: {' '.join(command[:3])}: {detail}",
            detail=detail,
        ) from error


def _docker_with_heartbeat(
    docker_runner: DockerRunner,
    command: list[str],
    *,
    task_id: str,
    heartbeat_seconds: float,
    command_timeout_seconds: float | None,
    progress_stream: TextIO,
) -> subprocess.CompletedProcess[str]:
    """Run a blocking Docker command while periodically reporting task progress."""
    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(
            _docker, docker_runner, command, timeout=command_timeout_seconds
        )
        while True:
            try:
                return future.result(timeout=heartbeat_seconds)
            except FutureTimeoutError:
                print(
                    f"Still running task {task_id}...",
                    file=progress_stream,
                    flush=True,
                )


def _resolve_qualified_model(
    docker_runner: DockerRunner, container_name: str, model: str
) -> str:
    """Resolve a bare model ID against the provider created by onboarding."""
    if "/" in model:
        return model
    result = _docker(
        docker_runner,
        ["docker", "exec", container_name, "cat", "/root/.openclaw/openclaw.json"],
    )
    try:
        config = json.loads(result.stdout)
        providers = config["models"]["providers"]
    except (json.JSONDecodeError, KeyError, TypeError) as error:
        raise ContractError("OpenClaw onboarding did not produce a readable model config") from error

    for provider_name, provider in providers.items():
        for configured_model in provider.get("models", []):
            if configured_model.get("id") == model:
                return f"{provider_name}/{model}"
    raise ContractError(f"Configured model {model!r} was not registered by OpenClaw onboarding")


def _export_session_trajectory(
    docker_runner: DockerRunner, container_name: str
) -> tuple[str, int]:
    """Materialize the agent's step-by-step trajectory from its SQLite session store.

    OpenClaw 2026.8.2 keeps sessions only in SQLite, so the JSONL trace has to be
    exported explicitly; the `transcripts` subsystem does not see agent sessions.
    """
    result = _docker(
        docker_runner,
        [
            "docker",
            "exec",
            container_name,
            "openclaw",
            "sessions",
            "export-trajectory",
            "--session-key",
            AGENT_SESSION_KEY,
            "--agent",
            AGENT_NAME,
            "--workspace",
            TRAJECTORY_WORKSPACE,
            "--output",
            TRAJECTORY_OUTPUT_NAME,
            "--json",
        ],
    )
    try:
        response = json.loads(result.stdout)
        output_dir = response["outputDir"]
        event_count = int(response["eventCount"])
    except (json.JSONDecodeError, KeyError, TypeError, ValueError) as error:
        raise ContractError("OpenClaw did not report a trajectory export") from error
    if not isinstance(output_dir, str) or not output_dir:
        raise ContractError("OpenClaw did not report a trajectory export directory")
    return output_dir, event_count


def _session_id_from_agent_response(response: object) -> str:
    """Read the session ID from supported OpenClaw agent JSON envelopes."""
    if not isinstance(response, dict):
        raise ContractError("OpenClaw agent did not return a JSON object")
    direct_session_id = response.get("sessionId")
    if isinstance(direct_session_id, str) and direct_session_id:
        return direct_session_id
    result = response.get("result")
    if isinstance(result, dict):
        meta = result.get("meta")
        if isinstance(meta, dict):
            agent_meta = meta.get("agentMeta")
            if isinstance(agent_meta, dict):
                session_file = agent_meta.get("sessionFile")
                if isinstance(session_file, str) and session_file:
                    return session_file
                session_id = agent_meta.get("sessionId")
                if isinstance(session_id, str) and session_id:
                    return session_id
    raise ContractError("OpenClaw agent response did not include a session ID")


def run_one_task(
    *,
    manifest_path: Path,
    run_root: Path,
    task_id: str,
    seed: int,
    image: str,
    mysql_host: str,
    mysql_port: int,
    mysql_user: str,
    mysql_password: str,
    network: str = DEFAULT_NETWORK,
    custom_base_url: str = "",
    custom_api_key: str = "",
    model: str = "",
    custom_context_window: int = DEFAULT_CUSTOM_CONTEXT_WINDOW,
    custom_max_tokens: int = DEFAULT_CUSTOM_MAX_TOKENS,
    gateway_port: int = DEFAULT_GATEWAY_PORT,
    agent_timeout_seconds: int = DEFAULT_AGENT_TIMEOUT_SECONDS,
    max_agent_continuations: int = DEFAULT_MAX_AGENT_CONTINUATIONS,
    docker_runner: DockerRunner = subprocess.run,
    gateway_ready_seconds: float = 2,
    task_context: str | None = None,
    heartbeat_seconds: float = 60,
    progress_stream: TextIO | None = None,
) -> TaskArtifacts:
    """Execute one manifest task, validate its final result, and remove its container."""
    if not custom_base_url or not custom_api_key or not model:
        raise ContractError(
            "custom_base_url, custom_api_key, and model are required for an agent run"
        )
    if custom_context_window < 16_000:
        raise ContractError("custom_context_window must be at least 16000")
    if custom_max_tokens < 1_000:
        raise ContractError("custom_max_tokens must be at least 1000")
    if agent_timeout_seconds <= 0:
        raise ContractError("agent_timeout_seconds must be positive")
    if max_agent_continuations < 0:
        raise ContractError("max_agent_continuations must not be negative")
    if heartbeat_seconds <= 0:
        raise ContractError("heartbeat_seconds must be positive")
    progress_stream = progress_stream or sys.stderr
    print(f"Starting task {task_id} (seed={seed})", file=progress_stream, flush=True)
    task = _read_manifest_entry(manifest_path, task_id, seed)
    task_root = run_root / "tasks" / task_id / str(seed)
    # A task whose previous attempt never finished has to be replayable, so the
    # directory is reused. Every stale artifact is removed first: leaving an old
    # final.json behind would let the previous attempt be read as this one.
    if task_root.exists():
        shutil.rmtree(task_root)
    task_root.mkdir(parents=True)
    artifacts = TaskArtifacts(
        task_root=task_root,
        trace_path=task_root / "agent_trace.jsonl",
        stdout_path=task_root / "stdout.log",
        gateway_path=task_root / "gateway.log",
        final_path=task_root / "final.json",
        metadata_path=task_root / "run_metadata.json",
    )
    metadata = {
        "task_id": task_id,
        "seed": seed,
        "database": task["database"],
        "image": image,
        "mysql_host": mysql_host,
        "mysql_port": mysql_port,
        "mysql_user": mysql_user,
        "model_context_window": custom_context_window,
        "model_max_tokens": custom_max_tokens,
    }
    artifacts.metadata_path.write_text(
        json.dumps(metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    package_root = Path(tempfile.mkdtemp(prefix="task-package-", dir=task_root))
    container_name = f"beaver-c0-{task_id}-{seed}-{uuid.uuid4().hex[:12]}"
    task_started = time.perf_counter()
    failure_reason: str | None = None
    agent_calls = 0
    agent_wall_seconds = 0.0
    trajectory_status = "unavailable"
    trajectory_event_count = 0
    secrets = (mysql_password, custom_api_key)

    def save_execution_trace() -> None:
        """Persist the agent's own trajectory, whatever the task outcome was."""
        nonlocal trajectory_status, trajectory_event_count
        artifacts.trace_path.write_text("", encoding="utf-8")
        try:
            output_dir, event_count = _export_session_trajectory(docker_runner, container_name)
            _docker(
                docker_runner,
                [
                    "docker",
                    "cp",
                    f"{container_name}:{output_dir}/events.jsonl",
                    str(artifacts.trace_path),
                ],
            )
        except (DockerCommandError, ContractError, subprocess.TimeoutExpired):
            return
        artifacts.trace_path.write_text(
            redact_trace_text(artifacts.trace_path.read_text(encoding="utf-8"), secrets=secrets),
            encoding="utf-8",
        )
        trajectory_status = "exported"
        trajectory_event_count = event_count

    def write_metadata() -> None:
        artifacts.metadata_path.write_text(
            json.dumps(
                {
                    **metadata,
                    "failure_reason": failure_reason,
                    "agent_calls": agent_calls,
                    "agent_wall_seconds": round(agent_wall_seconds, 3),
                    "wall_seconds": round(time.perf_counter() - task_started, 3),
                    "session_trajectory": trajectory_status,
                    "trajectory_event_count": trajectory_event_count,
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )

    try:
        (package_root / "task.json").write_text(
            json.dumps(task, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8"
        )
        if task_context is not None:
            (package_root / "context.md").write_text(task_context, encoding="utf-8")
        (package_root / "prompt.md").write_text(
            _prompt(task, task_context=task_context), encoding="utf-8"
        )
        _docker(
            docker_runner,
            [
                "docker",
                "create",
                "--name",
                container_name,
                "--network",
                network,
                "--env",
                f"MYSQL_HOST={mysql_host}",
                "--env",
                f"MYSQL_PORT={mysql_port}",
                "--env",
                f"MYSQL_USER={mysql_user}",
                "--env",
                f"MYSQL_PWD={mysql_password}",
                "--env",
                f"MYSQL_DATABASE={task['database']}",
                image,
                "/bin/bash",
                "-lc",
                "tail -f /dev/null",
            ],
        )
        _docker(docker_runner, ["docker", "cp", f"{package_root}/.", f"{container_name}:/tmp/c0-task"])
        _docker(docker_runner, ["docker", "start", container_name])
        _docker(
            docker_runner,
            [
                "docker",
                "exec",
                container_name,
                "/bin/bash",
                "-lc",
                "printf '[client]\\ndefault-character-set=utf8mb4\\n' > /root/.my.cnf",
            ],
        )
        _docker(
            docker_runner,
            [
                "docker",
                "exec",
                container_name,
                "openclaw",
                "onboard",
                "--non-interactive",
                "--accept-risk",
                "--skip-health",
                "--workspace",
                "/tmp/c0-task",
                "--gateway-bind",
                "loopback",
                "--gateway-port",
                str(gateway_port),
                "--auth-choice",
                "custom-api-key",
                "--custom-base-url",
                custom_base_url,
                "--custom-api-key",
                custom_api_key,
                "--custom-model-id",
                model,
            ],
        )
        qualified_model = _resolve_qualified_model(docker_runner, container_name, model)
        provider_name = qualified_model.split("/", maxsplit=1)[0]
        for field, value in (
            ("contextWindow", custom_context_window),
            ("maxTokens", custom_max_tokens),
        ):
            _docker(
                docker_runner,
                [
                    "docker",
                    "exec",
                    container_name,
                    "openclaw",
                    "config",
                    "set",
                    f'models.providers["{provider_name}"].models[0].{field}',
                    str(value),
                    "--strict-json",
                ],
            )
        _docker(
            docker_runner,
            [
                "docker",
                "exec",
                container_name,
                "openclaw",
                "config",
                "set",
                "agents.defaults.timeoutSeconds",
                str(agent_timeout_seconds),
                "--strict-json",
            ],
        )
        _docker(
            docker_runner,
            [
                "docker",
                "exec",
                "--detach",
                container_name,
                "/bin/bash",
                "-lc",
                (
                    "mkdir -p /tmp/c0-output && "
                    f"openclaw gateway run --bind loopback --port {gateway_port} "
                    ">/tmp/c0-output/gateway.log 2>&1"
                ),
            ],
        )
        if gateway_ready_seconds > 0:
            time.sleep(gateway_ready_seconds)
        _docker(
            docker_runner,
            [
                "docker",
                "exec",
                container_name,
                "/bin/bash",
                "-lc",
                f"openclaw models set {qualified_model}",
            ],
        )
        agent_outputs: list[str] = []
        agent_started = time.perf_counter()
        run_deadline = time.monotonic() + agent_timeout_seconds
        for attempt in range(max_agent_continuations + 1):
            remaining_seconds = math.ceil(run_deadline - time.monotonic())
            if remaining_seconds <= 0:
                failure_reason = "agent_timeout"
                break
            message = (
                'prompt=$(cat /tmp/c0-task/prompt.md); printf "%s" "$prompt"'
                if attempt == 0
                else (
                    'printf "%s" "Continue this BEAVER task in the same session. '
                    "Do not reply with a status update or a plan. Keep running tools "
                    'until /tmp/c0-output/final.json has been written and verified non-empty."'
                )
            )
            agent_command = (
                f"openclaw agent --agent {AGENT_NAME} --session-id {AGENT_SESSION_ID} "
                f'--timeout {remaining_seconds} --json --message "$({message})"'
            )
            agent_calls += 1
            try:
                started = _docker_with_heartbeat(
                    docker_runner,
                    [
                        "docker",
                        "exec",
                        container_name,
                        "/bin/bash",
                        "-lc",
                        agent_command,
                    ],
                    task_id=task_id,
                    heartbeat_seconds=heartbeat_seconds,
                    command_timeout_seconds=remaining_seconds,
                    progress_stream=progress_stream,
                )
            except subprocess.TimeoutExpired as error:
                output = error.output
                if isinstance(output, bytes):
                    output = output.decode(errors="replace")
                if isinstance(output, str):
                    agent_outputs.append(output)
                failure_reason = "agent_timeout"
                break
            except DockerCommandError as error:
                try:
                    agent_response = json.loads(error.detail)
                except json.JSONDecodeError:
                    raise
                if not isinstance(agent_response, dict) or agent_response.get("status") != "timeout":
                    raise
                agent_outputs.append(error.detail)
                failure_reason = "agent_timeout"
                break
            agent_outputs.append(started.stdout)
            final_probe = _docker(
                docker_runner,
                [
                    "docker",
                    "exec",
                    container_name,
                    "/bin/bash",
                    "-lc",
                    "test -s /tmp/c0-output/final.json && printf ready || true",
                ],
            )
            if final_probe.stdout.strip() == "ready":
                failure_reason = None
                break
            failure_reason = "final_artifact_not_written"
        agent_wall_seconds = time.perf_counter() - agent_started
        artifacts.stdout_path.write_text(
            redact_trace_text("\n".join(agent_outputs), secrets=secrets),
            encoding="utf-8",
        )
        _docker(
            docker_runner,
            [
                "docker",
                "cp",
                f"{container_name}:/tmp/c0-output/gateway.log",
                str(artifacts.gateway_path),
            ],
        )
        if failure_reason is None:
            try:
                _docker(
                    docker_runner,
                    [
                        "docker",
                        "cp",
                        f"{container_name}:/tmp/c0-output/final.json",
                        str(artifacts.final_path),
                    ],
                )
            except RuntimeError:
                failure_reason = "final_artifact_not_written"
        if failure_reason is not None or not artifacts.final_path.exists():
            artifacts.final_path.write_text(
                json.dumps(
                    {
                        "status": "failed",
                        "failure_reason": failure_reason or "final_artifact_not_written",
                    },
                    sort_keys=True,
                )
                + "\n",
                encoding="utf-8",
            )
            return artifacts
        try:
            response = json.loads(artifacts.final_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as error:
            raise ContractError("final.json is not valid JSON") from error
        if not isinstance(response, dict):
            raise ContractError("final.json must contain an object")
        validate_final_response(response)
        return artifacts
    finally:
        save_execution_trace()
        write_metadata()
        shutil.rmtree(package_root, ignore_errors=True)
        _docker(docker_runner, ["docker", "rm", "--force", container_name])


@contextmanager
def _stop_on_interrupt(stream: TextIO | None = None) -> Iterator[Callable[[], bool]]:
    """Turn the first Ctrl+C into a request to stop after the current task.

    A task can take ten minutes, so an interrupt that lands near its end would
    throw away work that is nearly paid for. The first signal is recorded and
    the batch stops at the next task boundary; a second signal restores the
    default handler, so an impatient user still gets an immediate abort.
    """
    stream = stream or sys.stderr
    requested = False

    def handle(signum: int, frame: Any) -> None:
        nonlocal requested
        requested = True
        signal.signal(signal.SIGINT, previous)
        print(
            "\nStop requested: finishing the current task, then saving the batch summary."
            "\nPress Ctrl+C again to abort immediately.",
            file=stream,
            flush=True,
        )

    previous = signal.signal(signal.SIGINT, handle)
    try:
        yield lambda: requested
    finally:
        signal.signal(signal.SIGINT, previous)


AGENT_TERMINAL_FAILURES = frozenset(
    {"agent_timeout", "final_artifact_not_written", "malformed_final_json"}
)


def _stored_record(run_root: Path, entry: Mapping[str, Any]) -> dict[str, Any] | None:
    """Return the recorded outcome of a task, or None when nothing was recorded.

    `task_costs.json` is written last, so its presence means the per-task
    pipeline ran to the end, whatever the outcome was.
    """
    task_root = run_root / "tasks" / entry["task_id"] / str(entry["seed"])
    try:
        stored = json.loads((task_root / "task_costs.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(stored, dict) or not isinstance(stored.get("costs"), dict):
        return None
    status = stored.get("status")
    failure_type = stored.get("failure_type")
    record: dict[str, Any] = {
        "task_id": entry["task_id"],
        "seed": entry["seed"],
        "status": status,
        "costs": stored["costs"],
    }
    if failure_type is not None:
        record["failure_type"] = failure_type
    if stored.get("error") is not None:
        record["error"] = stored["error"]
    try:
        metadata = json.loads((task_root / "run_metadata.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        metadata = {}
    record["image"] = metadata.get("image")
    record["mysql_host"] = metadata.get("mysql_host")
    return record


def _needs_a_run(record: Mapping[str, Any] | None, *, retry_failed: bool) -> bool:
    """Decide whether a resumed batch should replay this task.

    A failure only counts as settled when it describes the agent's own
    behaviour. A docker command timeout or a runner error says the machine
    misbehaved, so replaying costs nothing but time.
    """
    if record is None:
        return True
    if record["status"] == "ok":
        return False
    return retry_failed or record.get("failure_type") not in AGENT_TERMINAL_FAILURES


def run_manifest(
    *,
    manifest_path: Path,
    run_root: Path,
    image: str,
    mysql_host: str,
    mysql_port: int,
    mysql_user: str,
    mysql_password: str,
    network: str = DEFAULT_NETWORK,
    custom_base_url: str = "",
    custom_api_key: str = "",
    model: str = "",
    custom_context_window: int = DEFAULT_CUSTOM_CONTEXT_WINDOW,
    custom_max_tokens: int = DEFAULT_CUSTOM_MAX_TOKENS,
    gateway_port: int = DEFAULT_GATEWAY_PORT,
    agent_timeout_seconds: int = DEFAULT_AGENT_TIMEOUT_SECONDS,
    max_agent_continuations: int = DEFAULT_MAX_AGENT_CONTINUATIONS,
    docker_runner: DockerRunner = subprocess.run,
    gateway_ready_seconds: float = 2,
    parallelism: int = 1,
    task_contexts: Mapping[str, str] | None = None,
    retry_failed: bool = False,
    should_stop: Callable[[], bool] | None = None,
    progress_stream: TextIO | None = None,
) -> dict[str, Any]:
    """Run the manifest entries that have not finished yet, and summarize all of them.

    A batch can be stopped and resumed. Tasks that already reached a terminal
    outcome are skipped, and the aggregates are rebuilt from what is on disk, so
    a resumed batch reports the whole manifest rather than only its tail.
    """
    if parallelism < 1:
        raise ContractError("parallelism must be at least 1")
    entries = _read_manifest_entries(manifest_path)
    run_root.mkdir(parents=True, exist_ok=True)

    def run_entry(entry: dict[str, Any]) -> dict[str, Any]:
        task_root = run_root / "tasks" / entry["task_id"] / str(entry["seed"])
        record: dict[str, Any] = {
            "task_id": entry["task_id"],
            "seed": entry["seed"],
            "image": image,
            "mysql_host": mysql_host,
            "status": "failed",
        }
        started = time.perf_counter()
        failure_type: str | None = None
        try:
            artifacts = run_one_task(
                manifest_path=manifest_path,
                run_root=run_root,
                task_id=entry["task_id"],
                seed=entry["seed"],
                image=image,
                mysql_host=mysql_host,
                mysql_port=mysql_port,
                mysql_user=mysql_user,
                mysql_password=mysql_password,
                network=network,
                custom_base_url=custom_base_url,
                custom_api_key=custom_api_key,
                model=model,
                custom_context_window=custom_context_window,
                custom_max_tokens=custom_max_tokens,
                gateway_port=gateway_port,
                agent_timeout_seconds=agent_timeout_seconds,
                max_agent_continuations=max_agent_continuations,
                docker_runner=docker_runner,
                gateway_ready_seconds=gateway_ready_seconds,
                task_context=(task_contexts or {}).get(entry["task_id"]),
                progress_stream=progress_stream,
            )
            final = json.loads(artifacts.final_path.read_text(encoding="utf-8"))
            if final.get("status") == "failed":
                failure_type = final["failure_reason"]
                record["failure_type"] = failure_type
            else:
                record["status"] = "ok"
        except Exception as error:
            record["error"] = str(error)
            if isinstance(error, subprocess.TimeoutExpired):
                # The agent's own timeout is converted to `agent_timeout` inside
                # run_one_task, so reaching here means some other docker command
                # ran long: infrastructure trouble, not the agent's performance.
                failure_type = "docker_command_timeout"
            elif task_root.joinpath("final.json").exists():
                failure_type = "malformed_final_json"
            elif "final.json" in str(error):
                failure_type = "missing_artifact"
            else:
                failure_type = "runner_error"
            record["failure_type"] = failure_type
        trace_path = task_root / "agent_trace.jsonl"
        final_path = task_root / "final.json"
        stdout_path = task_root / "stdout.log"
        trace_text = trace_path.read_text(encoding="utf-8") if trace_path.exists() else ""
        final_text = final_path.read_text(encoding="utf-8") if final_path.exists() else ""
        costs = collect_task_costs(
            trace_text=trace_text,
            envelope_text=stdout_path.read_text(encoding="utf-8") if stdout_path.exists() else "",
            final_text=final_text,
            wall_seconds=time.perf_counter() - started,
            timed_out=failure_type == "agent_timeout",
            malformed_final_json=failure_type == "malformed_final_json",
        )
        record["costs"] = costs
        task_root.mkdir(parents=True, exist_ok=True)
        (task_root / "task_costs.json").write_text(
            json.dumps(
                {
                    "costs": costs,
                    "failure_type": failure_type,
                    "status": record["status"],
                    "task_id": entry["task_id"],
                    "seed": entry["seed"],
                    "error": record.get("error"),
                },
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        return record

    pending = [
        entry
        for entry in entries
        if _needs_a_run(_stored_record(run_root, entry), retry_failed=retry_failed)
    ]
    progress_stream = progress_stream or sys.stderr
    if len(pending) < len(entries):
        print(
            f"Resuming: {len(entries) - len(pending)} of {len(entries)} tasks already finished,"
            f" {len(pending)} left to run.",
            file=progress_stream,
            flush=True,
        )
    stopped_early = False
    ran: list[dict[str, Any]] = []
    if parallelism == 1:
        for entry in pending:
            if should_stop is not None and should_stop():
                stopped_early = True
                break
            try:
                ran.append(run_entry(entry))
            except KeyboardInterrupt:
                # The task's own cleanup already ran; without a task_costs.json it
                # stays pending, so the next attempt replays it from the start.
                stopped_early = True
                break
    else:
        with ThreadPoolExecutor(max_workers=parallelism) as pool:
            futures = [pool.submit(run_entry, entry) for entry in pending]
            try:
                ran = [future.result() for future in futures]
            except KeyboardInterrupt:
                stopped_early = True
                for future in futures:
                    future.cancel()
                ran = [future.result() for future in futures if future.done() and not future.cancelled()]

    tasks: list[dict[str, Any]] = []
    pending_task_ids: list[str] = []
    for entry in entries:
        stored = _stored_record(run_root, entry)
        if stored is not None:
            tasks.append(stored)
        if _needs_a_run(stored, retry_failed=False):
            pending_task_ids.append(entry["task_id"])
    ok_count = sum(1 for row in tasks if row["status"] == "ok")
    summary = {
        "task_count": len(tasks),
        "ok_count": ok_count,
        "failed_count": len(tasks) - ok_count,
        "tasks": tasks,
        "image": image,
        "mysql_host": mysql_host,
        "ran_count": len(ran),
        "skipped_count": len(entries) - len(pending),
        "pending_task_ids": pending_task_ids,
        "complete": not pending_task_ids,
        "stopped_early": stopped_early,
    }
    distribution = _cost_distribution(tasks)
    (run_root / "cost_distribution.json").write_text(
        json.dumps(distribution, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    if ok_count:
        budgets = propose_budgets(tasks)
        (run_root / "budget.json").write_text(
            json.dumps(budgets, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        summary["budgets"] = budgets
    summary["cost_distribution"] = distribution
    (run_root / "run_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return summary


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest-path", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--task-id")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--parallelism", type=int, default=1)
    parser.add_argument(
        "--retry-failed",
        action="store_true",
        help="Also replay tasks that already failed on the agent's own terms.",
    )
    parser.add_argument("--image", default=os.environ.get("BEAVER_C0_AGENT_IMAGE", "beaver-c0-agent:local"))
    parser.add_argument("--mysql-host", default=os.environ.get("BEAVER_C0_MYSQL_HOST", "beaver-c0-mysql"))
    parser.add_argument("--mysql-port", type=int, default=int(os.environ.get("BEAVER_C0_MYSQL_PORT", "3306")))
    parser.add_argument("--mysql-user", default=os.environ.get("AGENT_VIEW_AGENT_USER", "agent_view_agent"))
    parser.add_argument("--mysql-password", default=os.environ.get("AGENT_VIEW_AGENT_PASSWORD"))
    parser.add_argument("--network", default=DEFAULT_NETWORK)
    parser.add_argument("--custom-base-url", default=os.environ.get("OPENCLAW_CUSTOM_BASE_URL"))
    parser.add_argument("--custom-api-key", default=os.environ.get("OPENCLAW_CUSTOM_API_KEY"))
    parser.add_argument(
        "--model",
        default=os.environ.get("OPENCLAW_CUSTOM_MODEL_ID") or os.environ.get("DEFAULT_MODEL"),
    )
    parser.add_argument(
        "--custom-context-window",
        type=int,
        default=int(os.environ.get("OPENCLAW_CUSTOM_CONTEXT_WINDOW", DEFAULT_CUSTOM_CONTEXT_WINDOW)),
    )
    parser.add_argument(
        "--custom-max-tokens",
        type=int,
        default=int(os.environ.get("OPENCLAW_CUSTOM_MAX_TOKENS", DEFAULT_CUSTOM_MAX_TOKENS)),
    )
    parser.add_argument("--gateway-port", type=int, default=int(os.environ.get("GATEWAY_PORT", DEFAULT_GATEWAY_PORT)))
    parser.add_argument("--agent-timeout-seconds", type=int, default=DEFAULT_AGENT_TIMEOUT_SECONDS)
    parser.add_argument(
        "--max-agent-continuations", type=int, default=DEFAULT_MAX_AGENT_CONTINUATIONS
    )
    parser.add_argument("--gateway-ready-seconds", type=float, default=2)
    parser.add_argument("--skip-environment-preflight", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not args.mysql_password:
        parser.error("--mysql-password or AGENT_VIEW_AGENT_PASSWORD is required")
    manifest_path = args.manifest_path
    databases = {entry["database"] for entry in _read_manifest_entries(manifest_path)}
    if len(databases) != 1:
        parser.error(f"manifest must name exactly one database, found {sorted(databases)}")

    if not args.skip_environment_preflight:
        environment = check_environment(
            network=args.network,
            mysql_host=args.mysql_host,
            mysql_port=args.mysql_port,
            mysql_user=args.mysql_user,
            mysql_password=args.mysql_password,
            database=databases.pop(),
            image=args.image,
        )
        if environment["status"] != "ok":
            args.run_root.mkdir(parents=True, exist_ok=True)
            (args.run_root / "environment_preflight.json").write_text(
                json.dumps(environment, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            for check in environment["checks"]:
                if check["status"] == "failed":
                    print(
                        f"environment preflight failed: {check['name']}: {check['detail']}",
                        file=sys.stderr,
                    )
            raise SystemExit(2)

    shared_kwargs = {
        "manifest_path": manifest_path,
        "run_root": args.run_root,
        "image": args.image,
        "mysql_host": args.mysql_host,
        "mysql_port": args.mysql_port,
        "mysql_user": args.mysql_user,
        "mysql_password": args.mysql_password,
        "network": args.network,
        "custom_base_url": args.custom_base_url,
        "custom_api_key": args.custom_api_key,
        "model": args.model,
        "custom_context_window": args.custom_context_window,
        "custom_max_tokens": args.custom_max_tokens,
        "gateway_port": args.gateway_port,
        "agent_timeout_seconds": args.agent_timeout_seconds,
        "max_agent_continuations": args.max_agent_continuations,
        "gateway_ready_seconds": args.gateway_ready_seconds,
    }
    if args.task_id:
        artifacts = run_one_task(task_id=args.task_id, seed=args.seed, **shared_kwargs)
        print(json.dumps({"task_root": str(artifacts.task_root)}, sort_keys=True))
        return

    with _stop_on_interrupt() as should_stop:
        summary = run_manifest(
            parallelism=args.parallelism,
            retry_failed=args.retry_failed,
            should_stop=should_stop,
            **shared_kwargs,
        )
    print(json.dumps(
        {
            "task_count": summary["task_count"],
            "ok_count": summary["ok_count"],
            "failed_count": summary["failed_count"],
            "ran_count": summary["ran_count"],
            "skipped_count": summary["skipped_count"],
            "pending_count": len(summary["pending_task_ids"]),
            "complete": summary["complete"],
            "stopped_early": summary["stopped_early"],
            "run_root": str(args.run_root),
        },
        sort_keys=True,
    ))


if __name__ == "__main__":
    main()
