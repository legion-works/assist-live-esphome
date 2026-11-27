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


class Zeros(io.RawIOBase):
    def __init__(self, size: int) -> None:
        self.left = size

    def readable(self) -> bool:
        return True

    def readinto(self, buffer) -> int:
        count = min(len(buffer), self.left)
        buffer[:count] = b"\0" * count
        self.left -= count
        return count


def large_archive(tmp_path: Path, archive_type: str, size: int) -> Path:
    archive = tmp_path / f"source.{archive_type}"
    if archive_type == "tar.gz":
        with tarfile.open(archive, "w:gz") as target:
            member = tarfile.TarInfo("source/large.txt")
            member.size = size
            target.addfile(member, Zeros(size))
    else:
        with (
            zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as zip_target,
            zip_target.open("source/large.txt", "w") as zip_member,
        ):
            for _ in range(size >> 20):
                zip_member.write(b"\0" * (1 << 20))
    return archive


@pytest.mark.parametrize("archive_type", ["tar.gz", "zip"])
def test_large_archive_member_is_read_in_bounded_chunks(
    tmp_path: Path, archive_type: str
) -> None:
    import tracemalloc

    from tools.check_release import check_release

    archive = large_archive(tmp_path, archive_type, 64 << 20)
    tracemalloc.start()
    try:
        failures = check_release([archive])
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert failures == []
    assert peak < 8 << 20


@pytest.mark.parametrize("archive_type", ["tar.gz", "zip"])
def test_archive_member_size_limit_is_a_named_refusal(
    tmp_path: Path, archive_type: str, monkeypatch
) -> None:
    from tools import check_release

    monkeypatch.setattr(check_release, "MEMBER_LIMIT_BYTES", 1 << 20)
    archive = large_archive(tmp_path, archive_type, 2 << 20)
    assert check_release.check_release([archive]) == [
        f"{archive.name}!source/large.txt: archive member size limit"
    ]


def nested_archive(tmp_path: Path, members: int, size: int) -> Path:
    inner = io.BytesIO()
    with zipfile.ZipFile(inner, "w") as target:
        for index in range(members):
            target.writestr(f"source/{index}.txt", b"a" * size)
    # gzip hides the inner end record, so the outer file is read as a tar.
    archive = tmp_path / "source.tar.gz"
    with tarfile.open(archive, "w:gz") as target:
        member = tarfile.TarInfo("source/inner.zip")
        member.size = len(inner.getvalue())
        target.addfile(member, io.BytesIO(inner.getvalue()))
    return archive


@pytest.mark.parametrize("limit", ["entries", "bytes"])
def test_archive_budget_covers_nested_members(
    tmp_path: Path, monkeypatch, limit: str
) -> None:
    from tools import check_release

    archive = nested_archive(tmp_path, 8, 1 << 16)
    assert check_release.check_release([archive]) == []
    if limit == "entries":
        monkeypatch.setattr(check_release, "ARCHIVE_ENTRY_LIMIT", 5)
        expected = f"{archive.name}: archive entry limit"
    else:
        monkeypatch.setattr(check_release, "ARCHIVE_LIMIT_BYTES", 5 << 16)
        expected = f"{archive.name}: archive expansion limit"
    assert check_release.check_release([archive]) == [expected]


def test_archive_budget_is_separate_for_each_release_file(
    tmp_path: Path, monkeypatch
) -> None:
    from tools import check_release

    monkeypatch.setattr(check_release, "ARCHIVE_ENTRY_LIMIT", 9)
    first = nested_archive(tmp_path, 8, 16)
    second = first.rename(tmp_path / "second.tar.gz")
    first = nested_archive(tmp_path, 8, 16)
    assert check_release.check_release([first, second]) == []


@pytest.mark.parametrize(
    "content", [b"text\n", b"\x7fELFrenamed"], ids=["clean", "elf"]
)
def test_tar_that_is_also_a_zip_is_examined_as_both(
    tmp_path: Path, content: bytes
) -> None:
    from tools.check_release import check_release

    inner = io.BytesIO()
    with zipfile.ZipFile(inner, "w") as target:
        target.writestr("notes.txt", b"text\n")
    archive = tmp_path / "source.tar"
    with tarfile.open(archive, "w") as target:
        for name, data in (("firmware.txt", content), ("inner.zip", inner.getvalue())):
            member = tarfile.TarInfo(f"source/{name}")
            member.size = len(data)
            target.addfile(member, io.BytesIO(data))
    # The stored zip at the end gives the tar a zip end record.
    assert zipfile.is_zipfile(archive) and tarfile.is_tarfile(archive)
    expected = (
        []
        if content == b"text\n"
        else [f"{archive.name}!source/firmware.txt: compiled image magic"]
    )
    assert check_release([archive]) == expected


def small_archive(tmp_path: Path, archive_type: str, members: int, size: int) -> Path:
    archive = tmp_path / f"source.{archive_type}"
    if archive_type == "tar":
        with tarfile.open(archive, "w") as target:
            for index in range(members):
                member = tarfile.TarInfo(f"source/{index}.txt")
                member.size = size
                target.addfile(member, io.BytesIO(b"a" * size))
    else:
        with zipfile.ZipFile(archive, "w") as target:
            for index in range(members):
                target.writestr(f"source/{index}.txt", b"a" * size)
    return archive


@pytest.mark.parametrize("archive_type", ["tar", "zip"])
@pytest.mark.parametrize("limit", ["entries", "bytes"])
def test_archive_headers_count_before_any_member_is_read(
    tmp_path: Path, monkeypatch, archive_type: str, limit: str
) -> None:
    from tools import check_release

    archive = small_archive(tmp_path, archive_type, 20, 1 << 16)
    if limit == "entries":
        monkeypatch.setattr(check_release, "ARCHIVE_ENTRY_LIMIT", 5)
    else:
        monkeypatch.setattr(check_release, "ARCHIVE_LIMIT_BYTES", 5 << 16)

    def refuse(*args, **kwargs):
        raise AssertionError("member read before the header check")

    monkeypatch.setattr(check_release, "check_member", refuse)
    message = "archive entry limit" if limit == "entries" else "archive expansion limit"
    assert check_release.check_release([archive]) == [f"{archive.name}: {message}"]


def header_only_zip(
    path: Path, entries: int, file_size: int = 0, extra: bytes = b""
) -> None:
    local = bytearray()
    central = bytearray()
    for index in range(entries):
        name = f"{index}.txt".encode()
        central += struct.pack(
            "<4s6H3I5H2I",
            b"PK\x01\x02",
            20,
            20,
            0,
            0,
            0,
            0x21,
            0,
            0,
            file_size,
            len(name),
            len(extra),
            0,
            0,
            0,
            0,
            len(local),
        )
        central += name + extra
        local += struct.pack(
            "<4s5H3I2H", b"PK\x03\x04", 20, 0, 0, 0, 0x21, 0, 0, 0, len(name), 0
        )
        local += name
    end = struct.pack(
        "<4s4H2IH",
        b"PK\x05\x06",
        0,
        0,
        entries,
        entries,
        len(central),
        len(local),
        0,
    )
    path.write_bytes(bytes(local + central + end))


def test_header_only_zip_stops_at_the_entry_limit_in_bounded_memory(
    tmp_path: Path,
) -> None:
    import tracemalloc

    from tools.check_release import check_release

    archive = tmp_path / "source.zip"
    header_only_zip(archive, 60_000)
    with zipfile.ZipFile(archive) as target:
        assert len(target.infolist()) == 60_000
    tracemalloc.start()
    try:
        failures = check_release([archive])
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert failures == [f"{archive.name}: archive entry limit"]
    assert peak < 4 << 20


def test_zip_central_directory_size_is_checked_before_parsing(
    tmp_path: Path, monkeypatch
) -> None:
    from tools import check_release

    archive = small_archive(tmp_path, "zip", 100, 1)
    monkeypatch.setattr(
        check_release, "ARCHIVE_METADATA_LIMIT_BYTES", 1 << 10, raising=False
    )

    def refuse(*args, **kwargs):
        raise AssertionError("central directory parsed before the size check")

    monkeypatch.setattr(zipfile.ZipFile, "__init__", refuse)
    assert check_release.check_release([archive]) == [
        f"{archive.name}: archive metadata limit"
    ]


def test_tar_extended_header_is_bounded_before_parsing(
    tmp_path: Path, monkeypatch
) -> None:
    import tracemalloc

    from tools import check_release

    archive = tmp_path / "source.tar.gz"
    with tarfile.open(archive, "w:gz", format=tarfile.PAX_FORMAT) as target:
        member = tarfile.TarInfo("source/notes.txt")
        member.pax_headers = {"comment": "a" * (32 << 20)}
        target.addfile(member, io.BytesIO())
    monkeypatch.setattr(
        check_release, "ARCHIVE_METADATA_LIMIT_BYTES", 1 << 20, raising=False
    )
    tracemalloc.start()
    try:
        failures = check_release.check_release([archive])
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert failures == [f"{archive.name}: archive metadata limit"]
    assert peak < 8 << 20


def tar_header(name: str, kind: bytes, size: int, sparse_size: int = -1) -> bytes:
    member = tarfile.TarInfo(name)
    member.type = kind
    member.size = size
    block = bytearray(member.tobuf(format=tarfile.GNU_FORMAT))
    if sparse_size >= 0:
        # Old GNU sparse header: the expanded size is at offset 483.
        block[483:495] = b"%011o\0" % sparse_size
        block[148:156] = b" " * 8
        block[148:156] = b"%06o\0 " % sum(block)
    return bytes(block)


def test_tar_traversal_is_metered_before_any_member_is_read(
    tmp_path: Path, monkeypatch
) -> None:
    import gzip

    from tools import check_release

    # The stored data is 64 MiB, but the member declares an expanded size of 0.
    archive = tmp_path / "source.tar.gz"
    with gzip.open(archive, "wb", compresslevel=1) as target:
        target.write(tar_header("source/sparse.txt", b"S", 64 << 20, 0))
        for _ in range(64):
            target.write(b"\0" * (1 << 20))
        target.write(b"\0" * 1024)
    monkeypatch.setattr(check_release, "ARCHIVE_LIMIT_BYTES", 1 << 20)

    def refuse(*args, **kwargs):
        raise AssertionError("member read before the traversal check")

    monkeypatch.setattr(check_release, "check_member", refuse)
    assert check_release.check_release([archive]) == [
        f"{archive.name}: archive expansion limit"
    ]


def test_tar_declared_size_counts_for_each_member_type(
    tmp_path: Path, monkeypatch
) -> None:
    from tools import check_release

    archive = tmp_path / "source.tar"
    archive.write_bytes(
        tar_header("source/unknown", b"Z", 2 << 20) + b"\0" * ((2 << 20) + 1024)
    )
    monkeypatch.setattr(check_release, "ARCHIVE_LIMIT_BYTES", 1 << 20)
    assert check_release.check_release([archive]) == [
        f"{archive.name}: archive expansion limit"
    ]


def test_tar_extension_headers_count_as_entries(tmp_path: Path, monkeypatch) -> None:
    from tools import check_release

    archive = tmp_path / "source.tar"
    with tarfile.open(archive, "w", format=tarfile.PAX_FORMAT) as target:
        for index in range(3):
            member = tarfile.TarInfo(f"source/{index}-" + "a" * 150)
            target.addfile(member, io.BytesIO())
    assert check_release.check_release([archive]) == []
    # Each member has a pax header and a ustar header.
    monkeypatch.setattr(check_release, "ARCHIVE_ENTRY_LIMIT", 5)
    assert check_release.check_release([archive]) == [
        f"{archive.name}: archive entry limit"
    ]


def test_tar_extension_header_chain_is_bounded(tmp_path: Path) -> None:
    from tools.check_release import check_release

    record = b"13 comment=a\n"
    pax = tar_header("pax", tarfile.XHDTYPE, len(record))
    pax += record + b"\0" * (512 - len(record))
    archive = tmp_path / "source.tar"
    archive.write_bytes(
        pax * 2000 + tar_header("source/notes.txt", tarfile.REGTYPE, 0) + b"\0" * 1024
    )
    assert check_release([archive]) == [f"{archive.name}: archive header limit"]


@pytest.mark.parametrize("tar_format", [tarfile.PAX_FORMAT, tarfile.GNU_FORMAT])
@pytest.mark.parametrize("name_size", [150, 600])
def test_tar_extension_payload_is_not_a_header(
    tmp_path: Path, monkeypatch, tar_format: int, name_size: int
) -> None:
    from tools import check_release

    # The long name gives an extension payload of 512 bytes or of 1,024 bytes.
    archive = tmp_path / "source.tar"
    with tarfile.open(archive, "w", format=tar_format) as target:
        target.addfile(tarfile.TarInfo("source/" + "a" * name_size), io.BytesIO())
    # The member has an extension header and a ustar header.
    monkeypatch.setattr(check_release, "ARCHIVE_ENTRY_LIMIT", 2)
    assert check_release.check_release([archive]) == []
    monkeypatch.setattr(check_release, "ARCHIVE_ENTRY_LIMIT", 1)
    assert check_release.check_release([archive]) == [
        f"{archive.name}: archive entry limit"
    ]


def test_tar_global_records_count_for_each_member(tmp_path: Path, monkeypatch) -> None:
    from tools import check_release

    def write(path: Path, records: dict[str, str]) -> Path:
        with tarfile.open(
            path, "w", format=tarfile.PAX_FORMAT, pax_headers=records
        ) as target:
            for index in range(200):
                target.addfile(tarfile.TarInfo(f"source/{index}"), io.BytesIO())
        return path

    monkeypatch.setattr(check_release, "ARCHIVE_METADATA_LIMIT_BYTES", 4 << 20)
    # git archive writes one global record with the commit.
    small = write(tmp_path / "small.tar", {"comment": "0" * 40})
    assert check_release.check_release([small]) == []
    # The global records are small, but tarfile copies them into each member.
    large = write(tmp_path / "large.tar", {f"k{i}": "" for i in range(1200)})
    assert large.stat().st_size < 1 << 20
    assert check_release.check_release([large]) == [
        f"{large.name}: archive metadata limit"
    ]


def test_compressed_tar_input_is_counted_before_decompression(
    tmp_path: Path, monkeypatch
) -> None:
    import gzip

    from tools import check_release

    # The gzip member has only empty deflate parts. Thus the file
    # decompresses to no bytes.
    archive = tmp_path / "source.tar.gz"
    archive.write_bytes(empty_gzip(250_000))
    assert gzip.decompress(archive.read_bytes()) == b""
    assert archive.stat().st_size > 1 << 20
    monkeypatch.setattr(
        check_release, "ARCHIVE_INPUT_LIMIT_BYTES", 1 << 18, raising=False
    )
    assert check_release.check_release([archive]) == [
        f"{archive.name}: archive input limit"
    ]


def empty_gzip(blocks: int, flags: int = 0, field: bytes = b"") -> bytes:
    empty_block = b"\x00\x00\x00\xff\xff"
    last_block = b"\x01\x00\x00\xff\xff"
    header = b"\x1f\x8b\x08" + bytes([flags]) + b"\0" * 4 + b"\x00\xff" + field
    return header + empty_block * blocks + last_block + b"\0" * 8


def compressed_tar() -> bytes:
    target = io.BytesIO()
    with tarfile.open(fileobj=target, mode="w") as archive:
        info = tarfile.TarInfo("source/notes.txt")
        info.size = 5
        archive.addfile(info, io.BytesIO(b"notes"))
    return target.getvalue()


def framing(kind: str) -> bytes:
    import bz2
    import gzip
    import lzma

    tar = compressed_tar()
    if kind == "gzip-padding":
        return gzip.compress(tar, mtime=0) + b"\0" * (1 << 20)
    if kind == "gzip-name":
        return empty_gzip(1, 8, b"a" * 2048 + b"\0")
    if kind == "gzip-comment":
        return empty_gzip(1, 16, b"a" * (1 << 20) + b"\0")
    if kind == "gzip-extra":
        return empty_gzip(1, 4, struct.pack("<H", 2048) + b"a" * 2048)
    if kind == "gzip-members":
        return gzip.compress(tar, mtime=0) + gzip.compress(b"", mtime=0) * 16
    if kind == "bz2-streams":
        return bz2.compress(tar) + bz2.compress(b"") * 16
    return lzma.compress(tar) + lzma.compress(b"") * 16


@pytest.mark.parametrize(
    "kind",
    [
        "gzip-padding",
        "gzip-name",
        "gzip-comment",
        "gzip-extra",
        "gzip-members",
        "bz2-streams",
        "xz-streams",
    ],
)
def test_compressed_framing_is_bounded_with_default_limits(
    tmp_path: Path, monkeypatch, kind: str
) -> None:
    from tools import check_release

    archive = tmp_path / "source.tar.gz"
    archive.write_bytes(framing(kind))
    reads = []
    original = check_release.InputReader.read

    def count(self, size: int = -1) -> bytes:
        reads.append(size)
        return original(self, size)

    monkeypatch.setattr(check_release.InputReader, "read", count)
    assert check_release.check_release([archive]) == [
        f"{archive.name}: archive compression limit"
    ]
    # The refusal occurs before the decoder reads the file one byte at a time.
    assert len(reads) < 100


def test_compressed_framing_of_valid_archives_passes(tmp_path: Path) -> None:
    import bz2
    import gzip
    import lzma

    from tools.check_release import check_release

    tar = compressed_tar()
    half = len(tar) // 2
    for name, data in (
        ("two.tar.gz", gzip.compress(tar[:half]) + gzip.compress(tar[half:])),
        ("padded.tar.gz", gzip.compress(tar) + b"\0" * 512),
        ("two.tar.bz2", bz2.compress(tar[:half]) + bz2.compress(tar[half:])),
        ("two.tar.xz", lzma.compress(tar[:half]) + lzma.compress(tar[half:])),
    ):
        archive = tmp_path / name
        archive.write_bytes(data)
        assert check_release([archive]) == [], name


def test_zero_filled_file_is_not_decoded_as_lzma(tmp_path: Path, monkeypatch) -> None:
    import lzma

    from tools.check_release import check_release

    created = []
    original = lzma.LZMADecompressor

    def factory(*args, **kwargs):
        created.append(1)
        return original(*args, **kwargs)

    monkeypatch.setattr(lzma, "LZMADecompressor", factory)
    blank = tmp_path / "blank.dat"
    blank.write_bytes(b"\0" * (1 << 20))
    assert check_release([blank]) == []
    assert len(created) <= 1


def pax_payload(size: int) -> bytes:
    records = []
    total = 0
    index = 0
    while total < size:
        record = b" k%x=\n" % index
        length = len(record) + len(str(len(record) + 2))
        records.append(b"%d" % length + record)
        total += length
        index += 1
    return b"".join(records)


@pytest.mark.parametrize(
    "kind", [tarfile.XGLTYPE, tarfile.XHDTYPE, tarfile.GNUTYPE_LONGNAME]
)
@pytest.mark.parametrize("name", ["source.tar", "notes.dat"])
def test_tar_extension_payload_size_is_checked_before_parsing(
    tmp_path: Path, kind: bytes, name: str
) -> None:
    import tracemalloc

    from tools.check_release import check_release

    # The second name has no archive suffix. Thus only the format probe opens it.
    payload = (
        b"a" * (1 << 20) if kind == tarfile.GNUTYPE_LONGNAME else pax_payload(1 << 20)
    )
    archive = tmp_path / name
    archive.write_bytes(
        tar_header("pax", kind, len(payload))
        + payload
        + b"\0" * (-len(payload) % 512)
        + tar_header("source/notes.txt", tarfile.REGTYPE, 0)
        + b"\0" * 1024
    )
    tracemalloc.start()
    try:
        failures = check_release([archive])
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert failures == [f"{name}: archive metadata limit"]
    assert peak < 4 << 20


def test_tar_local_records_count_the_global_copy(tmp_path: Path, monkeypatch) -> None:
    from tools import check_release

    archive = tmp_path / "source.tar"
    with tarfile.open(
        archive,
        "w",
        format=tarfile.PAX_FORMAT,
        pax_headers={f"k{i}": "" for i in range(1200)},
    ) as target:
        for index in range(50):
            # The long name gives each member a local pax header.
            member = tarfile.TarInfo(f"source/{index}-" + "a" * 150)
            target.addfile(member, io.BytesIO())
    monkeypatch.setattr(check_release, "ARCHIVE_METADATA_LIMIT_BYTES", 6 << 20)
    assert check_release.check_release([archive]) == [
        f"{archive.name}: archive metadata limit"
    ]


def test_zip_member_reads_count_as_input(tmp_path: Path, monkeypatch) -> None:
    from tools import check_release

    archive = tmp_path / "source.zip"
    with zipfile.ZipFile(archive, "w") as target:
        target.writestr("source/notes.txt", b"a" * (4 << 20))
    # The format probes of the member read less than 2 MiB.
    monkeypatch.setattr(
        check_release, "ARCHIVE_INPUT_LIMIT_BYTES", 3 << 20, raising=False
    )
    assert check_release.check_release([archive]) == [
        f"{archive.name}: archive input limit"
    ]


def test_zip_extra_field_count_is_bounded(tmp_path: Path) -> None:
    from tools.check_release import check_release

    archive = tmp_path / "source.zip"
    header_only_zip(archive, 1, 0xFFFFFFFF, b"\x99\x99\0\0" * 16_000)
    assert check_release([archive]) == [f"{archive.name}: archive header limit"]


def test_zip_with_two_zip64_fields_is_refused(tmp_path: Path) -> None:
    from tools.check_release import check_release

    archive = tmp_path / "source.zip"
    zip64 = struct.pack("<HHQ", 1, 8, 10) + struct.pack("<HHQ", 1, 8, 20)
    header_only_zip(archive, 1, 0xFFFFFFFF, zip64)
    assert check_release([archive]) == [
        f"{archive.name}: unreadable archive (BadZipFile)"
    ]


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
