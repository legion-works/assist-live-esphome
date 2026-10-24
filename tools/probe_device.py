# SPDX-License-Identifier: GPL-3.0-or-later
import argparse
import asyncio
import base64
import hashlib
import hmac
import ipaddress
import json
import os
import re
import shutil
import struct
import time
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
PORT = 8765
REQUIRED = {
    "wifi_ssid",
    "wifi_password",
    "assist_live_device_token",
    "assist_live_server",
    "probe_run_id",
}


class ProbeLoader(yaml.SafeLoader):
    pass


def secret_reference(loader: ProbeLoader, node: yaml.Node) -> dict[str, str]:
    if not isinstance(node, yaml.ScalarNode):
        raise ValueError("secret reference must be a scalar")
    return {"secret": loader.construct_scalar(node)}


ProbeLoader.add_constructor("!secret", secret_reference)


def read_secrets(path: Path) -> dict[str, str]:
    fixture = ROOT / "tests/fixtures/secrets.yaml"
    if path.resolve() == fixture.resolve() or path.read_bytes() == fixture.read_bytes():
        raise ValueError("compile fixture secrets are not permitted")
    if path.resolve().is_relative_to(ROOT):
        raise ValueError("secrets must be outside the repository")
    values = yaml.safe_load(path.read_text())
    if not isinstance(values, dict) or any(
        not isinstance(values.get(k), str) or not values[k].strip() for k in REQUIRED
    ):
        raise ValueError("external secrets require all five non-empty string keys")
    if not re.fullmatch(r"[A-Za-z0-9_-]{32,128}", values["assist_live_device_token"]):
        raise ValueError("device token must have 32 to 128 ASCII token characters")
    if not re.fullmatch(r"[0-9a-f]{32}", values["probe_run_id"]):
        raise ValueError("probe_run_id must have 32 lowercase hex characters")
    ipaddress.IPv4Address(values["assist_live_server"])
    return values


def stage(config: Path, secrets: Path, output: Path) -> None:
    if output.resolve().is_relative_to(ROOT):
        raise ValueError("staging output must be outside the repository")
    if output.exists():
        raise ValueError("staging output already exists")
    if config.resolve() != (ROOT / "tests/probes/transport.yaml").resolve():
        raise ValueError("stage requires the reviewed probe configuration")
    read_secrets(secrets)
    header = config.with_name("transport_probe.h")
    revision = hashlib.sha256(config.read_bytes() + header.read_bytes()).hexdigest()
    text = config.read_text().replace(
        "probe_revision: source-not-staged", f"probe_revision: sha256-{revision}"
    )
    output.mkdir(mode=0o700, parents=True, exist_ok=False)
    (output / "transport.yaml").write_text(text)
    shutil.copyfile(header, output / header.name)
    descriptor = os.open(
        output / "secrets.yaml", os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600
    )
    with os.fdopen(descriptor, "wb") as target:
        target.write(secrets.read_bytes())


def valid_evidence(event: dict) -> bool:
    return (
        event.get("sender") == "device"
        and event.get("device_origin") == "voice-pe-probe"
        and isinstance(event.get("firmware_revision"), str)
        and re.fullmatch(r"sha256-[0-9a-f]{64}", event["firmware_revision"]) is not None
        and isinstance(event.get("boot_id"), str)
        and re.fullmatch(r"[0-9a-f]{16}", event["boot_id"]) is not None
        and type(event.get("seq")) is int
        and 0 <= event["seq"] < 2020
        and type(event.get("t_device_ms")) is int
        and event["t_device_ms"] >= 0
    )


def decode_event(packet: bytes, token: str, run_id: str) -> dict:
    try:
        text = packet.decode("ascii")
        body, tag = text.rsplit("|", 1)
        expected = hmac.new(token.encode(), body.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(tag, expected):
            raise ValueError("incorrect event tag")
        version, device, boot, seq, device_ms, stage_name, data = body.split("|")
        sender, origin, revision, run, transport, trial, elapsed = data.split(",")
        event: dict[str, Any] = dict(
            sender=sender,
            device_origin=origin,
            firmware_revision=revision,
            boot_id=boot,
            seq=int(seq),
            t_device_ms=int(device_ms),
            stage=stage_name,
            transport=transport,
            trial=int(trial),
            reconnect_ms=int(elapsed),
        )
        if (
            version != "1"
            or device != "voice-pe-probe"
            or run != run_id
            or transport not in {"udp", "websocket"}
            or stage_name not in {"ready", "probe_event", "reconnect"}
            or not 0 <= event["trial"] <= 10
            or event["reconnect_ms"] < 0
            or not valid_evidence(event)
        ):
            raise ValueError("invalid device event fields")
        return event
    except (UnicodeError, TypeError, ValueError):
        raise ValueError("invalid authenticated device event") from None


class EvidenceReader:
    def __init__(self, token: str, run_id: str):
        self.token = token
        self.run_id = run_id
        self.events: list[dict] = []
        self.seen: set[tuple[str, int]] = set()
        self.rejected = 0
        self.identity: tuple[str, str] | None = None

    def accept(self, packet: bytes, transport: str, arrival_ms: float) -> bool:
        try:
            event = decode_event(packet, self.token, self.run_id)
            identity = (event["boot_id"], event["firmware_revision"])
            key = (event["boot_id"], event["seq"])
            if event["transport"] != transport or key in self.seen:
                raise ValueError("replay or incorrect transport")
            # Trial rule: one measurement uses one boot of one firmware revision.
            # The server accepts new boot windows (assist-live docs/design.md).
            if self.identity is not None and self.identity != identity:
                raise ValueError("device restart or changed firmware during trial")
            # ready is not a measurement and does not reserve (boot_id, 0).
            if event["stage"] == "ready":
                return False
            base = 0 if transport == "udp" else 1010
            offset = event["seq"] - base
            if event["stage"] == "probe_event" and not (
                0 <= offset < 1000 and event["trial"] == 0
            ):
                raise ValueError("invalid event sequence")
            if event["stage"] == "reconnect" and (
                event["trial"] == 0 or offset != 999 + event["trial"]
            ):
                raise ValueError("invalid reconnect sequence")
            self.identity = identity
            self.seen.add(key)
            self.events.append({**event, "arrival_ms": arrival_ms})
            return True
        except ValueError:
            self.rejected += 1
            return False

    def summary(self, events: int, reconnects: int) -> dict:
        result = {}
        for transport in ("udp", "websocket"):
            rows = [e for e in self.events if e["transport"] == transport]
            numbered = [e for e in rows if e["stage"] == "probe_event"]
            high = -1
            reordered = 0
            for event in numbered:
                reordered += event["seq"] < high
                high = max(high, event["seq"])
            offsets = [e["arrival_ms"] - e["t_device_ms"] for e in numbered]
            trials = [e["reconnect_ms"] for e in rows if e["stage"] == "reconnect"]
            result[transport] = dict(
                received=len(numbered),
                missing=events - len(numbered),
                reordered=reordered,
                reconnects=len(trials),
                reconnects_missing=reconnects - len(trials),
                reconnect_ms=trials,
                delay_spread_ms=max(offsets) - min(offsets) if offsets else None,
            )
        return result


def write_report(
    path: Path,
    reader: EvidenceReader,
    events: int,
    reconnects: int,
    *,
    recorded: bool = False,
) -> None:
    state = (
        "Recorded sample. Device trial: not run."
        if recorded
        else "Device trial: authenticated device packets received."
    )
    if not recorded and reader.identity is None:
        state = "Device trial: no authenticated device events received."
    lines = [
        "# Device transport probe",
        "",
        state,
        "",
        "| Transport | Received | Missing | Reordered | Reconnects | "
        "Delay spread (ms) |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for name, row in reader.summary(events, reconnects).items():
        lines.append(
            f"| {name} | {row['received']} | {row['missing']} | {row['reordered']} | "
            f"{row['reconnects']} | {row['delay_spread_ms']} |"
        )
    lines.append("")
    for name, row in reader.summary(events, reconnects).items():
        lines.append(f"Reconnect times for `{name}` (ms): `{row['reconnect_ms']}`.")
    lines.extend(
        [
            "",
            f"Rejected packets: `{reader.rejected}`.",
            "",
            "Delay spread uses the minimum arrival offset as its reference. "
            "It is not absolute one-way latency.",
            "",
        ]
    )
    if reader.identity:
        lines.extend([f"Firmware revision: `{reader.identity[1]}`.", ""])
    path.write_text("\n".join(lines))


async def read_frame(reader: asyncio.StreamReader) -> bytes | None:
    first, second = await reader.readexactly(2)
    if first == 0x88:
        return None
    if first != 0x81 or not second & 0x80:
        raise ValueError("only masked, complete text frames are permitted")
    size = second & 0x7F
    if size == 126:
        size = struct.unpack("!H", await reader.readexactly(2))[0]
    if size > 1024 or size == 127:
        raise ValueError("probe frame is too large")
    mask = await reader.readexactly(4)
    data = await reader.readexactly(size)
    return bytes(value ^ mask[i % 4] for i, value in enumerate(data))


async def receive(reader: EvidenceReader, bind: str, seconds: float, raw: Path) -> None:
    def accept(packet: bytes, transport: str) -> None:
        arrival = time.monotonic_ns() / 1_000_000
        if reader.accept(packet, transport, arrival):
            with raw.open("a") as target:
                target.write(
                    json.dumps(
                        dict(
                            packet=packet.decode("ascii"),
                            transport=transport,
                            arrival_ms=arrival,
                        )
                    )
                    + "\n"
                )

    class UDP(asyncio.DatagramProtocol):
        def connection_made(self, transport):
            self.transport = transport

        def datagram_received(self, data, addr):
            try:
                event = decode_event(data, reader.token, reader.run_id)
                if event["stage"] == "ready":
                    body = f"arm|{event['boot_id']}|{reader.run_id}"
                    tag = hmac.new(
                        reader.token.encode(), body.encode(), hashlib.sha256
                    ).hexdigest()
                    self.transport.sendto(f"{body}|{tag}".encode(), addr)
                    return
            except ValueError:
                pass
            accept(data, "udp")

    async def websocket(
        source: asyncio.StreamReader, target: asyncio.StreamWriter
    ) -> None:
        try:
            header = (await asyncio.wait_for(source.readuntil(b"\r\n\r\n"), 5)).decode(
                "ascii"
            )
            fields = dict(
                line.split(": ", 1) for line in header.split("\r\n")[1:] if ": " in line
            )
            if (
                not header.startswith("GET /q1 HTTP/1.1\r\n")
                or fields.get("Upgrade", "").lower() != "websocket"
            ):
                raise ValueError("invalid WebSocket upgrade")
            key = fields["Sec-WebSocket-Key"]
            digest = base64.b64encode(
                hashlib.sha1(
                    (key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11").encode()
                ).digest()
            ).decode()
            target.write(
                (
                    "HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\n"
                    f"Connection: Upgrade\r\nSec-WebSocket-Accept: {digest}\r\n\r\n"
                ).encode()
            )
            await target.drain()
            while True:
                packet = await asyncio.wait_for(read_frame(source), 5)
                if packet is None:
                    break
                accept(packet, "websocket")
        except (
            ValueError,
            KeyError,
            UnicodeError,
            OSError,
            asyncio.IncompleteReadError,
            asyncio.LimitOverrunError,
            TimeoutError,
        ):
            reader.rejected += 1
        finally:
            target.close()
            await target.wait_closed()

    loop = asyncio.get_running_loop()
    udp, _ = await loop.create_datagram_endpoint(UDP, local_addr=(bind, PORT))
    try:
        server = await asyncio.start_server(websocket, bind, PORT)
        async with server:
            await asyncio.sleep(seconds)
    finally:
        udp.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", nargs="?", choices=["stage"])
    parser.add_argument("--config", type=Path)
    parser.add_argument("--secrets", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--arm", action="store_true")
    parser.add_argument("--events", type=int, choices=[1000], default=1000)
    parser.add_argument("--reconnects", type=int, choices=[10], default=10)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--sample", type=Path)
    parser.add_argument("--bind", default="0.0.0.0")
    parser.add_argument("--seconds", type=float, default=120)
    args = parser.parse_args(argv)
    if args.secrets is None:
        parser.error("--secrets is required")
    try:
        if args.command == "stage":
            if args.config is None or args.output is None or args.arm:
                parser.error("stage requires --config and --output, without --arm")
            stage(args.config, args.secrets, args.output)
            print("PASS probe staged; no upload or device connection")
            return 0
        if args.report is None or (not args.arm and args.sample is None):
            parser.error("a device run requires --arm and --report")
        if args.sample is not None and args.arm:
            parser.error("recorded samples cannot arm a device")
        if not 1 <= args.seconds <= 600:
            parser.error("--seconds must be 1 to 600")
        secrets = read_secrets(args.secrets)
        reader = EvidenceReader(
            secrets["assist_live_device_token"], secrets["probe_run_id"]
        )
        if args.sample:
            for line in args.sample.read_text().splitlines():
                row = json.loads(line)
                reader.accept(
                    row["packet"].encode(), row["transport"], row["arrival_ms"]
                )
        else:
            raw = args.secrets.resolve().parent / f"q1-{reader.run_id}.jsonl"
            descriptor = os.open(raw, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(descriptor, "w"):
                pass
            asyncio.run(receive(reader, args.bind, args.seconds, raw))
        write_report(
            args.report,
            reader,
            args.events,
            args.reconnects,
            recorded=args.sample is not None,
        )
        if reader.identity is None:
            print("FAIL probe evidence: no authenticated device events")
            return 1
        print(
            "PASS recorded sample read"
            if args.sample
            else "PASS device evidence recorded; inspect loss and reconnect results"
        )
        return 0
    except (OSError, ValueError, yaml.YAMLError) as error:
        print(f"FAIL probe: {type(error).__name__}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
