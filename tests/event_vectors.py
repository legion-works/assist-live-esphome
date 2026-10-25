# SPDX-License-Identifier: GPL-3.0-or-later
import hashlib
import hmac
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COMPONENT = ROOT / "components/assist_live"


def compiler() -> str:
    name = shutil.which(os.environ.get("CXX", "c++"))
    if name is None:
        raise RuntimeError("FAIL native codec: system C++ compiler is required")
    return name


def run(command: list[str]) -> str:
    result = subprocess.run(command, capture_output=True, text=True, timeout=60)
    if result.returncode:
        raise RuntimeError(
            f"FAIL native harness ({result.returncode}):\n"
            + result.stdout
            + result.stderr
        )
    if result.stderr:
        raise RuntimeError("FAIL native harness diagnostics:\n" + result.stderr)
    return result.stdout


def run_cpp_vectors(path: str | Path) -> str:
    vectors = json.loads(Path(path).read_text())
    assert vectors["version"] == 1 and vectors["vectors"]
    with tempfile.TemporaryDirectory(prefix="assist-live-codec-") as directory:
        executable = str(Path(directory) / "codec")
        run(
            [
                compiler(),
                "-std=c++17",
                "-Wall",
                "-Wextra",
                "-Werror",
                "-I",
                str(COMPONENT),
                str(ROOT / "tests/native/event_vectors.cpp"),
                str(COMPONENT / "event_codec.cpp"),
                "-o",
                executable,
            ]
        )
        for vector in vectors["vectors"]:
            event = vector["event"]
            key = bytes.fromhex(vector["key_hex"])
            canonical = bytes.fromhex(vector["canonical_hex"])
            assert hmac.digest(key, canonical, "sha256").hex() == vector["tag"]
            data = json.dumps(
                event["data"],
                sort_keys=True,
                ensure_ascii=False,
                separators=(",", ":"),
                allow_nan=False,
            )
            wire = (
                f'{{"version":1,"device":"{event["device"]}",'
                f'"boot":{event["boot"]},"seq":{event["seq"]},'
                f'"device_ms":{event["device_ms"]},"stage":"{event["stage"]}",'
                f'"data":{data},"tag":"{vector["tag"]}"}}'
            )
            result = run(
                [
                    executable,
                    vector["key_hex"],
                    vector["canonical_hex"],
                    vector["tag"],
                    event["device"],
                    str(event["boot"]),
                    str(event["seq"]),
                    str(event["device_ms"]),
                    event["stage"],
                    data.encode().hex(),
                    wire.encode().hex(),
                ]
            )
            assert json.loads(result) == {**event, "tag": vector["tag"]}
    return "PASS"


def run_cpp_runtime() -> str:
    with tempfile.TemporaryDirectory(prefix="assist-live-runtime-") as directory:
        for websocket in (False, True):
            executable = str(Path(directory) / ("websocket" if websocket else "udp"))
            command = [
                compiler(),
                "-std=c++17",
                "-Wall",
                "-Wextra",
                "-Werror",
                "-I",
                str(ROOT / "tests/native/include"),
                "-I",
                str(COMPONENT),
                str(ROOT / "tests/native/event_runtime.cpp"),
                str(COMPONENT / "event_codec.cpp"),
                "-o",
                executable,
            ]
            if websocket:
                command.insert(1, "-DUSE_ASSIST_LIVE_WEBSOCKET")
            run(command)
            output = run([executable])
            assert "PASS runtime" in output
            assert "fake-secret-byte-array" not in output
            assert "66616b652d736563726574" not in output
        access = Path(directory) / "private_key.cpp"
        access.write_text(
            '#include "assist_live.h"\n'
            "void leak(esphome::assist_live::AssistLiveComponent &component) "
            "{ (void) component.key_; }\n"
        )
        result = subprocess.run(
            [
                compiler(),
                "-std=c++17",
                "-I",
                str(ROOT / "tests/native/include"),
                "-I",
                str(COMPONENT),
                "-c",
                str(access),
                "-o",
                str(Path(directory) / "private.o"),
            ],
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert (
            result.returncode != 0
            and "protected" in result.stderr
            and "key_" in result.stderr
        )
    return "PASS"


def main() -> None:
    assert hashlib.sha256(
        (ROOT / "tests/fixtures/device-vectors.json").read_bytes()
    ).hexdigest() == (
        "b74cf28042f22e9bd85520a864f335e0f61fddbd99559ce458f78cd5b540bc89"
    )
    print(run_cpp_vectors(ROOT / "tests/fixtures/device-vectors.json"))
    print(run_cpp_runtime())


if __name__ == "__main__":
    main()
