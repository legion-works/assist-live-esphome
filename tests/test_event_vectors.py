import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_cpp_and_server_vectors_match():
    from tests.event_vectors import run_cpp_vectors

    assert run_cpp_vectors(ROOT / "tests/fixtures/device-vectors.json") == "PASS"


def test_runtime_keeps_audio_nonblocking_and_credentials_private():
    from tests.event_vectors import run_cpp_runtime

    assert run_cpp_runtime() == "PASS"


def test_missing_system_compiler_is_a_named_failure(monkeypatch):
    from tests.event_vectors import run_cpp_vectors

    monkeypatch.setenv("CXX", "no-such-assist-live-compiler")
    with pytest.raises(
        RuntimeError, match="FAIL native codec: system C\\+\\+ compiler is required"
    ):
        run_cpp_vectors(ROOT / "tests/fixtures/device-vectors.json")


def test_automation_data_is_canonical_and_cannot_claim_measured():
    from esphome import config_validation as cv

    from components.assist_live import event_data, server_address

    assert event_data({"z": 1, "a": "é"}) == '{"a":"é","z":1}'
    assert server_address("timing-server.invalid") == "timing-server.invalid"
    assert server_address("192.0.2.1") == "192.0.2.1"
    for value in (
        {"quality": "measured"},
        {"n": float("nan")},
        {"n": 1.5},
        {"n": 2**64},
        {"n": "x" * 257},
    ):
        with pytest.raises(cv.Invalid):
            event_data(value)


def test_generated_wake_timestamp_is_read_at_each_event(tmp_path):
    from tests.event_vectors import COMPONENT, compiler, native_json_include, run

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "esphome",
            "compile",
            "--only-generate",
            str(ROOT / "tests/fixtures/voice-pe.yaml"),
        ],
        env={
            **os.environ,
            "ESPHOME_DATA_DIR": str(tmp_path / "data"),
            "ESPHOME_BUILD_PATH": str(tmp_path / "build"),
        },
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    source = (tmp_path / "build/assist-live-compile-test/src/main.cpp").read_text()
    assert "set_hmac_key" in source
    expression = re.search(r"->set_device_ms\((\[\].*?\})\);", source, re.S)
    assert expression, (
        "event timestamp must be a runtime lambda, not a setup-time value"
    )
    harness = tmp_path / "generated_time.cpp"
    harness.write_text(
        '#include "assist_live.cpp"\n#include <cassert>\nint main() {\n'
        f"auto event_time = {expression[1]};\n"
        'test_time_us = 123000; assert(event_time("wake") == 123);\n'
        'test_time_us = 456000; assert(event_time("wake") == 456);\n}\n'
    )
    executable = str(tmp_path / "generated_time")
    run(
        [
            compiler(),
            "-std=c++17",
            "-Wall",
            "-Werror",
            "-I",
            str(ROOT / "tests/native/include"),
            "-I",
            native_json_include().name,
            "-I",
            str(COMPONENT),
            str(harness),
            str(COMPONENT / "event_codec.cpp"),
            "-o",
            executable,
        ]
    )
    run([executable])


@pytest.mark.parametrize("transport", ["udp", "websocket"])
@pytest.mark.parametrize("show_secrets", [False, True])
def test_config_masks_device_key_without_new_warnings(
    tmp_path, transport, show_secrets
):
    import yaml

    from tests.event_vectors import assert_secret_absent
    from tools.check_release import check_log

    command = [
        sys.executable,
        "-m",
        "esphome",
        "config",
        str(ROOT / f"tests/fixtures/voice-pe-{transport}.yaml"),
    ]
    if show_secrets:
        command.append("--show-secrets")
    result = subprocess.run(
        command,
        env={
            **os.environ,
            "ESPHOME_DATA_DIR": str(tmp_path / "data"),
            "ESPHOME_BUILD_PATH": str(tmp_path / "build"),
        },
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    secret = yaml.safe_load((ROOT / "tests/fixtures/secrets.yaml").read_text())
    assert_secret_absent(
        result.stdout + result.stderr, bytes.fromhex(secret["assist_live_hmac_key"])
    )
    assert "[redacted]" in result.stdout
    log = tmp_path / "config.log"
    log.write_text(result.stdout + result.stderr)
    assert check_log(log, compile_log=False) == []


def test_key_representer_changes_only_the_opaque_type():
    from esphome import yaml_util

    from components.assist_live import hmac_key

    public = {"text": "public", "number": 42, "flag": True}
    before = yaml_util.dump(public)
    fake = "00112233445566778899aabbccddeeff" * 2
    opaque = hmac_key(fake)
    assert str(opaque) == repr(opaque) == "[redacted]"
    for show in (False, True):
        masked = yaml_util.dump({"key": opaque}, show_secrets=show)
        assert "[redacted]" in masked and fake not in masked
    assert yaml_util.dump(public) == before
    assert fake in yaml_util.dump({"ordinary_string": fake})


@pytest.mark.parametrize(
    "encoding", ["raw", "hex", "decimal", "csv", "lines", "prefix"]
)
def test_secret_gate_refuses_every_key_window(encoding):
    from tests.event_vectors import assert_secret_absent

    key = b"fake-secret-byte-array-1234567890"[:32]
    part = key[3:9]
    rendered = {
        "raw": part.decode("ascii"),
        "hex": part.hex(),
        "decimal": "".join(str(byte) for byte in part),
        "csv": ",".join(str(byte) for byte in part),
        "lines": "\n".join(f"assist_live: key byte: {byte}" for byte in part),
        "prefix": key[:8].hex(),
    }[encoding]
    with pytest.raises(AssertionError, match="secret material"):
        assert_secret_absent(rendered, key)
    assert_secret_absent("Assist Live timing: UDP\nDropped timing events: 17", key)
