import json
import os
import re
import shutil
import subprocess
import sys
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
                for invocation in re.findall(r"\buv run [^\n]+", cmd):
                    assert invocation.startswith(
                        (
                            "uv run --locked ",
                            "uv run --no-project --python 3.14 python "
                            "../assist-live/tools/check_public_tree.py "
                            "--history --root . ",
                        )
                    )


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


def test_ci_keeps_one_checkout_and_fetches_the_authority():
    job = load_workflow("ci.yml")["jobs"]["checks"]
    checkouts = [
        step
        for step in job["steps"]
        if step.get("uses", "").startswith("actions/checkout@")
    ]
    assert len(checkouts) == 1
    assert checkouts[0]["with"]["fetch-depth"] == "0"
    assert "path" not in checkouts[0]["with"]
    steps = [
        step for step in job["steps"] if "check_public_tree.py" in step.get("run", "")
    ]
    assert len(steps) == 1, "CI must fetch and run the authoritative checker explicitly"
    runs = [step.get("run", "") for step in job["steps"]]
    assert next(i for i, run in enumerate(runs) if "gitleaks.tgz" in run) < runs.index(
        steps[0]["run"]
    )
    assert "defaults" not in job


@pytest.mark.parametrize(
    "path",
    [
        "tools/check_public_tree.py",
        "tests/test_public_tree.py",
        "LICENSES/Apache-2.0.txt",
    ],
)
def test_authority_checker_is_not_vendored(path):
    assert not (ROOT / path).exists()


@pytest.mark.parametrize("tool", ["bootstrap", "release"])
def test_worktree_checks_accept_unstaged_deletions(monkeypatch, capsys, tool):
    from tools import check_bootstrap, check_release

    original = subprocess.check_output

    def output(command, **kwargs):
        result = original(command, **kwargs)
        if command[:2] == ["git", "ls-files"]:
            result += b"\0deleted-source.py\0"
        return result

    monkeypatch.setattr(subprocess, "check_output", output)
    if tool == "bootstrap":
        monkeypatch.setattr(sys, "argv", ["check_bootstrap.py"])
        check_bootstrap.main()
        expected = "PASS firmware bootstrap"
    else:
        monkeypatch.setattr(sys, "argv", ["check_release.py", "--source-only"])
        assert check_release.main() == 0
        expected = "PASS source-only release"
    assert expected in capsys.readouterr().out


@pytest.mark.parametrize(
    "source,present,denylist,scan_exit,download_exit",
    [
        ("task", False, False, 0, 0),
        ("task", True, False, 0, 0),
        ("task", True, True, 0, 0),
        ("task", True, True, 17, 0),
        ("ci", True, False, 0, 0),
        ("ci", True, True, 0, 0),
        ("ci", True, True, 17, 0),
        ("ci", True, False, 0, 22),
    ],
)
def test_external_privacy_command(
    tmp_path, source, present, denylist, scan_exit, download_exit
):
    if source == "task":
        tasks = yaml.safe_load((ROOT / "Taskfile.yml").read_text())["tasks"]
        assert {"task": "privacy"} in tasks["check"]["cmds"]
        script = "\n".join(tasks["privacy"]["cmds"])
    else:
        commands = [
            step["run"]
            for step in load_workflow("ci.yml")["jobs"]["checks"]["steps"]
            if "check_public_tree.py" in step.get("run", "")
        ]
        assert len(commands) == 1, "CI must run the authoritative checker explicitly"
        script = commands[0]
    firmware = tmp_path / "firmware"
    firmware.mkdir()
    if present:
        checker = tmp_path / "assist-live/tools/check_public_tree.py"
        checker.parent.mkdir(parents=True)
        checker.write_text("")
    binary = tmp_path / "bin"
    binary.mkdir()
    curl = binary / "curl"
    curl.write_text(
        f"#!{sys.executable}\nimport json, os, sys\n"
        "from pathlib import Path\n"
        'Path(os.environ["CURL_CAPTURE"]).write_text(json.dumps(sys.argv[1:]))\n'
        'if int(os.environ["DOWNLOAD_EXIT"]):\n'
        '    sys.exit(int(os.environ["DOWNLOAD_EXIT"]))\n'
        'Path(sys.argv[sys.argv.index("-o") + 1]).write_text("checker")\n'
    )
    curl.chmod(0o700)
    uv = binary / "uv"
    uv.write_text(
        f"#!{sys.executable}\nimport json, os, sys\n"
        "from pathlib import Path\n"
        'Path(os.environ["CAPTURE"]).write_text(json.dumps(sys.argv[1:]))\n'
        'print("PASS external public tree")\n'
        'sys.exit(int(os.environ["SCAN_EXIT"]))\n'
    )
    uv.chmod(0o700)
    capture = tmp_path / "capture.json"
    curl_capture = tmp_path / "curl-capture.json"
    env = {key: value for key, value in os.environ.items() if key != "PRIVATE_DENYLIST"}
    env.update(
        PATH=str(binary),
        CAPTURE=str(capture),
        SCAN_EXIT=str(scan_exit),
        RUNNER_TEMP=str(tmp_path),
        CURL_CAPTURE=str(curl_capture),
        DOWNLOAD_EXIT=str(download_exit),
    )
    if denylist:
        env["PRIVATE_DENYLIST"] = str(tmp_path / "private denylist.txt")
    result = subprocess.run(
        ["/bin/bash", "-eu", "-c", script],
        cwd=firmware,
        env=env,
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == (download_exit or (scan_exit if present else 0)), (
        result.stdout + result.stderr
    )
    assert result.stderr == ""
    if source == "ci":
        assert json.loads(curl_capture.read_text()) == [
            "-fsSL",
            "https://raw.githubusercontent.com/legion-works/assist-live/main/tools/check_public_tree.py",
            "-o",
            str(tmp_path / "check_public_tree.py"),
        ]
    if download_exit:
        assert not capture.exists()
        return
    if present:
        script_path = (
            str(tmp_path / "check_public_tree.py")
            if source == "ci"
            else "../assist-live/tools/check_public_tree.py"
        )
        expected = [
            "run",
            "--no-project",
            "--python",
            "3.14",
            "python",
            script_path,
            "--history",
            "--root",
            ".",
        ]
        if denylist:
            expected += ["--private-denylist", env["PRIVATE_DENYLIST"]]
        assert json.loads(capture.read_text()) == expected
        assert result.stdout == "PASS external public tree\n"
    else:
        assert not capture.exists()
        assert result.stdout == "NOT CHECKED public tree\n"


def test_actionlint_install_uses_shared_release_archive():
    workflow = load_workflow("ci.yml")
    scripts = [
        step["run"]
        for job in workflow["jobs"].values()
        for step in job["steps"]
        if "actionlint" in step.get("run", "") and "Install" in step.get("name", "")
    ]
    assert len(scripts) == 1
    script = scripts[0]
    assert "releases/download/v1.7.12/actionlint_1.7.12_linux_amd64.tar.gz" in script
    assert "8aca8db96f1b94770f1b0d72b6dddcb1ebb8123cb3712530b08cc387b349a3d8" in script
    assert script.index("sha256sum -c -") < script.index(
        'tar -xzf "$RUNNER_TEMP/actionlint.tgz"'
    )
    assert "go install" not in script
