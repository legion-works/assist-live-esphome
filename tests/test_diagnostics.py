# SPDX-License-Identifier: GPL-3.0-or-later
import subprocess

import pytest

from tests.event_vectors import COMPONENT, ROOT, compiler, run
from tests.test_pre_roll import component_config, resolved_config, validate

TURN_KEYS = (
    "pre_roll_ms",
    "replay_gate_delay_ms",
    "history_trimmed_ms",
    "overflows",
    "dropped_ms",
    "first_live_queue_ms",
    "history_end_queue_ms",
    "turn_end_queue_ms",
)
COUNTER_KEYS = (
    "events_sent",
    "events_confirmed",
    "events_dropped",
    "events_refused",
    "sender_initialization_failures",
    "expired_gates",
)


def test_native_diagnostic_snapshot_and_publish_schedule(tmp_path):
    executable = str(tmp_path / "diagnostics")
    run(
        [
            compiler(),
            "-std=c++17",
            "-Wall",
            "-Wextra",
            "-Werror",
            "-DUSE_ASSIST_LIVE_DIAGNOSTICS",
            "-I",
            str(ROOT / "tests/native/include"),
            "-I",
            str(COMPONENT),
            str(ROOT / "tests/native/diagnostics.cpp"),
            "-o",
            executable,
        ]
    )
    result = subprocess.run([executable], capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout == "PASS diagnostics\n"


def test_diagnostics_off_unless_configured():
    assert "diagnostics" not in validate(component_config())


@pytest.mark.parametrize("key", ["connected", "events_confirmed"])
def test_udp_rejects_connection_claims(key):
    from esphome import config_validation as cv

    config = component_config()
    config["diagnostics"] = {key: {"name": "Transport"}}
    with pytest.raises(cv.Invalid, match="requires websocket transport"):
        validate(config)


def test_turn_diagnostics_require_pre_roll():
    from esphome import config_validation as cv

    config = component_config()
    del config["pre_roll"]
    config["diagnostics"] = {"pre_roll_ms": {"name": "History"}}
    with pytest.raises(cv.Invalid, match="requires pre_roll"):
        validate(config)


def test_resolved_entities_are_opt_in_and_diagnostic(tmp_path):
    baseline = resolved_config(ROOT / "tests/fixtures/voice-pe.yaml", tmp_path)
    enabled = resolved_config(ROOT / "tests/fixtures/voice-pe-pre-roll.yaml", tmp_path)
    assert "diagnostics" not in baseline["assist_live"], "default has no entities"
    diagnostics = enabled["assist_live"].get("diagnostics", {})
    expected = set(TURN_KEYS + COUNTER_KEYS) - {"events_confirmed"}
    assert set(diagnostics) == expected | {"passthrough_reached"}, (
        "opt-in configuration must expose every UDP diagnostic"
    )
    for key, entity in diagnostics.items():
        assert entity["entity_category"] == "diagnostic", key
        if key != "passthrough_reached":
            counter = key in COUNTER_KEYS
            assert entity["state_class"] == (
                "total_increasing" if counter else "measurement"
            ), key
            assert entity.get("unit_of_measurement", "") == (
                "ms" if key.endswith("_ms") else ""
            ), key
            if key in TURN_KEYS:
                assert entity["force_update"], (
                    "identical completed-turn values retain history updates"
                )
    source = (ROOT / "tests/fixtures/voice-pe-pre-roll.yaml").read_text()
    source = source.replace(
        "!include voice-pe.yaml", f"!include {ROOT / 'tests/fixtures/voice-pe.yaml'}"
    ).replace(
        "!include ../../examples/pre-roll.yaml",
        f"!include {ROOT / 'examples/pre-roll.yaml'}",
    )
    source = source.replace(
        "\nassist_live:\n", "\nassist_live:\n  transport: websocket\n"
    )
    source += '    connected:\n      name: "Timing connected"\n'
    source += '    events_confirmed:\n      name: "Events confirmed"\n'
    path = tmp_path / "websocket.yaml"
    path.write_text(source)
    websocket = resolved_config(path, tmp_path)["assist_live"]["diagnostics"]
    assert websocket["connected"]["device_class"] == "connectivity"
    assert websocket["connected"]["entity_category"] == "diagnostic"
    assert websocket["events_confirmed"]["state_class"] == "total_increasing"


def test_default_example_has_no_diagnostic_configuration():
    from tools.check_bootstrap import load_checked

    default = load_checked(ROOT / "examples/voice-pe.yaml")
    assert "diagnostics" not in default["assist_live"]
    example = load_checked(ROOT / "examples/voice-pe-pre-roll.yaml")
    fixture = load_checked(ROOT / "tests/fixtures/voice-pe-pre-roll.yaml")
    assert (
        example["assist_live"]["diagnostics"] == fixture["assist_live"]["diagnostics"]
    )
