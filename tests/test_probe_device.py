import asyncio
import hashlib
import hmac
import json
import os
import struct
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]


def test_probe_requires_device_evidence():
    from tools.probe_device import valid_evidence

    assert not valid_evidence({"sender": "host", "events": 1000})


TOKEN = "compile-only-not-a-real-token-00000000"
RUN = "0123456789abcdef0123456789abcdef"
REV = "sha256-" + "a" * 64


def packet(
    seq=0,
    stage="probe_event",
    transport="udp",
    trial=0,
    time=100,
    boot="0123456789abcdef",
):
    body = (
        f"1|voice-pe-probe|{boot}|{seq}|{time}|{stage}|"
        f"device,voice-pe-probe,{REV},{RUN},{transport},{trial},0"
    )
    tag = hmac.new(TOKEN.encode(), body.encode(), hashlib.sha256).hexdigest()
    return f"{body}|{tag}".encode()


def secrets_file(tmp_path):
    path = tmp_path / "external.yaml"
    path.write_text(
        yaml.safe_dump(
            {
                "wifi_ssid": "compile-only-no-network",
                "wifi_password": "compile-only-not-a-password",
                "assist_live_device_token": TOKEN,
                "assist_live_server": "192.0.2.1",
                "probe_run_id": RUN,
            }
        )
    )
    return path


def test_stage_is_self_contained_and_does_not_change_fixture(tmp_path):
    from tools.probe_device import stage

    secret = secrets_file(tmp_path)
    fixture = ROOT / "tests/fixtures/secrets.yaml"
    before = fixture.read_bytes()
    output = tmp_path / "staged"
    stage(ROOT / "tests/probes/transport.yaml", secret, output)
    assert fixture.read_bytes() == before
    assert (output / "secrets.yaml").read_bytes() == secret.read_bytes()
    assert (output / "transport_probe.h").read_bytes() == (
        ROOT / "tests/probes/transport_probe.h"
    ).read_bytes()
    assert (output / "secrets.yaml").stat().st_mode & 0o777 == 0o600
    assert "sha256-" in (output / "transport.yaml").read_text()
    with pytest.raises(ValueError):
        stage(ROOT / "tests/probes/transport.yaml", secret, output)


def test_stage_refuses_fixture_and_repository_output(tmp_path):
    from tools.probe_device import stage

    config = ROOT / "tests/probes/transport.yaml"
    with pytest.raises(ValueError, match="compile fixture"):
        stage(config, ROOT / "tests/fixtures/secrets.yaml", tmp_path / "out")
    with pytest.raises(ValueError, match="outside"):
        stage(config, secrets_file(tmp_path), ROOT / "tests/probes/staged")


@pytest.mark.parametrize(
    "key",
    [
        "wifi_ssid",
        "wifi_password",
        "assist_live_device_token",
        "assist_live_server",
        "probe_run_id",
    ],
)
def test_stage_requires_external_keys(tmp_path, key):
    from tools.probe_device import stage

    secret = secrets_file(tmp_path)
    values = yaml.safe_load(secret.read_text())
    del values[key]
    secret.write_text(yaml.safe_dump(values))
    with pytest.raises(ValueError):
        stage(ROOT / "tests/probes/transport.yaml", secret, tmp_path / "out")
    assert not (tmp_path / "out").exists()


def test_probe_extends_stock_without_native_overrides():
    from tools.probe_device import ProbeLoader

    config = yaml.load(
        (ROOT / "tests/probes/transport.yaml").read_text(), Loader=ProbeLoader
    )
    fixture = yaml.load(
        (ROOT / "tests/fixtures/voice-pe.yaml").read_text(), Loader=ProbeLoader
    )
    assert "on_boot" not in config["esphome"]
    assert config["packages"] == fixture["packages"]
    assert config["external_components"][0] == fixture["external_components"][0]
    for key in (
        "voice_assistant",
        "micro_wake_word",
        "media_player",
        "i2s_audio",
        "speaker",
        "microphone",
    ):
        assert key not in config
    assert (
        config["substitutions"]["voice_pe_sounds"]
        == fixture["substitutions"]["voice_pe_sounds"]
    )


@pytest.fixture(scope="module")
def resolved_configs(tmp_path_factory):
    from tools.probe_device import stage

    scratch = tmp_path_factory.mktemp("resolved-probe")
    staged = scratch / "probe"
    stage(ROOT / "tests/probes/transport.yaml", secrets_file(scratch), staged)

    class ResolvedLoader(yaml.SafeLoader):
        pass

    def resolved_lambda(loader: ResolvedLoader, node: yaml.Node) -> str:
        assert isinstance(node, yaml.ScalarNode)
        return loader.construct_scalar(node)

    ResolvedLoader.add_constructor("!lambda", resolved_lambda)
    results = []
    for config in (ROOT / "tests/fixtures/voice-pe.yaml", staged / "transport.yaml"):
        result = subprocess.run(
            [sys.executable, "-m", "esphome", "config", str(config)],
            cwd=ROOT,
            env={
                **os.environ,
                "ESPHOME_DATA_DIR": str(scratch / "data"),
                "ESPHOME_BUILD_PATH": str(scratch / "build"),
            },
            capture_output=True,
            text=True,
            check=False,
            timeout=120,
        )
        assert result.returncode == 0, result.stderr
        assert "INFO Configuration is valid!" in result.stderr
        results.append(yaml.load(result.stdout, Loader=ResolvedLoader))
    return results


def test_resolved_probe_keeps_stock_boot_and_starts_from_loop(resolved_configs):
    fixture, probe = resolved_configs
    assert probe["esphome"]["on_boot"] == fixture["esphome"]["on_boot"]
    assert probe["esphome"]["on_boot"][0]["priority"] == 375
    starts = probe["esphome"].get("on_loop", [])
    assert len(starts) == 1
    assert len(starts[0]["then"]) == 1
    assert "transport_probe::start(" in starts[0]["then"][0]["lambda"]
    assert "delay" not in starts[0]["then"][0]


def flatten_config(value, prefix=""):
    result = {}
    if isinstance(value, (dict, list)) and not value:
        result[prefix] = value
    elif isinstance(value, dict):
        for key, child in value.items():
            result.update(
                flatten_config(child, f"{prefix}.{key}" if prefix else str(key))
            )
    elif isinstance(value, list):
        for index, child in enumerate(value):
            result.update(flatten_config(child, f"{prefix}[{index}]"))
    else:
        result[prefix] = value
    return result


def test_resolved_config_has_only_probe_additions_and_external_credentials(
    resolved_configs,
):
    fixture, probe = (flatten_config(config) for config in resolved_configs)
    only_fixture = set(fixture) - set(probe)
    only_probe = set(probe) - set(fixture)
    changed = {
        key for key in fixture.keys() & probe.keys() if fixture[key] != probe[key]
    }
    assert only_fixture == {
        "substitutions.test_device",
        "substitutions.assist_live_device_token",
        "substitutions.assist_live_server",
        "assist_live.id",
        "external_components[2].source.type",
        "external_components[2].source.path",
        "external_components[2].components[0]",
        "external_components[2].refresh",
        "esphome.includes",
        "esp32.framework.advanced.include_builtin_idf_components",
    }
    assert only_probe == {
        "substitutions.probe_revision",
        "substitutions.probe_token",
        "substitutions.probe_server",
        "substitutions.probe_run_id",
        "esphome.includes[0]",
        "esphome.on_loop[0].then[0].lambda",
        "esp32.framework.advanced.include_builtin_idf_components[0]",
        "esp32.framework.sdkconfig_options.CONFIG_WS_TRANSPORT",
        "esp32.framework.sdkconfig_options.CONFIG_LWIP_MAX_SOCKETS",
    }
    assert changed == {
        "esphome.name",
        "esphome.build_path",
        "wifi.networks[0].ssid",
        "wifi.networks[0].password",
        "wifi.use_address",
    }


def test_authenticated_packet_and_all_signed_fields():
    from tools.probe_device import decode_event

    event = decode_event(packet(), TOKEN, RUN)
    assert event["seq"] == 0
    assert event["t_device_ms"] == 100
    assert event["firmware_revision"] == REV
    for old, new in [
        (b"probe_event", b"wake_detected"),
        (b"|0|", b"|1|"),
        (b"|100|", b"|101|"),
        (b"device,", b"host,"),
        (b"|0123456789abcdef|", b"|1123456789abcdef|"),
        (REV.encode(), ("sha256-" + "b" * 64).encode()),
    ]:
        with pytest.raises(ValueError):
            decode_event(packet().replace(old, new), TOKEN, RUN)
    with pytest.raises(ValueError):
        decode_event(packet(), TOKEN, "f" * 32)


@pytest.mark.parametrize(
    "field", ["firmware_revision", "t_device_ms", "seq", "boot_id", "device_origin"]
)
def test_evidence_refuses_missing_device_fields(field):
    from tools.probe_device import decode_event, valid_evidence

    event = decode_event(packet(), TOKEN, RUN)
    assert valid_evidence(event)
    del event[field]
    assert not valid_evidence(event)


def test_reader_rejects_replay_and_tracks_loss_order_and_restart():
    from tools.probe_device import EvidenceReader

    reader = EvidenceReader(TOKEN, RUN)
    assert reader.accept(packet(0), "udp", 1000)
    assert reader.accept(packet(2, time=120), "udp", 1030)
    assert reader.accept(packet(1, time=110), "udp", 1040)
    assert not reader.accept(packet(1, time=110), "udp", 1041)
    assert not reader.accept(packet(3), "websocket", 1042)
    assert reader.summary(4, 10)["udp"]["missing"] == 1
    assert reader.summary(4, 10)["udp"]["reordered"] == 1
    assert reader.summary(4, 10)["udp"]["delay_spread_ms"] == 30


def test_report_writer_uses_recorded_sample_without_device_claim(tmp_path):
    from tools.probe_device import EvidenceReader, write_report

    reader = EvidenceReader(TOKEN, RUN)
    reader.accept(packet(), "udp", 1000)
    target = tmp_path / "report.md"
    write_report(target, reader, 1000, 10, recorded=True)
    text = target.read_text()
    assert "Recorded sample" in text
    assert "Device trial: not run" in text
    assert "| udp | 1 | 999 |" in text
    assert TOKEN not in text
    assert "firmware ready" not in text
    evidence = tmp_path / "sample.jsonl"
    evidence.write_text(
        json.dumps(
            {"packet": packet().decode(), "transport": "udp", "arrival_ms": 1000}
        )
        + "\n"
    )


def test_cli_requires_arm_and_exact_trial_counts(tmp_path):
    from tools.probe_device import main

    with pytest.raises(SystemExit):
        main(
            [
                "--events",
                "1000",
                "--reconnects",
                "10",
                "--report",
                str(tmp_path / "report.md"),
            ]
        )
    with pytest.raises(SystemExit):
        main(
            [
                "--arm",
                "--events",
                "999",
                "--reconnects",
                "10",
                "--report",
                str(tmp_path / "report.md"),
            ]
        )
    assert not (tmp_path / "report.md").exists()


def test_reader_rejects_restart_and_invalid_trial():
    from tools.probe_device import EvidenceReader

    reader = EvidenceReader(TOKEN, RUN)
    assert reader.accept(packet(), "udp", 1000)
    assert not reader.accept(packet(1, boot="f" * 16), "udp", 1010)
    assert not reader.accept(packet(999, stage="reconnect", trial=0), "udp", 1020)
    assert not reader.accept(packet(1002, stage="reconnect", trial=1), "udp", 1020)
    assert reader.rejected == 3


def test_complete_recorded_sample_counts_each_transport_and_trial():
    from tools.probe_device import EvidenceReader

    reader = EvidenceReader(TOKEN, RUN)
    for transport, base in (("udp", 0), ("websocket", 1010)):
        for i in range(1000):
            assert reader.accept(
                packet(base + i, transport=transport, time=i), transport, 1000 + i
            )
        for trial in range(1, 11):
            assert reader.accept(
                packet(
                    base + 999 + trial,
                    stage="reconnect",
                    transport=transport,
                    trial=trial,
                    time=2000 + trial,
                ),
                transport,
                3000 + trial,
            )
    for row in reader.summary(1000, 10).values():
        assert row["received"] == 1000
        assert row["missing"] == row["reordered"] == row["reconnects_missing"] == 0
        assert row["reconnects"] == 10


def test_recorded_sample_cli_never_calls_receiver(tmp_path, monkeypatch, capsys):
    from tools import probe_device

    async def forbidden(*args):
        pytest.fail("sample processing must not open a receiver")

    monkeypatch.setattr(probe_device, "receive", forbidden)
    sample = tmp_path / "sample.jsonl"
    sample.write_text(
        json.dumps(dict(packet=packet().decode(), transport="udp", arrival_ms=1000))
        + "\n"
    )
    report = tmp_path / "report.md"
    assert (
        probe_device.main(
            [
                "--sample",
                str(sample),
                "--secrets",
                str(secrets_file(tmp_path)),
                "--events",
                "1000",
                "--reconnects",
                "10",
                "--report",
                str(report),
            ]
        )
        == 0
    )
    assert "PASS recorded sample read" in capsys.readouterr().out
    assert "Device trial: not run" in report.read_text()


def test_armed_cli_arguments_with_recorded_receiver_data(tmp_path, monkeypatch):
    from tools import probe_device

    async def recorded(reader, bind, seconds, raw):
        assert bind == "192.0.2.2"
        assert seconds == 30
        assert raw.exists()
        reader.accept(packet(), "udp", 1000)

    monkeypatch.setattr(probe_device, "receive", recorded)
    report = tmp_path / "report.md"
    assert (
        probe_device.main(
            [
                "--arm",
                "--events",
                "1000",
                "--reconnects",
                "10",
                "--secrets",
                str(secrets_file(tmp_path)),
                "--report",
                str(report),
                "--bind",
                "192.0.2.2",
                "--seconds",
                "30",
            ]
        )
        == 0
    )
    assert "| udp | 1 | 999 |" in report.read_text()
    assert "firmware ready" not in report.read_text()
    raw = tmp_path / f"q1-{RUN}.jsonl"
    assert raw.exists()
    assert raw.stat().st_mode & 0o777 == 0o600


def test_empty_receiver_report_does_not_claim_device_origin(tmp_path):
    from tools.probe_device import EvidenceReader, write_report

    report = tmp_path / "empty.md"
    write_report(report, EvidenceReader(TOKEN, RUN), 1000, 10)
    assert "no authenticated device events" in report.read_text()


@pytest.mark.parametrize("payload", [b"short", b"x" * 300])
def test_masked_websocket_frame_reader(payload):
    from tools.probe_device import read_frame

    async def read():
        reader = asyncio.StreamReader()
        mask = b"abcd"
        length = (
            bytes([0x80 | len(payload)])
            if len(payload) < 126
            else b"\xfe" + struct.pack("!H", len(payload))
        )
        reader.feed_data(
            b"\x81"
            + length
            + mask
            + bytes(c ^ mask[i % 4] for i, c in enumerate(payload))
        )
        reader.feed_eof()
        return await read_frame(reader)

    assert asyncio.run(read()) == payload


@pytest.mark.parametrize(
    "header", [b"\x01\x80", b"\x81\x00", b"\x81\xff", b"\x81\xfe\xff\xff"]
)
def test_websocket_reader_refuses_fragments_unmasked_and_oversize(header):
    from tools.probe_device import read_frame

    async def read():
        reader = asyncio.StreamReader()
        reader.feed_data(header)
        reader.feed_eof()
        with pytest.raises(ValueError):
            await read_frame(reader)

    asyncio.run(read())
