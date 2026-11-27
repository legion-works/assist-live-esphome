import asyncio
import hashlib
import hmac
import json
import os
import shutil
import signal
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
    device="assist-live-probe",
):
    body = (
        f"1|{device}|{boot}|{seq}|{time}|{stage}|"
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
    from tools.check_bootstrap import load_checked
    from tools.probe_device import ProbeLoader

    config = yaml.load(
        (ROOT / "tests/probes/transport.yaml").read_text(), Loader=ProbeLoader
    )
    fixture = load_checked(ROOT / "tests/fixtures/voice-pe.yaml")
    assert "on_boot" not in config["esphome"]
    assert config["packages"] == {"voice_pe": fixture["packages"]["voice_pe"]}
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
    import copy

    from tests.test_pre_roll import assert_stock_wake_handler
    from tests.test_reply_options import assert_stock_off
    from tools.check_bootstrap import check_preserved

    production, stock_probe = resolved_configs
    production = copy.deepcopy(production)
    assert_stock_off(stock_probe, production)
    production_handler = production["micro_wake_word"]["on_wake_word_detected"]
    production_handler["then"] = assert_stock_wake_handler(
        production_handler["then"],
        stock_probe["micro_wake_word"]["on_wake_word_detected"]["then"],
        "return;",
    )
    for before, after in zip(stock_probe["select"], production["select"], strict=True):
        if before["id"] == "wake_word_sensitivity":
            after["on_value"] = before["on_value"]
    production["script"] = [
        item
        for item in production["script"]
        if item["id"]
        not in {
            "assist_live_apply_wake_cutoffs",
            "assist_live_update_reply_wake",
            "assist_live_reply_wake_tail",
            "assist_live_cancel_reply_wake",
            "assist_live_restart_reply_wake",
        }
    ]
    production["globals"] = [
        item
        for item in production["globals"]
        if item["id"]
        not in {"reply_wake_window", "reply_wake_pending", "reply_wake_detected_ms"}
    ]
    if not production["globals"]:
        del production["globals"]
    production["voice_assistant"]["on_listening"] = stock_probe["voice_assistant"][
        "on_listening"
    ]
    for trigger in ("on_error", "on_client_disconnected"):
        production["voice_assistant"][trigger] = stock_probe["voice_assistant"][trigger]
    production["switch"] = stock_probe["switch"]
    for key, value in {
        "assist_live_reply_capture": "return;",
        "assist_live_reply_ready": "return true;",
        "assist_live_reply_cancel": "return;",
        "assist_live_reply_window": "false",
        "assist_live_reply_restart": "false",
    }.items():
        assert production["substitutions"].pop(key) == value
    for section in stock_probe:
        if section not in {
            "substitutions",
            "esphome",
            "wifi",
            "external_components",
            "esp32",
        }:
            check_preserved(stock_probe[section], production[section])
    fixture, probe = (flatten_config(config) for config in (production, stock_probe))
    only_fixture = set(fixture) - set(probe)
    only_probe = set(probe) - set(fixture)
    changed = {
        key for key in fixture.keys() & probe.keys() if fixture[key] != probe[key]
    }
    assert only_fixture == {
        "substitutions.test_device",
        "substitutions.assist_live_server",
        "substitutions.assist_live_wake_arm",
        "substitutions.assist_live_wake_started",
        "assist_live.id",
        "external_components[2].source.type",
        "external_components[2].source.path",
        "external_components[2].components[0]",
        "external_components[2].refresh",
        "esphome.includes",
        "esp32.framework.advanced.include_builtin_idf_components",
        "assist_live.device",
        "assist_live.hmac_key",
        "assist_live.media_player_id",
        "assist_live.port",
        "assist_live.server",
        "assist_live.transport",
        "voice_assistant.on_end.then[5].lambda",
        "voice_assistant.on_start.then[1].lambda",
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
    "field",
    [
        "firmware_revision",
        "t_device_ms",
        "seq",
        "boot_id",
        "device_origin",
        "device_id",
    ],
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


def test_device_identity_is_retained_and_cannot_change(tmp_path):
    from tools.probe_device import EvidenceReader, decode_event, write_report

    event = decode_event(packet(device="test-node"), TOKEN, RUN)
    assert event["device_id"] == "test-node"
    reader = EvidenceReader(TOKEN, RUN)
    assert reader.accept(packet(device="test-node"), "udp", 1000)
    identifier = reader.events[0]["device_id"]
    assert identifier.startswith("device-")
    assert identifier != "test-node"
    assert not reader.accept(packet(1, device="other-node"), "udp", 1010)
    report = tmp_path / "trial.md"
    write_report(report, reader, 1000, 10, recorded=True)
    assert f"Device ID: `{identifier}`." in report.read_text()


def test_report_cannot_replace_research_record(tmp_path, monkeypatch):
    from tools import probe_device

    monkeypatch.setattr(probe_device, "ROOT", tmp_path)
    record = tmp_path / "docs/research/q1-device-probe.md"
    record.parent.mkdir(parents=True)
    record.write_text("Hand-written procedure\n")
    with pytest.raises(ValueError, match="research record"):
        probe_device.write_report(
            record, probe_device.EvidenceReader(TOKEN, RUN), 1000, 10
        )
    assert record.read_text() == "Hand-written procedure\n"


def test_cli_refuses_research_output_before_reading_secrets(tmp_path, monkeypatch):
    from tools import probe_device

    monkeypatch.setattr(probe_device, "ROOT", tmp_path)

    def forbidden(*args):
        pytest.fail("a protected report path must stop before secret access")

    monkeypatch.setattr(probe_device, "read_secrets", forbidden)
    with pytest.raises(SystemExit):
        probe_device.main(
            [
                "--arm",
                "--bind",
                "192.0.2.2",
                "--secrets",
                str(tmp_path / "external.yaml"),
                "--report",
                str(tmp_path / "docs/research/q1-device-probe.md"),
            ]
        )


@pytest.mark.parametrize(
    "alias",
    ["secrets", "symlink", "hardlink", "sample", "derived", "salt", "raw"],
)
def test_cli_refuses_report_aliases_before_any_access(
    tmp_path, monkeypatch, capsys, alias
):
    from tools import probe_device

    def forbidden(*args, **kwargs):
        pytest.fail("an aliased report must stop before input access")

    for name in ("read_secrets", "load_trial_salt", "receive"):
        monkeypatch.setattr(probe_device, name, forbidden)
    secret = secrets_file(tmp_path)
    sample = tmp_path / "sample.jsonl"
    sample.write_text("")
    report = {
        "secrets": secret,
        "symlink": tmp_path / "link.md",
        "hardlink": tmp_path / "hard.md",
        "sample": sample,
        "derived": tmp_path / "sample.md",
        "salt": tmp_path / f"q1-{RUN}.salt",
        "raw": tmp_path / f"q1-{RUN}.jsonl",
    }[alias]
    if alias == "symlink":
        report.symlink_to(secret)
    if alias == "hardlink":
        os.link(secret, report)
    if alias == "derived":
        sample = sample.rename(tmp_path / "sample.events.jsonl")
    before = {path: path.read_bytes() for path in (secret, sample)}
    names = sorted(path.name for path in tmp_path.iterdir())
    mode = (
        ["--arm", "--bind", "192.0.2.2"]
        if alias == "raw"
        else ["--sample", str(sample)]
    )
    argv = [*mode, "--secrets", str(secret), "--report", str(report)]
    assert probe_device.main(argv) == 1
    assert "must not replace" in capsys.readouterr().out
    assert {path: path.read_bytes() for path in before} == before
    assert sorted(path.name for path in tmp_path.iterdir()) == names


@pytest.mark.parametrize("slot", ["report", "events"])
@pytest.mark.parametrize("evidence", ["salt", "jsonl"])
def test_cli_refuses_hard_links_to_trial_records_before_any_access(
    tmp_path, monkeypatch, capsys, slot, evidence
):
    from tools import probe_device

    def forbidden(*args, **kwargs):
        pytest.fail("an aliased report must stop before input access")

    for name in ("read_secrets", "load_trial_salt", "receive"):
        monkeypatch.setattr(probe_device, name, forbidden)
    secret = secrets_file(tmp_path)
    sample = tmp_path / "sample.jsonl"
    sample.write_text("")
    record = tmp_path / f"q1-{RUN}.{evidence}"
    record.write_bytes(b"synthetic trial record\n")
    report = tmp_path / "trial.md"
    os.link(record, report if slot == "report" else tmp_path / "trial.events.jsonl")
    argv = ["--sample", str(sample), "--secrets", str(secret), "--report"]
    assert probe_device.main([*argv, str(report)]) == 1
    assert "must not replace" in capsys.readouterr().out
    assert record.read_bytes() == b"synthetic trial record\n"


@pytest.mark.parametrize("slot", ["report", "events"])
def test_report_write_refuses_a_trial_record_link_made_after_preflight(
    tmp_path, monkeypatch, capsys, slot
):
    from tools import probe_device

    original = probe_device.load_trial_salt
    report = tmp_path / "trial.md"
    target = report if slot == "report" else tmp_path / "trial.events.jsonl"

    def salt_then_link(directory, run_id):
        salt = original(directory, run_id)
        os.link(directory / f"q1-{run_id}.salt", target)
        return salt

    monkeypatch.setattr(probe_device, "load_trial_salt", salt_then_link)
    sample = tmp_path / "sample.jsonl"
    sample.write_text("")
    argv = ["--sample", str(sample), "--secrets", str(secrets_file(tmp_path))]
    assert probe_device.main([*argv, "--report", str(report)]) == 1
    assert "must not replace" in capsys.readouterr().out
    salt = tmp_path / f"q1-{RUN}.salt"
    assert len(salt.read_bytes()) == 32


SECRET_MARKER = "synthetic-credential-marker-7f3c"


@pytest.mark.parametrize(
    "text",
    [
        f'wifi_ssid: test\nwifi_password: "{SECRET_MARKER}\n',
        f"wifi_ssid: test\nwifi_password: !!int {SECRET_MARKER}\n",
        f"wifi_ssid: test\nwifi_password: !!float {SECRET_MARKER}\n",
        f"wifi_ssid: test\nwifi_password: !!bool {SECRET_MARKER}\n",
        f"wifi_ssid: test\nwifi_password: !!timestamp {SECRET_MARKER}\n",
        f"wifi_ssid: test\nwifi_password: !!timestamp 2026-13-45 {SECRET_MARKER}\n",
        f"wifi_ssid: test\nwifi_password: !!binary {SECRET_MARKER}!\n",
        f"wifi_password: {SECRET_MARKER}\nnested: " + "[" * 20000 + "\n",
        f"- {SECRET_MARKER}\n",
        f"{SECRET_MARKER}\n",
    ],
    ids=[
        "scanner",
        "int",
        "float",
        "bool",
        "timestamp",
        "bad-date",
        "binary",
        "deep",
        "list",
        "scalar",
    ],
)
def test_malformed_secrets_never_print_secret_text(tmp_path, text):
    secret = tmp_path / "external.yaml"
    secret.write_text(text)
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "tools/probe_device.py"),
            "--sample",
            str(tmp_path / "sample.jsonl"),
            "--secrets",
            str(secret),
            "--report",
            str(tmp_path / "report.md"),
        ],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 1, result.stdout + result.stderr
    assert SECRET_MARKER not in result.stdout + result.stderr
    assert result.stderr == ""
    assert result.stdout.startswith("FAIL probe: ValueError: ")


def test_malformed_secrets_error_has_no_chained_exception(tmp_path):
    from tools.probe_device import read_secrets

    secret = tmp_path / "external.yaml"
    secret.write_text(f"wifi_ssid: test\nwifi_password: !!int {SECRET_MARKER}\n")
    with pytest.raises(ValueError) as error:
        read_secrets(secret)
    assert str(error.value) == f"{secret}: invalid YAML at line 2"
    assert error.value.__cause__ is None and error.value.__context__ is None


def test_malformed_secrets_report_file_and_line_without_source_text(tmp_path, capsys):
    from tools.probe_device import main

    marker = "synthetic-credential-marker-7f3c"
    secret = tmp_path / "external.yaml"
    secret.write_text(f'wifi_ssid: test\nwifi_password: "{marker}\n')
    argv = ["--sample", str(tmp_path / "sample.jsonl"), "--secrets", str(secret)]
    assert main([*argv, "--report", str(tmp_path / "report.md")]) == 1
    output = capsys.readouterr().out
    assert marker not in output
    assert f"{secret}: invalid YAML at line " in output


def test_invalid_server_address_error_has_no_secret_value(tmp_path):
    from tools.probe_device import read_secrets

    secret = secrets_file(tmp_path)
    marker = "synthetic-server-marker-7f3c"
    secret.write_text(secret.read_text().replace("192.0.2.1", marker))
    with pytest.raises(ValueError) as error:
        read_secrets(secret)
    assert marker not in str(error.value)
    assert error.value.__suppress_context__


@pytest.mark.parametrize("device", ["", "bad name", "a" * 64, "node`"])
def test_decoder_refuses_invalid_node_names(device):
    from tools.probe_device import decode_event

    with pytest.raises(ValueError):
        decode_event(packet(device=device), TOKEN, RUN)


def test_armed_run_requires_bind_before_receiver(tmp_path, monkeypatch):
    from tools import probe_device

    async def forbidden(*args):
        pytest.fail("missing bind must not open a receiver")

    monkeypatch.setattr(probe_device, "receive", forbidden)
    with pytest.raises(SystemExit):
        probe_device.main(
            [
                "--arm",
                "--secrets",
                str(secrets_file(tmp_path)),
                "--report",
                str(tmp_path / "trial.md"),
            ]
        )
    assert not (tmp_path / f"q1-{RUN}.jsonl").exists()


def test_cli_prints_error_text(tmp_path, capsys):
    from tools.probe_device import main

    assert (
        main(
            [
                "stage",
                "--config",
                str(ROOT / "tests/probes/transport.yaml"),
                "--secrets",
                str(ROOT / "tests/fixtures/secrets.yaml"),
                "--output",
                str(tmp_path / "out"),
            ]
        )
        == 1
    )
    assert (
        "ValueError: compile fixture secrets are not permitted"
        in capsys.readouterr().out
    )


def test_key_count_error_uses_required_set(tmp_path, monkeypatch):
    from tools import probe_device

    monkeypatch.setattr(probe_device, "REQUIRED", {*probe_device.REQUIRED, "extra"})
    with pytest.raises(ValueError, match="all 6 non-empty"):
        probe_device.read_secrets(secrets_file(tmp_path))


def test_firmware_start_guard_follows_success_and_bounds_retries():
    source = (ROOT / "tests/probes/transport_probe.h").read_text()
    start = source[source.index("inline void start(") :]
    assert "attempts >= 3" in start
    assert "++attempts" in start
    assert start.index("started = true") > start.index("result == pdPASS")
    assert "ESP_LOGE" in start
    assert "esphome::App.get_name().c_str()" in start
    assert '"1|voice-pe-probe|"' not in source


def test_mac_suffix_is_private_in_report_and_evidence(tmp_path, monkeypatch):
    from tools import probe_device

    raw_id = "assist-live-probe-a1b2c3"
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    repository = tmp_path / "repository"
    (repository / ".git").mkdir(parents=True)
    report = repository / "trial.md"

    async def recorded(reader, bind, seconds, raw):
        assert reader.accept(packet(device=raw_id), "udp", 1000)
        assert reader.accept(packet(1, device=raw_id), "udp", 1010)

    monkeypatch.setattr(probe_device, "receive", recorded)
    assert (
        probe_device.main(
            [
                "--arm",
                "--bind",
                "192.0.2.2",
                "--secrets",
                str(secrets_file(scratch)),
                "--report",
                str(report),
            ]
        )
        == 0
    )
    for output in repository.iterdir():
        if output.is_file():
            assert raw_id not in output.read_text()
            assert "-a1b2c3" not in output.read_text()
    rows = [
        json.loads(row)
        for row in report.with_suffix(".events.jsonl").read_text().splitlines()
    ]
    identifier = rows[0]["device_id"]
    assert identifier.startswith("device-")
    assert rows[1]["device_id"] == identifier
    assert f"Device ID: `{identifier}`." in report.read_text()
    salts = list(scratch.glob("*.salt"))
    assert len(salts) == 1
    assert len(salts[0].read_bytes()) == 32
    assert salts[0].stat().st_mode & 0o777 == 0o600
    assert not list(repository.rglob("*.salt"))


def test_trial_token_is_stable_with_private_salt_and_changes_between_trials(tmp_path):
    from tools.probe_device import EvidenceReader, load_trial_salt

    salt = load_trial_salt(tmp_path, RUN)
    assert load_trial_salt(tmp_path, RUN) == salt
    identifiers = []
    for key in (salt, salt, load_trial_salt(tmp_path, "f" * 32)):
        reader = EvidenceReader(TOKEN, RUN, salt=key)
        assert reader.accept(packet(device="assist-live-probe-a1b2c3"), "udp", 1000)
        identifiers.append(reader.events[0]["device_id"])
    assert identifiers[0] == identifiers[1]
    assert identifiers[0] != identifiers[2]


def test_trial_salt_refuses_repository_directory(tmp_path):
    from tools.probe_device import load_trial_salt

    (tmp_path / ".git").mkdir()
    with pytest.raises(ValueError, match="outside.*repository"):
        load_trial_salt(tmp_path, RUN)
    assert not list(tmp_path.glob("*.salt"))


def run_native_start(tmp_path, mutant):
    compiler = shutil.which("c++") or shutil.which("g++")
    if compiler is None:
        pytest.fail("FAIL native start guard: system C++ compiler not found")
    harness = ROOT / "tests/native/start_guard.cpp"
    assert harness.is_file(), "FAIL native start guard: missing harness source"
    source = (ROOT / "tests/probes/transport_probe.h").read_text()
    start = source[
        source.index("inline void start(") : source.index(
            "} // namespace transport_probe"
        )
    ]
    if mutant != "control":
        before, after = {
            "early-guard": ("  ++attempts;", "  started = true;\n  ++attempts;"),
            "no-bound": ("started || attempts >= 3", "started"),
            "no-error-log": ("ESP_LOGE(", "if (false) ESP_LOGE("),
        }[mutant]
        assert before in start
        start = start.replace(before, after, 1)
    (tmp_path / "probe_start.inc").write_text(start)
    executable = tmp_path / "start-guard"
    result = subprocess.run(
        [
            compiler,
            "-std=c++17",
            "-Wall",
            "-Wextra",
            "-Werror",
            "-I",
            str(tmp_path),
            str(harness),
            "-o",
            str(executable),
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
        cwd=tmp_path,
    )
    assert result.returncode == 0, (
        f"FAIL native start guard compile: {result.stdout}{result.stderr}"
    )
    return [
        subprocess.run(
            [str(executable), *args],
            capture_output=True,
            check=False,
            timeout=10,
            cwd=tmp_path,
        ).returncode
        for args in ([], ["all-fail"])
    ]


@pytest.mark.parametrize(
    "mutant,expected",
    [
        ("control", [0, 0]),
        ("early-guard", [-signal.SIGABRT, -signal.SIGABRT]),
        ("no-bound", [0, -signal.SIGABRT]),
        ("no-error-log", [-signal.SIGABRT, -signal.SIGABRT]),
    ],
)
def test_native_start_guard(tmp_path, mutant, expected):
    assert run_native_start(tmp_path, mutant) == expected


def test_missing_native_compiler_has_named_failure(tmp_path, monkeypatch):
    monkeypatch.setenv("PATH", str(tmp_path))
    with pytest.raises(
        pytest.fail.Exception,
        match=r"FAIL native start guard: system C\+\+ compiler not found",
    ):
        run_native_start(tmp_path, "control")
