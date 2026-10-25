import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_source_only_boundary():
    assert (ROOT / "components/assist_live/assist_live.h").exists()
    assert "GNU GENERAL PUBLIC LICENSE" in (ROOT / "LICENSE").read_text()
    result = subprocess.run(
        ["git", "ls-files", "--", "*.bin"], check=True, capture_output=True, cwd=ROOT
    )
    assert result.stdout == b""


def test_transport_is_required_and_identity_is_not_a_node_name():
    from esphome import config_validation as cv

    from components.assist_live import CONFIG_SCHEMA

    with pytest.raises(cv.Invalid) as error:
        CONFIG_SCHEMA(
            {
                "id": "telemetry",
                "device": "satellite-compile-test",
                "hmac_key": "00" * 32,
                "server": "192.0.2.1",
                "media_player_id": "external_media_player",
            }
        )
    assert any(item.path == ["transport"] for item in error.value.errors)


@pytest.mark.parametrize("change", ["action", "secret", "example"])
def test_preservation_gate_refuses_undocumented_changes(change):
    from tools.check_bootstrap import (
        check_preserved,
        check_secret_names,
        compare_example,
    )

    if change == "action":
        with pytest.raises(ValueError, match="stock"):
            check_preserved({"on_start": [{"stop": "native"}]}, {"on_start": []})
    elif change == "secret":
        with pytest.raises(ValueError, match="secret"):
            check_secret_names({"extra": "fake"})
    else:
        with pytest.raises(ValueError, match="example"):
            compare_example({"wifi": {"power_save_mode": "none"}}, {"wifi": {}})


def test_production_templates_do_not_require_the_probe_token():
    from tools.check_bootstrap import load_checked

    for name in ("examples/voice-pe.yaml", "tests/fixtures/voice-pe.yaml"):
        assert (
            "assist_live_device_token" not in load_checked(ROOT / name)["substitutions"]
        )


def test_example_comparison_refuses_unused_probe_token():
    from tools.check_bootstrap import compare_example, load_checked

    fixture = load_checked(ROOT / "tests/fixtures/voice-pe.yaml")
    example = load_checked(ROOT / "examples/voice-pe.yaml")
    fixture["substitutions"]["assist_live_device_token"] = (
        "!secret",
        "assist_live_device_token",
    )
    example["substitutions"]["assist_live_device_token"] = (
        "!secret",
        "assist_live_device_token",
    )
    with pytest.raises(ValueError, match="probe token"):
        compare_example(fixture, example)
