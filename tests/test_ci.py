import json
import os
import re
import shutil
import subprocess
import tomllib
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]


def test_release_strategy_has_matching_version_source() -> None:
    config = json.loads((ROOT / "release-please-config.json").read_text())
    strategy = config["packages"]["."]["release-type"]
    version_file = (
        ROOT / {"python": "pyproject.toml", "simple": "version.txt"}[strategy]
    )
    assert version_file.is_file()
    if strategy == "python":
        version = tomllib.loads(version_file.read_text())["project"]["version"]
    else:
        version = version_file.read_text().strip()
    manifest = json.loads((ROOT / ".release-please-manifest.json").read_text())
    assert manifest["."] == version


def load_workflow(name: str) -> dict:
    return yaml.load(
        (ROOT / ".github/workflows" / name).read_text(), Loader=yaml.BaseLoader
    )


@pytest.mark.parametrize("result", ["success", "failure", "cancelled", "skipped"])
def test_required_check_rejects_every_non_success(result: str) -> None:
    jobs = load_workflow("ci.yml")["jobs"]
    required = jobs["ci-complete"]
    assert set(required["needs"]) == set(jobs) - {"ci-complete"}
    assert required["if"] == "${{ always() }}"
    step = required["steps"][0]
    assert step["env"]["NEEDS"] == "${{ toJSON(needs) }}"
    needs = {job: {"result": "success"} for job in required["needs"]}
    for job in needs:
        changed = {**needs, job: {"result": result}}
        run = subprocess.run(
            ["bash", "-e", "-c", step["run"]],
            env={**os.environ, "NEEDS": json.dumps(changed)},
            capture_output=True,
            text=True,
            check=False,
        )
        assert run.returncode == (0 if result == "success" else 1), run.stdout


@pytest.mark.parametrize(
    "name", ["ci.yml", "release-please.yml", "release-artifacts.yml"]
)
def test_workflow_pins_and_permissions(name: str) -> None:
    workflow = load_workflow(name)
    assert workflow["permissions"] == {"contents": "read"}
    for job in workflow["jobs"].values():
        for step in job["steps"]:
            if "uses" in step:
                assert re.fullmatch(r"[^@]+@[a-f0-9]{40}", step["uses"])
                assert not step["uses"].startswith("actions/upload-artifact@")


@pytest.mark.parametrize("name", ["release-please.yml", "release-artifacts.yml"])
def test_release_guard_fails_closed(name: str) -> None:
    workflow = load_workflow(name)
    assert set(workflow["on"]) == {"workflow_dispatch"}
    for job in workflow["jobs"].values():
        step = job["steps"][0]
        assert step["env"]["APPROVED"] == "${{ vars.ASSIST_LIVE_RELEASES_APPROVED }}"
        for value in ("", "false", "true"):
            run = subprocess.run(
                ["bash", "-e", "-c", step["run"]],
                env={**os.environ, "APPROVED": value},
                capture_output=True,
                text=True,
                check=False,
            )
            assert run.returncode == (0 if value == "true" else 1)


@pytest.mark.parametrize(
    "original",
    [
        "test-network",
        "test-password-not-valid",
        "test-device-token-not-valid",
        "assist-live-server.invalid",
        "satellite-compile-test",
        "000102030405060708090a0b0c0d0e0f000102030405060708090a0b0c0d0e0f",
    ],
)
def test_fixture_secret_change_stops_scan(tmp_path: Path, original: str) -> None:
    target = tmp_path / "tests/fixtures"
    target.mkdir(parents=True)
    shutil.copyfile(ROOT / ".gitleaks.toml", tmp_path / ".gitleaks.toml")
    fixture = target / "secrets.yaml"
    shutil.copyfile(ROOT / "tests/fixtures/secrets.yaml", fixture)
    for changed in (False, True):
        if changed:
            fixture.write_text(fixture.read_text().replace(original, "different-value"))
        result = subprocess.run(
            ["gitleaks", "dir", ".", "--redact", "--exit-code", "1"],
            cwd=tmp_path,
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == int(changed), result.stdout + result.stderr


def test_probe_compile_and_floor_tests_are_required():
    tasks = yaml.safe_load((ROOT / "Taskfile.yml").read_text())["tasks"]
    checks = tasks["check"]["cmds"]
    assert {"task": "compile-probe"} in checks
    assert {"task": "unit-floor"} in checks
    probe = "\n".join(tasks["compile-probe"]["cmds"])
    for required in (
        "probe_device.py stage",
        "transport.yaml",
        "compile-only",
        "check_release.py --compile-log",
        "--build-root",
        "gitleaks dir",
        "mktemp -d",
    ):
        assert required in probe
    assert "RUNNER_TEMP" in probe
    assert "esphome compile" in probe
    floor = "\n".join(tasks["unit-floor"]["cmds"])
    assert "uv run --locked --python 3.12 pytest tests/ -q" in floor
    assert "UV_PROJECT_ENVIRONMENT=.venv-floor" in floor
    assert ".venv-floor/" in (ROOT / ".gitignore").read_text().splitlines()
    for job in load_workflow("ci.yml")["jobs"].values():
        if "steps" in job:
            runs = "\n".join(step.get("run", "") for step in job["steps"])
            if "task config compile" in runs:
                assert "compile-probe" in runs
    assert any("gitleaks git" in cmd for cmd in tasks["secrets"]["cmds"])
    for task in tasks.values():
        for cmd in task["cmds"]:
            if isinstance(cmd, str):
                assert not re.search(r"uv run (?!\-\-locked)", cmd)


def test_history_scans_require_complete_checkout():
    tasks = yaml.safe_load((ROOT / "Taskfile.yml").read_text())["tasks"]
    history_tasks = {
        name
        for name, task in tasks.items()
        if any(isinstance(cmd, str) and "gitleaks git" in cmd for cmd in task["cmds"])
    }
    while True:
        expanded = history_tasks | {
            name
            for name, task in tasks.items()
            if any(
                isinstance(cmd, dict) and cmd.get("task") in history_tasks
                for cmd in task["cmds"]
            )
        }
        if expanded == history_tasks:
            break
        history_tasks = expanded
    checked = set()
    for name, job in load_workflow("ci.yml")["jobs"].items():
        runs = "\n".join(step.get("run", "") for step in job["steps"])
        invoked = {
            word
            for command in re.findall(r"\btask\s+([^\n;&|]+)", runs)
            for word in command.split()
        }
        if "gitleaks git" not in runs and not invoked & history_tasks:
            continue
        checkouts = [
            step
            for step in job["steps"]
            if step.get("uses", "").startswith("actions/checkout@")
        ]
        assert checkouts, f"{name}: history scan needs a checkout"
        assert all(
            step.get("with", {}).get("fetch-depth") == "0" for step in checkouts
        ), name
        checked.add(name)
    assert {"checks", "compile"} <= checked


def test_cmake_is_forced_and_checked_before_each_build():
    taskfile = yaml.safe_load((ROOT / "Taskfile.yml").read_text())
    assert taskfile["env"]["ESPHOME_IDF_DEFAULT_TOOLS_FORCE"] == "required;cmake"
    for name in ("compile", "compile-probe"):
        commands = "\n".join(taskfile["tasks"][name]["cmds"])
        assert commands.index("check_release.py --toolchain") < commands.index(
            "esphome compile"
        )
    compile_job = load_workflow("ci.yml")["jobs"]["compile"]
    assert compile_job["env"]["ESPHOME_IDF_DEFAULT_TOOLS_FORCE"] == "required;cmake"
    runs = "\n".join(step.get("run", "") for step in compile_job["steps"])
    assert runs.index("check_release.py --toolchain") < runs.index(
        "task config compile"
    )


def test_ci_runs_native_vectors_and_both_transport_compiles():
    tasks = yaml.safe_load((ROOT / "Taskfile.yml").read_text())["tasks"]
    assert {"task": "vectors"} in tasks["check"]["cmds"]
    assert tasks["vectors"]["cmds"] == ["uv run --locked python -m tests.event_vectors"]
    for name in ("config", "compile"):
        command = "\n".join(tasks[name]["cmds"])
        assert "for transport in udp websocket" in command
        assert "tests/fixtures/voice-pe-$transport.yaml" in command
        assert f"check_release.py --{name}-log" in command
    workflow = load_workflow("ci.yml")["jobs"]
    checks = "\n".join(step.get("run", "") for step in workflow["checks"]["steps"])
    assert "c++ --version" in checks and "unit vectors" in checks
    compile_steps = "\n".join(
        step.get("run", "") for step in workflow["compile"]["steps"]
    )
    assert "task config compile" in compile_steps


def test_public_tree_scan_is_required_locally_and_in_ci():
    tasks = yaml.safe_load((ROOT / "Taskfile.yml").read_text())["tasks"]
    assert {"task": "privacy"} in tasks["check"]["cmds"]
    privacy = "\n".join(tasks["privacy"]["cmds"])
    assert "check_public_tree.py --history --root ." in privacy
    assert '--private-denylist "$PRIVATE_DENYLIST"' in privacy
    checks = load_workflow("ci.yml")["jobs"]["checks"]
    runs = "\n".join(step.get("run", "") for step in checks["steps"])
    assert "source-only secrets privacy" in runs
