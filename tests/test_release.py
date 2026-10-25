import io
import json
import re
import struct
import subprocess
import sys
import tarfile
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_binary_release_is_refused(tmp_path: Path) -> None:
    from tools.check_release import check_release

    image = tmp_path / "firmware.bin"
    image.write_bytes(b"test")
    assert check_release([image])


@pytest.mark.parametrize("suffix", [".elf", ".map", ".uf2", ".factory.img", ".hex"])
def test_compiled_suffix_is_refused(tmp_path: Path, suffix: str) -> None:
    from tools.check_release import check_release

    image = tmp_path / f"firmware{suffix}"
    image.write_bytes(b"test")
    assert check_release([image])


@pytest.mark.parametrize(
    "magic",
    [
        b"\x7fELF",
        b"\xe9\x03\x00\x00" + b"\0" * 20,
        b"\xff" * 4096
        + b"\xe9\x03\x00\x00"
        + b"\0" * 20
        + b"\xff" * (0x8000 - 4096 - 24)
        + struct.pack("<HBBII16sI", 0x50AA, 0, 0, 0x10000, 0x100000, b"app", 0)
        + b"\xff" * (0x10000 - 0x8000 - 32)
        + b"\xe9\x03\x00\x00"
        + b"\0" * 20,
    ],
    ids=["elf", "app", "factory"],
)
def test_renamed_image_is_refused(tmp_path: Path, magic: bytes) -> None:
    from tools.check_release import check_release

    image = tmp_path / "firmware.txt"
    image.write_bytes(magic)
    assert check_release([image])


@pytest.mark.parametrize("archive_type", ["tar", "zip"])
def test_release_archive_is_inspected(tmp_path: Path, archive_type: str) -> None:
    from tools.check_release import check_release

    archive = tmp_path / f"source.{archive_type}"
    content = b"\x7fELFrenamed"
    if archive_type == "tar":
        with tarfile.open(archive, "w") as target:
            member = tarfile.TarInfo("source/firmware.txt")
            member.size = len(content)
            target.addfile(member, io.BytesIO(content))
    else:
        with zipfile.ZipFile(archive, "w") as target:
            target.writestr("source/firmware.txt", content)
    assert check_release([archive])


def test_source_passes_and_failures_are_collected(tmp_path: Path) -> None:
    from tools.check_release import check_release

    source = tmp_path / "component.cpp"
    source.write_text("void setup() {}\n")
    assert check_release([source]) == []
    assert len(check_release([tmp_path / "missing", tmp_path / "other"])) == 2


BASELINE = (
    "WARNING register_action('voice_kit.flash', ...) is missing the synchronous= "
    "parameter. Defaulting to synchronous=False (safe but prevents StringRef "
    "optimization). Check the C++ class: use synchronous=False if play_next_() "
    "is deferred to a callback, timer, or loop(); use synchronous=True if "
    "play_next_() always runs before the initial play/play_complex call returns\n"
    "WARNING GPIO0 is a strapping pin and should only be used for I/O with care.\n"
    "Attaching external pullup/down resistors to strapping pins can cause "
    "unexpected failures.\n"
    "See https://esphome.io/guides/faq/#why-am-i-getting-a-warning-about-strapping-pins\n"
    "WARNING GPIO3 is a strapping pin and should only be used for I/O with care.\n"
    "WARNING [esp32_rmt_led_strip] 'rgb_order' is deprecated, use "
    "'channel_colors: GRB'. Will be removed in 2027.3.0\n"
    "WARNING GPIO45 is a strapping pin and should only be used for I/O with care.\n"
    "INFO Successfully compiled program.\n"
)


def test_stock_warning_baseline_passes(tmp_path: Path) -> None:
    log = tmp_path / "compile.log"
    log.write_text(BASELINE)
    result = subprocess.run(
        [sys.executable, "tools/check_release.py", "--compile-log", str(log)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "PASS compile warnings" in result.stdout


def test_warning_word_in_url_is_not_a_warning(tmp_path: Path) -> None:
    from tools.check_release import check_log

    log = tmp_path / "compile.log"
    log.write_text(
        "https://example.invalid/a-warning-reference\n"
        "INFO Successfully compiled program.\n"
    )
    assert check_log(log, compile_log=True) == []


def test_warning_prefix_is_normalized(tmp_path: Path) -> None:
    from tools.check_release import check_log

    log = tmp_path / "compile.log"
    log.write_text(
        "\x1b[33m2026-10-24T12:00:00Z WARNING GPIO0 is a strapping pin "
        "and should only be used for I/O with care.\x1b[0m\n"
        "INFO Successfully compiled program.\n"
    )
    assert check_log(log, compile_log=True) == []


@pytest.mark.parametrize(
    "extra",
    [
        "WARNING new component warning\n",
        "file.cpp:1:2: warning: new warning\n",
    ],
)
def test_new_compile_warning_is_refused(tmp_path: Path, extra: str) -> None:
    log = tmp_path / "compile.log"
    log.write_text(BASELINE + extra)
    result = subprocess.run(
        [sys.executable, "tools/check_release.py", "--compile-log", str(log)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 1
    assert "FAIL compile warnings" in result.stdout


def test_missing_compile_success_is_refused(tmp_path: Path) -> None:
    log = tmp_path / "compile.log"
    log.write_text("INFO Compiling\n")
    result = subprocess.run(
        [sys.executable, "tools/check_release.py", "--compile-log", str(log)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 1


COMPILER_DIAGNOSTICS = [
    (
        "build/esp-idf/esphome__micro-opus/opus-staged/silk/NLSF2A.c",
        54,
        19,
        "'cos_LSF_QA' may be used uninitialized",
        "-Wmaybe-uninitialized",
    ),
    *[
        (
            "managed_components/espressif__esp-tflite-micro/"
            f"tensorflow/lite/kernels/internal/reference/{name}.h",
            line,
            column,
            "declaration of 'const tflite::ArithmeticParams& params' "
            "shadows a parameter",
            "-Wshadow",
        )
        for name, line, column in [
            ("mul", 150, 34),
            ("mul", 209, 34),
            ("mul", 249, 34),
            ("sub", 264, 62),
            ("sub", 284, 34),
            ("sub", 308, 62),
            ("sub", 420, 62),
        ]
    ],
]


@pytest.mark.parametrize("source,line,column,message,flag", COMPILER_DIAGNOSTICS)
def test_third_party_compiler_baseline_passes(
    tmp_path: Path, source: str, line: int, column: int, message: str, flag: str
) -> None:
    from tools.check_release import check_log

    log = tmp_path / "compile.log"
    log.write_text(
        f"\x1b[33m{tmp_path / source}:{line}:{column}: warning: "
        f"{message} [{flag}]\x1b[0m\nINFO Successfully compiled program.\n"
    )
    assert check_log(log, compile_log=True) == []


@pytest.mark.parametrize(
    "source",
    [
        "components/assist_live/mul.h",
        "src/esphome/components/assist_live/managed_components/"
        "espressif__esp-tflite-micro/tensorflow/lite/kernels/internal/reference/mul.h",
        "tests/fixtures/voice-pe.yaml",
        "examples/voice-pe.yaml",
    ],
)
def test_owned_source_cannot_use_compiler_baseline(tmp_path: Path, source: str) -> None:
    from tools.check_release import check_log

    log = tmp_path / "compile.log"
    log.write_text(
        f"{source}:150:34: warning: declaration of "
        "'const tflite::ArithmeticParams& params' shadows a parameter [-Wshadow]\n"
        "INFO Successfully compiled program.\n"
    )
    assert check_log(log, compile_log=True)


@pytest.fixture(autouse=True)
def component_versions(tmp_path):
    (tmp_path / "dependencies.lock").write_text(
        "dependencies:\n  esphome/micro-opus:\n    version: 0.4.1\n"
        "  espressif/esp-tflite-micro:\n    version: 1.3.3~1\n"
        "  idf:\n    version: 5.5.6\n"
    )
    (tmp_path / "build").mkdir(exist_ok=True)
    (tmp_path / "build/CMakeCache.txt").write_text(
        "CMAKE_COMMAND:INTERNAL=/test-tools/cmake/3.30.2/bin/cmake\n"
        "CMAKE_CACHE_MAJOR_VERSION:INTERNAL=3\n"
        "CMAKE_CACHE_MINOR_VERSION:INTERNAL=30\n"
        "CMAKE_CACHE_PATCH_VERSION:INTERNAL=2\n"
    )


@pytest.mark.parametrize("offset", [0, 4096])
def test_random_magic_byte_is_not_an_image(offset):
    from tools.check_release import check_content

    assert check_content("source.txt", b"a" * offset + b"\xe9" + b"a" * 100) == []


def test_app_header_is_refused():
    from tools.check_release import check_content

    header = struct.pack("<BBBBI", 0xE9, 3, 0, 0x2F, 0x40370000) + b"\0" * 16
    assert check_content("renamed.txt", header)


@pytest.mark.parametrize("change", ["version", "missing", "source"])
def test_compile_checks_component_versions(tmp_path, change):
    from tools.check_release import check_log

    lock = tmp_path / "dependencies.lock"
    if change == "version":
        lock.write_text(lock.read_text().replace("0.4.1", "0.4.2"))
    elif change == "source":
        lock.write_text(lock.read_text().replace("esphome/micro-opus", "other/opus"))
    else:
        lock.unlink()
    log = tmp_path / "compile.log"
    log.write_text("INFO Successfully compiled program.\n")
    assert check_log(log, compile_log=True)


CI_CMAKE_DEPRECATIONS = (
    "Compatibility with CMake < 3.10 will be removed from a future version of CMake. "
    "Update the VERSION argument <min> value.  Or, use the <min>...<max> syntax "
    "to tell CMake that the project requires at least <min> but has been updated "
    "to work with policies introduced by <max> or earlier."
)


def test_ci_deprecation_fragment_reports_cmake_drift(tmp_path):
    from tools.check_release import check_log

    cache = tmp_path / "build/CMakeCache.txt"
    cache.write_text(
        "CMAKE_COMMAND:INTERNAL=/runner-tools/cmake/4.4.4/bin/cmake\n"
        "CMAKE_CACHE_MAJOR_VERSION:INTERNAL=4\n"
        "CMAKE_CACHE_MINOR_VERSION:INTERNAL=4\n"
        "CMAKE_CACHE_PATCH_VERSION:INTERNAL=4\n"
    )
    log = tmp_path / "compile.log"
    log.write_text(
        "".join(
            f"CMake Warning (deprecated) at managed_components/{component}/"
            "CMakeLists.txt:"
            f"{line} (cmake_minimum_required):\n  {CI_CMAKE_DEPRECATIONS}\n\n"
            for component, line in [
                ("espressif__esp-nn", 1),
                ("espressif__esp-tflite-micro", 3),
            ]
            * 2
        )
        + "INFO Successfully compiled program.\n"
    )
    errors = check_log(log, compile_log=True)
    assert any(
        "CMake toolchain mismatch" in error and "4.4.4" in error for error in errors
    )
    assert sum("new warning" in error for error in errors) == 4


@pytest.mark.parametrize("change", ["missing", "version", "command"])
def test_compile_refuses_cmake_cache_drift(tmp_path, change):
    from tools.check_release import check_log

    cache = tmp_path / "build/CMakeCache.txt"
    if change == "missing":
        cache.unlink()
    elif change == "version":
        cache.write_text(
            cache.read_text().replace("VERSION:INTERNAL=30", "VERSION:INTERNAL=31")
        )
    else:
        cache.write_text(
            cache.read_text().replace(
                "CMAKE_COMMAND:INTERNAL=", "OTHER_COMMAND:INTERNAL="
            )
        )
    log = tmp_path / "compile.log"
    log.write_text("INFO Successfully compiled program.\n")
    assert any("CMake toolchain" in error for error in check_log(log, compile_log=True))


@pytest.mark.parametrize("version,exit_code", [("3.30.2", 0), ("4.4.4", 1)])
def test_cmake_preflight_reports_path_and_version(
    tmp_path, monkeypatch, capsys, version, exit_code
):
    from tools import check_release

    binary = tmp_path / "cmake"
    binary.write_text(f"#!/bin/sh\nprintf 'cmake version {version}\\n'\n")
    binary.chmod(0o700)
    monkeypatch.setattr(check_release, "resolve_cmake", lambda: binary, raising=False)
    monkeypatch.setattr(sys, "argv", ["check_release.py", "--toolchain"])
    assert check_release.main() == exit_code
    output = capsys.readouterr().out
    assert str(binary) in output
    assert version in output
    assert ("PASS" if exit_code == 0 else "FAIL") + " CMake toolchain" in output


def test_resolver_checks_manifest_and_uses_framework_environment(tmp_path, monkeypatch):
    from esphome.espidf import framework

    from tools.check_release import resolve_cmake

    tools = tmp_path / "tools"
    tools.mkdir()
    manifest = tools / "tools.json"
    manifest.write_text(
        json.dumps(
            {
                "tools": [
                    {
                        "name": "cmake",
                        "versions": [{"name": "3.30.2", "status": "recommended"}],
                    }
                ]
            }
        )
    )
    binary = tmp_path / "bin/cmake"
    binary.parent.mkdir()
    binary.write_text("#!/bin/sh\nexit 0\n")
    binary.chmod(0o700)
    monkeypatch.setattr(
        framework,
        "check_esp_idf_install",
        lambda *args, **kwargs: (tmp_path, tmp_path / "penv"),
    )
    monkeypatch.setattr(
        framework, "get_framework_env", lambda *args: {"PATH": str(binary.parent)}
    )
    assert resolve_cmake() == binary
    manifest.write_text(manifest.read_text().replace("3.30.2", "3.31.0"))
    with pytest.raises(ValueError, match="CMake pin mismatch"):
        resolve_cmake()


@pytest.mark.parametrize("ci", [None, "true"])
def test_cmake_resolver_uses_fixture_lock_and_one_target_set(tmp_path, monkeypatch, ci):
    from esphome.espidf import framework

    from tools.check_release import resolve_cmake

    if ci:
        monkeypatch.setenv("CI", ci)
    else:
        monkeypatch.delenv("CI", raising=False)
    calls = []

    def install(version, *, targets):
        calls.append((version, targets))
        return tmp_path, tmp_path / "penv"

    monkeypatch.setattr(framework, "check_esp_idf_install", install)
    monkeypatch.setattr(
        framework, "get_framework_env", lambda *args: {"PATH": str(tmp_path)}
    )
    (tmp_path / "tools").mkdir()
    (tmp_path / "tools/tools.json").write_text(
        json.dumps(
            {
                "tools": [
                    {
                        "name": "cmake",
                        "versions": [{"name": "3.30.2", "status": "recommended"}],
                    }
                ]
            }
        )
    )
    binary = tmp_path / "cmake"
    binary.write_text("fake executable")
    binary.chmod(0o700)
    lock = tmp_path / "dependencies.lock"
    lock.write_text("dependencies:\n  idf:\n    version: 5.5.7\n")
    assert resolve_cmake(lock) == binary
    assert calls == [("5.5.7", ["esp32s3"])]


@pytest.mark.parametrize("mode", ["resolve", "execute", "version"])
def test_cmake_failures_have_one_shape(tmp_path, monkeypatch, capsys, mode):
    from tools import check_release

    binary = tmp_path / "cmake"
    binary.write_text(
        "#!/bin/sh\n"
        + ("exit 2\n" if mode == "execute" else "printf 'cmake version 4.4.4\\n'\n")
    )
    binary.chmod(0o700)

    def resolve():
        if mode == "resolve":
            raise ValueError("fixture failure")
        return binary

    monkeypatch.setattr(check_release, "resolve_cmake", resolve)
    assert not check_release.check_cmake_toolchain()
    errors = [
        line for line in capsys.readouterr().out.splitlines() if line.startswith("FAIL")
    ]
    assert len(errors) == 1
    assert re.fullmatch(
        r"FAIL CMake toolchain: path=\S+ version=\S+ error=.+", errors[0]
    )


def test_compile_checks_the_fixture_idf_lock_against_the_actual_build(
    tmp_path, monkeypatch
):
    from tools import check_release

    log = tmp_path / "compile.log"
    log.write_text("INFO Successfully compiled program.\n")
    monkeypatch.setattr(
        check_release, "read_fixture_idf_version", lambda: "5.5.7", raising=False
    )
    assert any(
        "fixture IDF version mismatch" in error
        for error in check_release.check_log(log, compile_log=True)
    )


@pytest.mark.parametrize(
    "header",
    [
        "CMake Deprecation Warning at other.cmake:1 (message):",
        "  CMake Warning at other.cmake:1 (message):",
    ],
)
def test_other_cmake_warning_forms_are_refused(tmp_path, header):
    from tools.check_release import check_log

    log = tmp_path / "compile.log"
    log.write_text(header + "\n  notice\n\nINFO Successfully compiled program.\n")
    assert any("new warning" in error for error in check_log(log, compile_log=True))


@pytest.mark.parametrize(
    "diagnostic",
    [
        "CMake Warning at other.cmake:1 (message):\n  new notice\n\n",
        "CMake Warning (dev) at other.cmake:1 (message):\n  new notice\n\n",
        "CMake Warning:\n  unknown notice\n\n",
        "CMake Warning at framework-espidf/tools/cmake/project.cmake:765 (message):\n"
        "  changed notice\n\n",
    ],
)
def test_new_cmake_warning_is_refused(tmp_path, diagnostic):
    from tools.check_release import check_log

    log = tmp_path / "compile.log"
    log.write_text(diagnostic + "INFO Successfully compiled program.\n")
    assert any("new warning" in error for error in check_log(log, compile_log=True))


@pytest.mark.parametrize(
    "name,line,message",
    [
        ("build", 631, ""),
        ("project", 765, "Missing kconfig option.  Re-run the build process..."),
    ],
)
@pytest.mark.parametrize("framework_path", ["framework-espidf", "frameworks/5.5.6"])
def test_upstream_cmake_baseline_checks_framework_version(
    tmp_path, name, line, message, framework_path
):
    from tools.check_release import check_log

    framework = tmp_path / framework_path
    framework.mkdir(parents=True)
    log = tmp_path / "compile.log"
    log.write_text(
        f"CMake Warning at {framework}/tools/cmake/{name}.cmake:{line} (message):\n"
        + (f"  {message}\n" if message else "")
        + "\nCall Stack (most recent call first):\n  CMakeLists.txt:1 (project)\n\n"
        "INFO Successfully compiled program.\n"
    )
    assert check_log(log, compile_log=True) == []
    lock = tmp_path / "dependencies.lock"
    lock.write_text(lock.read_text().replace("5.5.6", "5.5.7"))
    assert check_log(log, compile_log=True)


@pytest.mark.parametrize("change", ["line", "path", "message", "missing-version"])
def test_cmake_baseline_fields_are_exact(tmp_path, change):
    from tools.check_release import check_log

    framework = tmp_path / "framework-espidf"
    framework.mkdir()
    if change == "missing-version":
        lock = tmp_path / "dependencies.lock"
        lock.write_text(lock.read_text().replace("  idf:\n    version: 5.5.6\n", ""))
    source = "project" if change != "path" else "other"
    line = 765 if change != "line" else 766
    message = "Missing kconfig option.  Re-run the build process..."
    if change == "message":
        message += " changed"
    log = tmp_path / "compile.log"
    log.write_text(
        f"CMake Warning at {framework}/tools/cmake/{source}.cmake:{line} (message):\n"
        f"  {message}\n\nINFO Successfully compiled program.\n"
    )
    errors = check_log(log, compile_log=True)
    expected = (
        "baseline version source" if change == "missing-version" else "new warning"
    )
    assert any(expected in error for error in errors)


def test_native_cmake_baseline_uses_compiled_tree_version(tmp_path):
    from tools.check_release import check_log

    log = tmp_path / "compile.log"
    log.write_text(
        f"CMake Warning at {tmp_path}/frameworks/5.5.6/"
        "tools/cmake/build.cmake:631 (message):\n"
        "Call Stack (most recent call first):\n  CMakeLists.txt:3 (project)\n\n"
        "INFO Successfully compiled program.\n"
    )
    assert check_log(log, compile_log=True) == []


@pytest.mark.parametrize("changed", ["path", "line", "flag", "message"])
def test_compiler_baseline_fields_are_exact(tmp_path: Path, changed: str) -> None:
    from tools.check_release import check_log

    diagnostic = (
        "managed_components/espressif__esp-tflite-micro/"
        "tensorflow/lite/kernels/internal/reference/mul.h:150:34: warning: "
        "declaration of 'const tflite::ArithmeticParams& params' shadows a parameter "
        "[-Wshadow]\nINFO Successfully compiled program.\n"
    )
    before, after = {
        "path": ("mul.h", "other.h"),
        "line": (":150:", ":151:"),
        "flag": ("-Wshadow", "-Wextra"),
        "message": ("shadows a parameter", "hides a parameter"),
    }[changed]
    log = tmp_path / "compile.log"
    log.write_text(diagnostic.replace(before, after))
    assert check_log(log, compile_log=True)


def test_changed_config_baseline_text_is_refused(tmp_path: Path) -> None:
    from tools.check_release import check_log

    log = tmp_path / "compile.log"
    log.write_text(
        BASELINE.replace("GPIO0 is a strapping pin", "GPIO0 changed warning")
    )
    assert check_log(log, compile_log=True)


@pytest.mark.parametrize("content", [None, "[broken", "dependencies: {}"])
def test_build_lock_error_names_compiled_source(tmp_path, content):
    from tools.check_release import check_component_versions

    lock = tmp_path / "dependencies.lock"
    if content is None:
        lock.unlink()
    else:
        lock.write_text(content)
    errors = check_component_versions(tmp_path)
    assert "cannot read compiled IDF version source: dependencies.lock" in errors
    assert "cannot read fixture IDF baseline version source" not in errors


def test_explicit_missing_source_still_fails(tmp_path, monkeypatch, capsys):
    from tools.check_release import main

    monkeypatch.setattr(
        sys, "argv", ["check_release.py", "--source-only", str(tmp_path / "missing.py")]
    )
    assert main() == 1
    assert (
        "FAIL source-only release: missing.py: unreadable source file"
        in capsys.readouterr().out
    )
