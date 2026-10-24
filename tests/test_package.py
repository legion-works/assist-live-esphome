import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_source_only_boundary():
    assert (ROOT / "components/assist_live/assist_live.h").exists()
    assert "GNU GENERAL PUBLIC LICENSE" in (ROOT / "LICENSE").read_text()
    result = subprocess.run(
        ["git", "ls-files", "--", "*.bin"], check=True, capture_output=True, cwd=ROOT
    )
    assert result.stdout == b""
