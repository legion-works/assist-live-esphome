import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def component_config():
    return {
        "id": "telemetry",
        "device": "satellite-compile-test",
        "hmac_key": "00" * 32,
        "server": "192.0.2.1",
        "transport": "udp",
        "media_player_id": "external_media_player",
        "pre_roll": {
            "id": "history_mic",
            "microphone": "i2s_mics",
            "wake_sound": "wake_sound",
        },
    }


def validate(config):
    from esphome.const import KEY_CORE, KEY_TARGET_FRAMEWORK, KEY_TARGET_PLATFORM
    from esphome.core import CORE

    from components.assist_live import CONFIG_SCHEMA

    CORE.data[KEY_CORE] = {
        KEY_TARGET_PLATFORM: "esp32",
        KEY_TARGET_FRAMEWORK: "esp-idf",
    }
    try:
        return CONFIG_SCHEMA(config)
    finally:
        CORE.reset()


def test_optional_pre_roll_accepts_physical_stereo_source_and_provisional_length():
    result = validate(component_config())
    assert result["pre_roll"]["length_ms"] == 250


@pytest.mark.parametrize("length", [0, -1, 1001])
def test_pre_roll_refuses_length_outside_device_limit(length):
    from esphome import config_validation as cv

    config = component_config()
    config["pre_roll"]["length_ms"] = length
    with pytest.raises(cv.Invalid, match="length_ms"):
        validate(config)


@pytest.mark.parametrize("length", [1, 1000])
def test_pre_roll_accepts_length_boundaries(length):
    config = component_config()
    config["pre_roll"]["length_ms"] = length
    assert validate(config)["pre_roll"]["length_ms"] == length


def test_pre_roll_requires_wake_sound_reference():
    from esphome import config_validation as cv

    config = component_config()
    del config["pre_roll"]["wake_sound"]
    with pytest.raises(cv.Invalid, match="wake_sound"):
        validate(config)


@pytest.mark.parametrize("change", ["third", "channel", "id", "gain"])
def test_final_validation_refuses_stock_source_drift_without_partial_rewrite(change):
    import copy

    from esphome import config_validation as cv
    from esphome import final_validate as fv
    from esphome.config import Config

    from components.assist_live import validate_pre_roll

    config = component_config()
    sources = [
        {
            "microphone": "i2s_mics",
            "channels": [channel],
            "gain_factor": 1,
            "bits_per_sample": 16,
        }
        for channel in (0, 1)
    ]
    if change == "third":
        sources.append(copy.deepcopy(sources[0]))
    elif change == "channel":
        sources[1]["channels"] = [0]
    elif change == "id":
        sources[1]["microphone"] = "other_mic"
    else:
        sources[1]["gain_factor"] = 4
    before = copy.deepcopy(sources)
    full = Config()
    full["voice_assistant"] = {"microphone": sources}
    token = fv.full_config.set(full)
    try:
        with pytest.raises(cv.Invalid, match="unchanged stock two-channel VA sources"):
            validate_pre_roll(config)
        assert sources == before, "failure must not partially rewire either source"
    finally:
        fv.full_config.reset(token)


def test_native_pre_roll_history_and_pacing(tmp_path):
    from tests.event_vectors import COMPONENT, compiler, run

    executable = str(tmp_path / "pre_roll")
    run(
        [
            compiler(),
            "-std=c++17",
            "-Wall",
            "-Wextra",
            "-Werror",
            "-I",
            str(COMPONENT),
            str(ROOT / "tests/native/pre_roll.cpp"),
            "-o",
            executable,
        ]
    )
    assert run([executable]) == "PASS pre-roll\n"


def test_native_microphone_adapter_callback_allocations(tmp_path):
    from importlib import resources

    from tests.event_vectors import COMPONENT, compiler, run

    include = tmp_path / "include"
    for header in (
        "core/defines.h",
        "core/component.h",
        "core/helpers.h",
        "components/audio/audio.h",
        "components/switch/switch.h",
        "components/voice_assistant/voice_assistant.h",
        "components/api/api_connection.h",
    ):
        path = include / "esphome" / header
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('#include "pre_roll_host.h"\n')
    path = include / "esphome/components/microphone/microphone.h"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        resources.files("esphome")
        .joinpath("components/microphone/microphone.h")
        .read_text()
    )
    log = include / "esphome/core/log.h"
    log.write_text(
        (ROOT / "tests/native/include/esphome/core/log.h").read_text()
        + "\n#define ESP_LOGD ESP_LOGCONFIG\n#define ESP_LOGE ESP_LOGCONFIG\n"
    )
    executable = str(tmp_path / "microphone_adapter")
    run(
        [
            compiler(),
            "-std=c++17",
            "-Wall",
            "-Wextra",
            "-Werror",
            "-pthread",
            "-DUSE_ASSIST_LIVE_PRE_ROLL",
            "-I",
            str(include),
            "-I",
            str(ROOT / "tests/native"),
            "-I",
            str(ROOT / "tests/native/include"),
            "-I",
            str(COMPONENT),
            str(ROOT / "tests/native/microphone_adapter.cpp"),
            "-o",
            executable,
        ]
    )
    output = run([executable])
    assert "PASS microphone adapter" in output
    assert "arm_to_start_ms=32 arm_expired=0" in output
    assert "arm_to_start_ms=33 arm_expired=1" in output


def resolved_config(path, tmp_path, *, verbose=False):
    import yaml

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "esphome",
            *(["-v"] if verbose else []),
            "config",
            str(path),
        ],
        capture_output=True,
        text=True,
        timeout=120,
        env={
            **os.environ,
            "ESPHOME_BUILD_PATH": str(tmp_path / "build"),
        },
    )
    assert result.returncode == 0, result.stdout + result.stderr

    class ConfigLoader(yaml.SafeLoader):
        pass

    def lambda_text(loader: ConfigLoader, node: yaml.Node):
        assert isinstance(node, yaml.ScalarNode)
        return loader.construct_scalar(node)

    ConfigLoader.add_constructor("!lambda", lambda_text)
    return yaml.load(result.stdout, Loader=ConfigLoader)


def stock_wake_config(tmp_path):
    source = (ROOT / "tests/fixtures/voice-pe.yaml").read_text()
    source = source.split("\nassist_live:\n", 1)[0]
    source = "\n".join(line for line in source.splitlines() if "!include" not in line)
    source = source.replace("../../components", str(ROOT / "components"))
    path = tmp_path / "stock.yaml"
    path.write_text(source)
    (tmp_path / "secrets.yaml").write_bytes(
        (ROOT / "tests/fixtures/secrets.yaml").read_bytes()
    )
    return resolved_config(path, tmp_path)


def assert_stock_wake_handler(handler, stock_handler, arm):
    assert handler[0] == {
        "assist_live.emit_event": {
            "id": "assist_live_component",
            "stage": "wake_detected",
            "data": "{}",
        }
    }, "wake timestamp must precede the stock sound and delay"
    removed = 0

    def without_arm(value):
        nonlocal removed
        if isinstance(value, list):
            result = []
            for index, item in enumerate(value):
                if item == {"lambda": arm}:
                    assert (
                        index + 1 < len(value)
                        and "voice_assistant.start" in value[index + 1]
                    ), "pre-roll arm must be directly before the wake start"
                    removed += 1
                else:
                    result.append(without_arm(item))
            return result
        if isinstance(value, dict):
            return {key: without_arm(item) for key, item in value.items()}
        return value

    normalized = without_arm(handler[1:])
    assert normalized == stock_handler, (
        "stock wake handler drift: update the shared handler for the package pin"
    )
    assert removed == 1, "exactly one arm slot before the wake start"
    return normalized


@pytest.mark.parametrize("name", ["default", "pre-roll", "example"])
def test_wake_timestamp_precedes_sound_and_matches_pinned_stock(tmp_path, name):
    stock = stock_wake_config(tmp_path)
    path = (
        ROOT
        / {
            "default": "tests/fixtures/voice-pe.yaml",
            "pre-roll": "tests/fixtures/voice-pe-pre-roll.yaml",
            "example": "examples/voice-pe.yaml",
        }[name]
    )
    source = path.read_text()
    for relative in ("../components", "../../components"):
        source = source.replace(f"path: {relative}", f"path: {ROOT / 'components'}")
    for relative in ("wake-word.yaml", "../../examples/wake-word.yaml"):
        source = source.replace(
            f"!include {relative}", f"!include {ROOT / 'examples/wake-word.yaml'}"
        )
    source = source.replace(
        "!include voice-pe.yaml", f"!include {ROOT / 'tests/fixtures/voice-pe.yaml'}"
    ).replace(
        "!include ../../examples/pre-roll.yaml",
        f"!include {ROOT / 'examples/pre-roll.yaml'}",
    )
    source += "\nswitch:\n  - id: !extend wake_sound\n    restore_mode: ALWAYS_ON\n"
    path = tmp_path / "sound-on.yaml"
    path.write_text(source)
    config = resolved_config(path, tmp_path)
    assert (
        next(item for item in config["switch"] if item["id"] == "wake_sound")[
            "restore_mode"
        ]
        == "ALWAYS_ON"
    )
    assert "assist_live" not in stock
    stock_handler = stock["micro_wake_word"]["on_wake_word_detected"]["then"]
    assert "wake_sound" in str(stock_handler)
    assert "300" in str(stock_handler)
    assert_stock_wake_handler(
        config["micro_wake_word"]["on_wake_word_detected"]["then"],
        stock_handler,
        "id(pre_roll_mic).wake_detected();" if name == "pre-roll" else "return;",
    )
    for key, value in stock["micro_wake_word"].items():
        if key != "on_wake_word_detected":
            assert config["micro_wake_word"][key] == value


def test_stock_wake_handler_upgrade_drift_has_named_failure(tmp_path):
    stock = stock_wake_config(tmp_path)
    config = resolved_config(ROOT / "tests/fixtures/voice-pe.yaml", tmp_path)
    changed_stock = stock["micro_wake_word"]["on_wake_word_detected"]["then"]
    changed_stock.append({"lambda": "new_stock_action();"})
    with pytest.raises(AssertionError, match="stock wake handler drift"):
        assert_stock_wake_handler(
            config["micro_wake_word"]["on_wake_word_detected"]["then"],
            changed_stock,
            "return;",
        )


def test_resolved_pre_roll_rewires_only_va_and_preserves_stock_actions(tmp_path):
    baseline = resolved_config(ROOT / "tests/fixtures/voice-pe.yaml", tmp_path)
    enabled = resolved_config(ROOT / "tests/fixtures/voice-pe-pre-roll.yaml", tmp_path)
    assert "pre_roll" not in baseline["assist_live"]
    assert [
        source["microphone"] for source in baseline["voice_assistant"]["microphone"]
    ] == ["i2s_mics", "i2s_mics"]
    assert (
        enabled["micro_wake_word"]["microphone"]
        == baseline["micro_wake_word"]["microphone"]
    )
    assert [
        source["microphone"] for source in enabled["voice_assistant"]["microphone"]
    ] == ["pre_roll_mic", "pre_roll_mic"]
    assert [
        source["channels"] for source in enabled["voice_assistant"]["microphone"]
    ] == [[0], [1]]
    for key in ("speaker", "media_player", "script", "select", "light"):
        assert enabled[key] == baseline[key], key
    assert enabled["micro_wake_word"]["models"] == baseline["micro_wake_word"]["models"]
    expected = baseline["voice_assistant"]["microphone"]
    for source in expected:
        source["microphone"] = "pre_roll_mic"
    assert enabled["voice_assistant"]["microphone"] == expected

    removed = 0

    def without_arm(value):
        nonlocal removed
        if isinstance(value, list):
            result = []
            for item in value:
                if item == {"lambda": "id(pre_roll_mic).wake_detected();"}:
                    removed += 1
                    result.append({"lambda": "return;"})
                else:
                    result.append(without_arm(item))
            return result
        if isinstance(value, dict):
            return {key: without_arm(item) for key, item in value.items()}
        return value

    handler = enabled["micro_wake_word"]["on_wake_word_detected"]["then"]
    stock_handler = baseline["micro_wake_word"]["on_wake_word_detected"]["then"]
    assert handler[0] == stock_handler[0], "timing event precedes the wake-sound delay"
    normalized = without_arm(handler)
    assert normalized == stock_handler
    assert removed == 1

    def check_arm_position(value):
        if isinstance(value, list):
            for index, item in enumerate(value):
                if item == {"lambda": "id(pre_roll_mic).wake_detected();"}:
                    assert "voice_assistant.start" in value[index + 1], (
                        "arm is adjacent to the specific wake start"
                    )
                check_arm_position(item)
        elif isinstance(value, dict):
            for item in value.values():
                check_arm_position(item)

    check_arm_position(handler)

    physical_users = []

    def collect_users(value, path=()):
        if isinstance(value, dict):
            for key, item in value.items():
                if key in {"microphone.mute", "microphone.unmute"}:
                    assert item["id"] == "i2s_mics", path
                    physical_users.append(key)
                if key == "microphone" and isinstance(item, str):
                    expected = (
                        "pre_roll_mic" if path[0] == "voice_assistant" else "i2s_mics"
                    )
                    assert item == expected, path
                collect_users(item, (*path, key))
        elif isinstance(value, list):
            for index, item in enumerate(value):
                collect_users(item, (*path, index))

    collect_users(
        resolved_config(
            ROOT / "tests/fixtures/voice-pe-pre-roll.yaml", tmp_path, verbose=True
        )
    )
    assert physical_users.count("microphone.mute") == 1
    assert physical_users.count("microphone.unmute") == 2
    assert enabled["micro_wake_word"]["microphone"]["microphone"] == "i2s_mics"


def test_pre_roll_probe_resolves_with_external_compile_only_secrets(tmp_path):
    base = (
        (ROOT / "tests/fixtures/voice-pe.yaml")
        .read_text()
        .replace("../../components", str(ROOT / "components"))
        .replace("../../examples/wake-word.yaml", str(ROOT / "examples/wake-word.yaml"))
    )
    probe = (
        (ROOT / "tests/probes/pre-roll.yaml")
        .read_text()
        .replace("../fixtures/voice-pe.yaml", "base.yaml")
        .replace("../../examples/pre-roll.yaml", "history.yaml")
    )
    (tmp_path / "base.yaml").write_text(base)
    (tmp_path / "history.yaml").write_text(
        (ROOT / "examples/pre-roll.yaml").read_text()
    )
    (tmp_path / "secrets.yaml").write_bytes(
        (ROOT / "tests/fixtures/secrets.yaml").read_bytes()
    )
    path = tmp_path / "pre-roll.yaml"
    path.write_text(probe)
    config = resolved_config(path, tmp_path)
    assert config["esphome"]["name"] == "assist-live-history"
    assert [
        source["microphone"] for source in config["voice_assistant"]["microphone"]
    ] == ["pre_roll_mic", "pre_roll_mic"]
    stock = stock_wake_config(tmp_path)
    assert_stock_wake_handler(
        config["micro_wake_word"]["on_wake_word_detected"]["then"],
        stock["micro_wake_word"]["on_wake_word_detected"]["then"],
        "id(pre_roll_mic).wake_detected();",
    )
