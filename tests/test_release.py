import io
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


@pytest.mark.parametrize("suffix", [".elf", ".map", ".uf2", ".factory.img"])
def test_compiled_suffix_is_refused(tmp_path: Path, suffix: str) -> None:
    from tools.check_release import check_release

    image = tmp_path / f"firmware{suffix}"
    image.write_bytes(b"test")
    assert check_release([image])


@pytest.mark.parametrize(
    "magic", [b"\x7fELF", b"\xe9\x03\x00\x00", b"\x00" * 4096 + b"\xe9"]
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
