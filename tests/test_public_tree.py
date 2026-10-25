import ipaddress
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize(
    "value", [0x0A000001, 0xAC100001, 0xC0A80001, 0xA9FE0101, 0x64400001]
)
def test_public_scan_refuses_private_addresses(value):
    from tools.check_public_tree import scan_text

    assert scan_text(str(ipaddress.IPv4Address(value)), set())["network"] == 1
    assert not scan_text("192.0.2.1 and timing-server.invalid", set())


def test_public_scan_refuses_private_paths_and_ipv6():
    from tools.check_public_tree import scan_text

    for text in (
        "/" + "home/example/file",
        "/" + "Users/example/file",
        "C:" + chr(92) + "Users" + chr(92) + "example",
    ):
        assert scan_text(text, set())["private_path"] == 1
    assert (
        scan_text(
            str(ipaddress.IPv6Address(0xFD000000000000000000000000000001)), set()
        )["network"]
        == 1
    )


def test_public_scan_reports_optional_denylist_without_private_values(tmp_path, capsys):
    from tools.check_public_tree import main

    root = tmp_path / "tree"
    root.mkdir()
    assert not any((parent / ".git").exists() for parent in root.parents)
    subprocess.run(
        ["git", "-C", str(root), "init", "-b", "main"], check=True, capture_output=True
    )
    public = root / "public.txt"
    public.write_text("public canary 192.0.2.1")
    assert main(["--root", str(root)]) == 0
    assert "NOT CHECKED private denylist" in capsys.readouterr().out
    denylist = tmp_path / "denylist.txt"
    denylist.write_text("synthetic-blocked-value\n")
    public.write_text("synthetic-blocked-value")
    assert main(["--root", str(root), "--private-denylist", str(denylist)]) == 1
    output = capsys.readouterr().out
    assert "denylist=1" in output and "synthetic-blocked-value" not in output
    private = str(ipaddress.IPv4Address(0xC0A80001))
    public.write_text(private)
    assert main(["--root", str(root)]) == 1
    output = capsys.readouterr().out
    assert "network=1" in output and private not in output
