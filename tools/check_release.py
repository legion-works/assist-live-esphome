# SPDX-License-Identifier: GPL-3.0-or-later
import argparse
import io
import re
import subprocess
import tarfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COMPILED_SUFFIXES = {".bin", ".elf", ".map", ".uf2", ".img"}
ANSI = re.compile(r"\x1b\[[0-9;]*m")
WARNING_LEVEL = re.compile(
    r"^\s*(?:(?:\[[0-9TZ:.,+ -]+\]|[0-9TZ:.,+ -]+)\s*)?(WARNING\b.*)$"
)
COMPILER_WARNING = re.compile(
    r"^(?P<path>.+?):(?P<line>\d+)(?::\d+)?:\s*warning:\s*"
    r"(?P<message>.+?)\s+\[(?P<flag>-W[^\]]+)\]$"
)

# Stock Voice PE tag 26.9.0, commit 2644f4c794271d735d182ca7ebf899ed46164f4e:
# voice_kit/__init__.py and home-assistant-voice.yaml cause these five warnings.
WARNING_BASELINE = {
    "WARNING register_action('voice_kit.flash', ...) is missing the synchronous= "
    "parameter. Defaulting to synchronous=False (safe but prevents StringRef "
    "optimization). Check the C++ class: use synchronous=False if play_next_() "
    "is deferred to a callback, timer, or loop(); use synchronous=True if "
    "play_next_() always runs before the initial play/play_complex call returns",
    "WARNING GPIO0 is a strapping pin and should only be used for I/O with care.",
    "WARNING GPIO3 is a strapping pin and should only be used for I/O with care.",
    "WARNING [esp32_rmt_led_strip] 'rgb_order' is deprecated, use "
    "'channel_colors: GRB'. Will be removed in 2027.3.0",
    "WARNING GPIO45 is a strapping pin and should only be used for I/O with care.",
}

# The clean ESPHome 2026.10.0 build records these component versions in
# dependencies.lock and managed_components/<component>/idf_component.yml.
# A component-relative path prevents these messages from hiding local warnings.
COMPILER_BASELINE = {
    (
        "esphome/micro-opus",
        "silk/NLSF2A.c",
        54,
        "-Wmaybe-uninitialized",
        "'cos_LSF_QA' may be used uninitialized",
    ): ("0.4.1", "dependencies.lock:dependencies.esphome/micro-opus.version"),
    **{
        (
            "espressif/esp-tflite-micro",
            f"tensorflow/lite/kernels/internal/reference/{name}.h",
            line,
            "-Wshadow",
            "declaration of 'const tflite::ArithmeticParams& params' "
            "shadows a parameter",
        ): (
            "1.3.3~1",
            "dependencies.lock:dependencies.espressif/esp-tflite-micro.version",
        )
        for name, line in [
            ("mul", 150),
            ("mul", 209),
            ("mul", 249),
            ("sub", 264),
            ("sub", 284),
            ("sub", 308),
            ("sub", 420),
        ]
    },
}
COMPILER_SOURCE_ROOTS = {
    "esphome/micro-opus": "build/esp-idf/esphome__micro-opus/opus-staged/",
    "espressif/esp-tflite-micro": "managed_components/espressif__esp-tflite-micro/",
}


def compiler_warning_is_baselined(line: str) -> bool:
    warning = COMPILER_WARNING.fullmatch(line.strip())
    if warning is None:
        return False
    source = warning["path"].replace("\\", "/")
    parts = source.split("/")
    if ".." in parts or "components/assist_live/" in source:
        return False
    for component, marker in COMPILER_SOURCE_ROOTS.items():
        _, separator, relative = ("/" + source).rpartition("/" + marker)
        if separator:
            key = (
                component,
                relative,
                int(warning["line"]),
                warning["flag"],
                warning["message"],
            )
            return key in COMPILER_BASELINE
    return False


def check_content(name: str, data: bytes, depth: int = 0) -> list[str]:
    failures = []
    if Path(name).suffix.lower() in COMPILED_SUFFIXES:
        failures.append(f"{name}: compiled artifact suffix")
    if data.startswith((b"\x7fELF", b"\xe9", b"UF2\n")) or data[4096:4097] == b"\xe9":
        failures.append(f"{name}: compiled image magic")
    stream = io.BytesIO(data)
    # Python 3.12 zipfile.is_zipfile does not restore the stream position.
    # Each probe gets its own stream, so tarfile.is_tarfile reads from offset 0.
    is_zip = zipfile.is_zipfile(io.BytesIO(data))
    is_tar = tarfile.is_tarfile(io.BytesIO(data))
    archive_suffix = name.lower().endswith((".zip", ".tar", ".tar.gz", ".tgz"))
    if not (is_zip or is_tar or archive_suffix):
        return failures
    if depth >= 3:
        return [*failures, f"{name}: archive nesting limit"]
    try:
        stream.seek(0)
        if is_zip:
            with zipfile.ZipFile(stream) as archive:
                for item in archive.infolist():
                    if not item.is_dir():
                        failures.extend(
                            check_content(
                                f"{name}!{item.filename}", archive.read(item), depth + 1
                            )
                        )
        else:
            with tarfile.open(fileobj=stream) as archive:
                for member in archive:
                    if member.isdir():
                        continue
                    if not member.isfile():
                        failures.append(
                            f"{name}!{member.name}: non-source archive entry"
                        )
                        continue
                    content = archive.extractfile(member)
                    if content is not None:
                        failures.extend(
                            check_content(
                                f"{name}!{member.name}", content.read(), depth + 1
                            )
                        )
    except (OSError, tarfile.TarError, zipfile.BadZipFile, RuntimeError) as error:
        failures.append(f"{name}: unreadable archive ({type(error).__name__})")
    return failures


def check_release(paths: list[Path]) -> list[str]:
    failures = []
    for path in paths:
        try:
            failures.extend(check_content(path.name, path.read_bytes()))
        except OSError:
            failures.append(f"{path.name}: unreadable source file")
    return failures


def check_log(path: Path, compile_log: bool) -> list[str]:
    try:
        text = ANSI.sub("", path.read_text())
    except (OSError, UnicodeError):
        return ["unreadable log"]
    failures = []
    for line in text.splitlines():
        warning = WARNING_LEVEL.match(line)
        if warning is not None:
            message = warning.group(1).strip()
            if message not in WARNING_BASELINE:
                failures.append(f"new warning: {message}")
        elif re.search(r":\s*warning:", line, re.IGNORECASE):
            if not compiler_warning_is_baselined(line):
                failures.append(f"new warning: {line.strip()}")
    anchor = (
        "INFO Successfully compiled program."
        if compile_log
        else "INFO Configuration is valid!"
    )
    if anchor not in text.splitlines():
        failures.append("missing success line")
    return failures


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-only", action="store_true")
    parser.add_argument("--compile-log", type=Path)
    parser.add_argument("--config-log", type=Path)
    parser.add_argument("paths", type=Path, nargs="*")
    args = parser.parse_args()
    failed = False
    for path, label in ((args.compile_log, "compile"), (args.config_log, "config")):
        if path is not None:
            errors = check_log(path, label == "compile")
            for error in errors:
                print(f"FAIL {label} warnings: {error}")
            if not errors:
                print(f"PASS {label} warnings: new_warnings=0")
            failed |= bool(errors)
    if args.source_only:
        try:
            names = (
                subprocess.check_output(
                    ["git", "ls-files", "-co", "--exclude-standard", "-z"], cwd=ROOT
                )
                .decode()
                .split("\0")
            )
            paths = [ROOT / name for name in sorted(set(names)) if name]
            errors = check_release([*paths, *args.paths])
        except (OSError, subprocess.CalledProcessError):
            errors = ["cannot list publishable files"]
        for error in errors:
            print(f"FAIL source-only release: {error}")
        if not errors:
            print("PASS source-only release")
        failed |= bool(errors)
    elif args.paths:
        parser.error("paths require --source-only")
    elif args.compile_log is None and args.config_log is None:
        parser.error("select --source-only, --compile-log, or --config-log")
    return int(failed)


if __name__ == "__main__":
    raise SystemExit(main())
