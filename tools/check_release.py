# SPDX-License-Identifier: GPL-3.0-or-later
import argparse
import io
import json
import re
import shutil
import struct
import subprocess
import tarfile
import tempfile
import zipfile
from pathlib import Path
from typing import IO, Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
CMAKE_VERSION = "3.30.2"
COMPILED_SUFFIXES = {".bin", ".elf", ".map", ".uf2", ".img", ".hex"}
# Archive members go to a temporary file in chunks, not into memory.
CHUNK_BYTES = 1 << 16
# The limit stops an expanded member before it fills the temporary disk.
MEMBER_LIMIT_BYTES = 1 << 30
# One release file, with its nested archives, has these totals.
ARCHIVE_LIMIT_BYTES = 1 << 32
ARCHIVE_ENTRY_LIMIT = 10_000
# Archive headers (ZIP central directory, TAR headers) are read before the
# members. This limit stops them before they fill memory.
ARCHIVE_METADATA_LIMIT_BYTES = 1 << 26
# A tar member has a small number of extended headers. A zip entry has a
# small number of `extra` fields. Python uses recursion for tar extended
# headers. For `extra` fields, its work increases as the square of the count.
TAR_HEADER_CHAIN_LIMIT = 16
ZIP_EXTRA_FIELD_LIMIT = 64
# The merged-image check reads the partition table, which ends at 0x9000.
PREFIX_BYTES = 0x9000
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
CMAKE_WARNING = re.compile(
    r"^CMake Warning at (?P<path>.+?):(?P<line>\d+) \(message\):$"
)
CMAKE_BASELINE = {
    ("esp-idf", "tools/cmake/build.cmake", 631, ""): (
        "5.5.6",
        "dependencies.lock:dependencies.idf.version",
    ),
    (
        "esp-idf",
        "tools/cmake/project.cmake",
        765,
        "Missing kconfig option.  Re-run the build process...",
    ): ("5.5.6", "dependencies.lock:dependencies.idf.version"),
}


def read_fixture_idf_version(
    lock_path: Path = ROOT / "tests/fixtures/dependencies.lock",
) -> str:
    try:
        idf_version = yaml.safe_load(lock_path.read_text())["dependencies"]["idf"][
            "version"
        ]
        if not isinstance(idf_version, str) or not re.fullmatch(
            r"\d+\.\d+\.\d+", idf_version
        ):
            raise ValueError("invalid IDF version")
    except (OSError, ValueError, TypeError, KeyError, yaml.YAMLError) as error:
        raise ValueError("fixture IDF dependency lock missing or invalid") from error
    return idf_version


def resolve_cmake(lock_path: Path = ROOT / "tests/fixtures/dependencies.lock") -> Path:
    from esphome.espidf.framework import check_esp_idf_install, get_framework_env

    idf_version = read_fixture_idf_version(lock_path)
    framework, python_env = check_esp_idf_install(idf_version, targets=["esp32s3"])
    manifest = json.loads((framework / "tools/tools.json").read_text())
    recommended = [
        version["name"]
        for tool in manifest["tools"]
        if tool["name"] == "cmake"
        for version in tool["versions"]
        if version["status"] == "recommended"
    ]
    if recommended != [CMAKE_VERSION]:
        raise ValueError(
            f"CMake pin mismatch: IDF recommends {recommended}, "
            f"expected {CMAKE_VERSION}"
        )
    environment = get_framework_env(framework, python_env)
    executable = shutil.which("cmake", path=environment["PATH"])
    if executable is None:
        raise ValueError("CMake executable missing from ESP-IDF environment")
    return Path(executable)


def check_cmake_toolchain() -> bool:
    executable = None
    version = "unknown"
    try:
        executable = resolve_cmake()
        result = subprocess.run(
            [str(executable), "--version"],
            capture_output=True,
            text=True,
            check=True,
            timeout=30,
        )
        match = re.search(r"(?m)^cmake version (\S+)$", result.stdout)
        version = match[1] if match else "unknown"
        print(f"INFO CMake toolchain: path={executable} version={version}")
        if version != CMAKE_VERSION:
            raise ValueError(
                f"CMake toolchain mismatch: expected {CMAKE_VERSION}, found {version}"
            )
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        print(
            f"FAIL CMake toolchain: path={executable or 'unresolved'} "
            f"version={version} error={error}"
        )
        return False
    print(f"PASS CMake toolchain: version={CMAKE_VERSION}")
    return True


def read_build_cmake(build_root: Path) -> tuple[str, str]:
    try:
        text = (build_root / "build/CMakeCache.txt").read_text()
        fields = dict(re.findall(r"(?m)^(CMAKE_\w+):(?:INTERNAL|FILEPATH)=(.+)$", text))
        executable = fields["CMAKE_COMMAND"]
        version = ".".join(
            fields[f"CMAKE_CACHE_{part}_VERSION"]
            for part in ("MAJOR", "MINOR", "PATCH")
        )
        if not Path(executable).is_absolute():
            raise ValueError("non-absolute CMake command")
        return executable, version
    except (OSError, ValueError, KeyError, UnicodeError) as error:
        raise ValueError("CMake toolchain cache missing or invalid") from error


def check_component_versions(build_root: Path) -> list[str]:
    failures = []
    try:
        expected_idf = read_fixture_idf_version()
    except (OSError, ValueError, TypeError, KeyError, yaml.YAMLError):
        expected_idf = None
        failures.append("cannot read fixture IDF baseline version source")
    try:
        actual_idf = yaml.safe_load((build_root / "dependencies.lock").read_text())[
            "dependencies"
        ]["idf"]["version"]
        if expected_idf is not None and actual_idf != expected_idf:
            failures.append("fixture IDF version mismatch: compiled dependency lock")
    except (OSError, ValueError, TypeError, KeyError, yaml.YAMLError):
        failures.append("cannot read compiled IDF version source: dependencies.lock")
    for version, source in sorted(
        set(COMPILER_BASELINE.values()) | set(CMAKE_BASELINE.values())
    ):
        filename, field = source.split(":", 1)
        component = field.removeprefix("dependencies.").removesuffix(".version")
        try:
            lock = yaml.safe_load((build_root / filename).read_text())
            actual = lock["dependencies"][component]["version"]
        except (OSError, ValueError, TypeError, KeyError, yaml.YAMLError):
            failures.append(f"cannot read baseline version source: {source}")
            continue
        if actual != version:
            failures.append(f"baseline version mismatch: {source}: expected {version}")
    return failures


def cmake_warning_is_baselined(header: str, message: str) -> bool:
    warning = CMAKE_WARNING.fullmatch(header)
    if warning is None:
        return False
    path = Path(warning["path"])
    if ".." in path.parts or "components/assist_live/" in path.as_posix():
        return False
    if path.parent.name != "cmake" or path.parent.parent.name != "tools":
        return False
    framework = path.parent.parent.parent
    if framework.name != "framework-espidf" and framework.parent.name != "frameworks":
        return False
    key = ("esp-idf", "tools/cmake/" + path.name, int(warning["line"]), message)
    baseline = CMAKE_BASELINE.get(key)
    if baseline is None:
        return False
    version, _ = baseline
    return framework.name == "framework-espidf" or framework.name == version


def esp_image_header(data: bytes, offset: int = 0) -> bool:
    header = data[offset : offset + 24]
    # ESP-IDF 5.5.6 esp_app_format.h:81-110 defines the 24-byte header.
    return (
        len(header) == 24
        and header[0] == 0xE9
        and 1 <= header[1] <= 16
        and header[2] <= 5
        and header[3] & 0x0F in {0, 1, 2, 15}
        and header[3] >> 4 <= 7
        and header[19:23] == b"\0" * 4
        and header[23] in {0, 1}
    )


def merged_esp_image(data: bytes, stream: IO[bytes] | None = None) -> bool:
    """Find a factory image. With a stream, data is only the file prefix."""
    if not esp_image_header(data, 0x1000):
        return False
    # ESP32-S3 factory images contain a partition table and an app partition.
    for offset in range(0x8000, min(len(data), 0x9000) - 31, 32):
        entry = data[offset : offset + 32]
        if entry[:2] != b"\xaa\x50":
            break
        app_offset = int.from_bytes(entry[4:8], "little")
        if entry[2] != 0 or app_offset < 0x10000:
            continue
        if stream is None:
            header = data[app_offset : app_offset + 24]
        else:
            stream.seek(app_offset)
            header = stream.read(24)
        if esp_image_header(header):
            return True
    return False


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


class ArchiveBudgetError(Exception):
    pass


class ArchiveBudget:
    """Count the entries, expanded bytes, and header bytes of one release file.

    Nested archives use the budget of the release file that contains them.
    """

    def __init__(self) -> None:
        self.entries = ARCHIVE_ENTRY_LIMIT
        self.bytes = ARCHIVE_LIMIT_BYTES
        self.metadata = ARCHIVE_METADATA_LIMIT_BYTES

    def entry(self) -> None:
        self.entries -= 1
        if self.entries < 0:
            raise ArchiveBudgetError("archive entry limit")

    def declare(self, size: int) -> None:
        """Refuse an archive if its declared member sizes are more than the budget."""
        if size > self.bytes:
            raise ArchiveBudgetError("archive expansion limit")

    def expand(self, size: int) -> None:
        self.bytes -= size
        if self.bytes < 0:
            raise ArchiveBudgetError("archive expansion limit")

    def read_metadata(self, size: int) -> None:
        self.metadata -= size
        if self.metadata < 0:
            raise ArchiveBudgetError("archive metadata limit")


class MetadataReader:
    """Give the uncompressed tar stream to tarfile and meter it.

    The reader counts each byte that tarfile reads or skips, after
    decompression. It also counts the header reads and the header blocks.
    Each check occurs before the read or the seek, because tarfile reads a
    complete extended header with one call, and a forward seek in a
    compressed stream decompresses the skipped bytes.
    """

    def __init__(
        self,
        raw: Any,
        limit: int,
        physical_limit: int,
        budget: ArchiveBudget | None,
    ) -> None:
        self.raw = raw
        self.limit = limit
        self.physical_limit = physical_limit
        self.budget = budget
        self.used = 0
        self.physical = 0
        self.headers = 0
        self.counting = True

    def advance(self, size: int) -> None:
        if self.physical + size > self.physical_limit:
            raise ArchiveBudgetError("archive expansion limit")
        self.physical += size

    def read(self, size: int = -1) -> bytes:
        if size < 0:
            raise ArchiveBudgetError("archive metadata limit")
        self.advance(size)
        if not self.counting:
            return self.raw.read(size)
        if self.used + size > self.limit:
            raise ArchiveBudgetError("archive metadata limit")
        data = self.raw.read(size)
        self.used += len(data)
        # 512 bytes with the value 0 end the archive. Each other read of this size
        # gets a header, an extended header, or a part of a sparse map.
        if size == tarfile.BLOCKSIZE and data.strip(b"\0"):
            self.headers += 1
            if self.headers > TAR_HEADER_CHAIN_LIMIT:
                raise ArchiveBudgetError("archive header limit")
            if self.budget is not None:
                self.budget.entry()
        return data

    def write(self, data: bytes) -> object:
        raise OSError("read-only archive")

    def tell(self) -> int:
        return self.raw.tell()

    def seek(self, offset: int, whence: int = 0) -> object:
        current = self.raw.tell()
        if whence == 1:
            offset += current
        elif whence != 0:
            raise OSError("unsupported seek")
        # To go to an earlier position, a compressed stream starts again at 0.
        self.advance(offset - current if offset >= current else offset)
        return self.raw.seek(offset)

    def close(self) -> object:
        return self.raw.close()


class MetadataTarFile(tarfile.TarFile):
    metadata_limit = 0
    physical_limit = 0
    entry_budget: ArchiveBudget | None = None
    reader: MetadataReader

    @classmethod
    def taropen(cls, name, mode="r", fileobj=None, **kwargs: Any):
        # tarfile.open gives the decompressed stream to taropen. Thus the
        # reader sees the uncompressed bytes.
        reader = MetadataReader(
            fileobj, cls.metadata_limit, cls.physical_limit, cls.entry_budget
        )
        archive = super().taropen(name, mode, reader, **kwargs)
        archive.reader = reader
        return archive


def open_tar(
    stream: IO[bytes],
    limit: int,
    physical_limit: int,
    budget: ArchiveBudget | None = None,
) -> MetadataTarFile:
    class LimitedTarFile(MetadataTarFile):
        metadata_limit = limit
        entry_budget = budget

    LimitedTarFile.physical_limit = physical_limit
    stream.seek(0)
    return LimitedTarFile.open(fileobj=stream, mode="r:*")


def next_member(archive: MetadataTarFile) -> tarfile.TarInfo | None:
    archive.reader.headers = 0
    archive.reader.counting = True
    member = archive.next()
    archive.reader.counting = False
    return member


def is_tar(stream: IO[bytes], budget: ArchiveBudget) -> bool:
    """Do the tarfile.is_tarfile test with the header limits."""
    try:
        with open_tar(stream, budget.metadata, budget.bytes):
            return True
    except tarfile.TarError:
        return False


def zip_declared_size(size: int, extra: bytes) -> int:
    """Give the member size that zipfile reads from the `extra` data.

    zipfile copies the remaining `extra` data for each field. The field limit
    stops that work before ZipFile reads the central directory.
    """
    offset = 0
    fields = 0
    zip64 = False
    while len(extra) - offset >= 4:
        fields += 1
        if fields > ZIP_EXTRA_FIELD_LIMIT:
            raise ArchiveBudgetError("archive header limit")
        kind, length = struct.unpack_from("<HH", extra, offset)
        if offset + 4 + length > len(extra):
            raise zipfile.BadZipFile("Corrupt extra field")
        if kind == 1:
            # Each ZIP64 field can change the sizes. One field is unambiguous.
            if zip64:
                raise zipfile.BadZipFile("more than one zip64 extra field")
            zip64 = True
            if size == 0xFFFFFFFF:
                if length < 8:
                    raise zipfile.BadZipFile("Corrupt zip64 extra field")
                size = int(struct.unpack_from("<Q", extra, offset + 4)[0])
        offset += 4 + length
    return size


def count_zip_headers(stream: IO[bytes], budget: ArchiveBudget) -> None:
    """Count the central directory entries before zipfile reads them.

    ZipFile reads the complete central directory and makes one ZipInfo for
    each entry. This walk reads one entry at a time and stops at a limit.
    """
    # ZipFile uses this function to find the central directory. Thus the walk
    # examines the same bytes. Index 5 is the size. Index 9 is the location of
    # the end record.
    end = zipfile._EndRecData(stream)  # type: ignore[attr-defined]
    if not end:
        raise zipfile.BadZipFile("File is not a zip file")
    size = end[5]
    start = end[9] - size
    if start < 0:
        raise zipfile.BadZipFile("Bad offset for central directory")
    budget.read_metadata(size)
    stream.seek(start)
    total = 0
    declared = 0
    while total < size:
        header = stream.read(46)
        if len(header) != 46 or not header.startswith(b"PK\x01\x02"):
            raise zipfile.BadZipFile("Bad magic number for central directory")
        file_size, name_size, extra_size, comment_size = struct.unpack_from(
            "<I3H", header, 24
        )
        budget.entry()
        stream.seek(name_size, 1)
        extra = stream.read(extra_size)
        stream.seek(comment_size, 1)
        declared += zip_declared_size(file_size, extra)
        budget.declare(declared)
        total += 46 + name_size + extra_size + comment_size


def count_tar_headers(stream: IO[bytes], budget: ArchiveBudget) -> tuple[int, int]:
    """Read all tar headers before a member is read.

    Each 512-byte header, also an extended header, counts as an entry. Each
    member size counts, for all member types. Give the header limit and the
    stream limit for the second read.
    """
    with open_tar(stream, budget.metadata, budget.bytes, budget) as archive:
        declared = 0
        entries = 0
        while (member := next_member(archive)) is not None:
            entries += 1
            declared += member.size
            budget.declare(declared)
        budget.read_metadata(archive.reader.used)
        # Before each header, tarfile can read one byte to find the end of
        # the member data. The stream position controls that read.
        return (
            archive.reader.used + entries,
            archive.reader.physical + entries + 2 * tarfile.BLOCKSIZE,
        )


def check_member(
    name: str, source: IO[bytes], declared: int, depth: int, budget: ArchiveBudget
) -> list[str]:
    if declared > MEMBER_LIMIT_BYTES:
        return [f"{name}: archive member size limit"]
    if declared > budget.bytes:
        raise ArchiveBudgetError("archive expansion limit")
    with tempfile.TemporaryFile() as spool:
        size = 0
        while chunk := source.read(CHUNK_BYTES):
            size += len(chunk)
            if size > MEMBER_LIMIT_BYTES:
                return [f"{name}: archive member size limit"]
            budget.expand(len(chunk))
            spool.write(chunk)
        return check_content(name, spool, depth, budget)


def check_content(
    name: str,
    data: bytes | IO[bytes],
    depth: int = 0,
    budget: ArchiveBudget | None = None,
) -> list[str]:
    if budget is None:
        try:
            return check_content(name, data, depth, ArchiveBudget())
        except ArchiveBudgetError as error:
            return [f"{name}: {error}"]
    stream = io.BytesIO(data) if isinstance(data, bytes) else data
    failures = []
    if Path(name).suffix.lower() in COMPILED_SUFFIXES:
        failures.append(f"{name}: compiled artifact suffix")
    stream.seek(0)
    prefix = stream.read(PREFIX_BYTES)
    if (
        prefix.startswith((b"\x7fELF", b"UF2\n"))
        or esp_image_header(prefix)
        or merged_esp_image(prefix, stream)
    ):
        failures.append(f"{name}: compiled image magic")
    # Python 3.12 zipfile.is_zipfile does not restore the stream position.
    # Each probe starts at offset 0.
    stream.seek(0)
    is_zip = zipfile.is_zipfile(stream)
    tar = is_tar(stream, budget)
    archive_suffix = name.lower().endswith((".zip", ".tar", ".tar.gz", ".tgz"))
    if not (is_zip or tar or archive_suffix):
        return failures
    if depth >= 3:
        return [*failures, f"{name}: archive nesting limit"]
    # The check examines each archive format that it finds in the file. A
    # finding in one format gives a refusal.
    scans = []
    if is_zip:
        scans.append(check_zip)
    if tar or not is_zip:
        scans.append(check_tar)
    for scan in scans:
        try:
            stream.seek(0)
            failures.extend(scan(name, stream, depth, budget))
        except (OSError, tarfile.TarError, zipfile.BadZipFile, RuntimeError) as error:
            failures.append(f"{name}: unreadable archive ({type(error).__name__})")
    return failures


def check_zip(
    name: str, stream: IO[bytes], depth: int, budget: ArchiveBudget
) -> list[str]:
    count_zip_headers(stream, budget)
    failures = []
    stream.seek(0)
    with zipfile.ZipFile(stream) as archive:
        for item in archive.infolist():
            if not item.is_dir():
                with archive.open(item) as content:
                    failures.extend(
                        check_member(
                            f"{name}!{item.filename}",
                            content,
                            item.file_size,
                            depth + 1,
                            budget,
                        )
                    )
    return failures


def check_tar(
    name: str, stream: IO[bytes], depth: int, budget: ArchiveBudget
) -> list[str]:
    header_limit, physical_limit = count_tar_headers(stream, budget)
    failures = []
    # This second read gets the same bytes. The budget has these bytes from
    # the first read. Thus the limits come from the first read.
    with open_tar(stream, header_limit, physical_limit) as archive:
        while (member := next_member(archive)) is not None:
            if member.isdir():
                pass
            elif not member.isfile():
                failures.append(f"{name}!{member.name}: non-source archive entry")
            elif (extracted := archive.extractfile(member)) is not None:
                failures.extend(
                    check_member(
                        f"{name}!{member.name}",
                        extracted,
                        member.size,
                        depth + 1,
                        budget,
                    )
                )
    return failures


def check_release(paths: list[Path]) -> list[str]:
    failures = []
    for path in paths:
        try:
            with path.open("rb") as stream:
                failures.extend(check_content(path.name, stream))
        except OSError:
            failures.append(f"{path.name}: unreadable source file")
    return failures


def check_log(
    path: Path, compile_log: bool, build_root: Path | None = None
) -> list[str]:
    try:
        text = ANSI.sub("", path.read_text())
    except (OSError, UnicodeError):
        return ["unreadable log"]
    failures = (
        check_component_versions(build_root or path.parent)
        if compile_log or re.search(r"(?m)^\s*CMake (?:Deprecation )?Warning\b", text)
        else []
    )
    if compile_log:
        try:
            executable, version = read_build_cmake(build_root or path.parent)
            if version != CMAKE_VERSION:
                failures.append(
                    f"CMake toolchain mismatch: path={executable} version={version}; "
                    f"expected {CMAKE_VERSION}"
                )
        except ValueError as error:
            failures.append(str(error))
    lines = text.splitlines()
    for index, line in enumerate(lines):
        if re.match(r"^\s*CMake (?:Deprecation )?Warning\b", line):
            body = []
            for continuation in lines[index + 1 :]:
                if not continuation.startswith(("  ", "\t")):
                    break
                body.append(continuation.strip())
            message = " ".join(body)
            if not cmake_warning_is_baselined(line.strip(), message):
                failures.append(f"new warning: {line} {message}".strip())
            continue
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
    parser.add_argument("--toolchain", action="store_true")
    parser.add_argument("--compile-log", type=Path)
    parser.add_argument("--config-log", type=Path)
    parser.add_argument("--build-root", type=Path)
    parser.add_argument("paths", type=Path, nargs="*")
    args = parser.parse_args()
    failed = args.toolchain and not check_cmake_toolchain()
    for path, label in ((args.compile_log, "compile"), (args.config_log, "config")):
        if path is not None:
            if label == "compile":
                try:
                    executable, version = read_build_cmake(
                        args.build_root or path.parent
                    )
                    print(f"INFO CMake build: path={executable} version={version}")
                except ValueError:
                    pass
            errors = check_log(path, label == "compile", args.build_root)
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
            deleted = set(
                subprocess.check_output(
                    ["git", "ls-files", "--deleted", "-z"], cwd=ROOT
                )
                .decode()
                .split("\0")
            )
            paths = [ROOT / name for name in sorted(set(names) - deleted) if name]
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
    elif args.compile_log is None and args.config_log is None and not args.toolchain:
        parser.error(
            "select --source-only, --compile-log, --config-log, or --toolchain"
        )
    return int(failed)


if __name__ == "__main__":
    raise SystemExit(main())
