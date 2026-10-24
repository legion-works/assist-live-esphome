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


def test_fixture_secret_change_stops_scan(tmp_path: Path) -> None:
    target = tmp_path / "tests/fixtures"
    target.mkdir(parents=True)
    shutil.copyfile(ROOT / ".gitleaks.toml", tmp_path / ".gitleaks.toml")
    fixture = target / "secrets.yaml"
    shutil.copyfile(ROOT / "tests/fixtures/secrets.yaml", fixture)
    for changed in (False, True):
        if changed:
            fixture.write_text(
                fixture.read_text().replace(
                    "test-password-not-valid", "different-value"
                )
            )
        result = subprocess.run(
            ["gitleaks", "dir", ".", "--redact", "--exit-code", "1"],
            cwd=tmp_path,
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == int(changed), result.stdout + result.stderr
